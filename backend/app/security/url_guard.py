"""SSRF protection: validate URLs and fetch them inside strict limits."""

import asyncio
import codecs
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.brand import USER_AGENT

MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 3 * 1024 * 1024
TOTAL_TIMEOUT_SECONDS = 25.0

_PER_REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_DEFAULT_PORTS = {"http": 80, "https": 443}
_DEC_PART = re.compile(r"[0-9]+$")
_CHARSET = re.compile(r"charset=([A-Za-z0-9_.-]+)")

_BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("100::/64"),
    ipaddress.ip_network("2001:db8::/32"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
)
_METADATA_IPS = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("100.100.100.200"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)


class UrlBlockedError(ValueError):
    """Raised when a URL is rejected or a guarded fetch fails."""

    def __init__(self, reason: str, code: str = "URL_BLOCKED") -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True)
class FetchResult:
    """Outcome of a guarded fetch: final URL, status, and capped body."""

    final_url: str
    status_code: int
    content: bytes
    content_type: str
    headers: dict[str, str]
    redirect_count: int

    @property
    def text(self) -> str:
        """Decode the body with the declared charset, else UTF-8."""
        return self.content.decode(_charset_from_content_type(self.content_type), errors="replace")


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    if ip in _METADATA_IPS:
        return True
    for network in _BLOCKED_NETWORKS:
        if ip.version == network.version and ip in network:
            return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _ip_is_blocked(ip.ipv4_mapped)
    return False


def _parse_legacy_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """Parse inet_aton style addresses: decimal, octal, hex, short forms."""
    if not host or len(host) > 64 or host.count(".") > 3:
        return None
    parts = host.split(".")
    if len(parts) > 4:
        return None
    numbers: list[int] = []
    for part in parts:
        if not part:
            return None
        base = 10
        digits = part
        lowered = part.lower()
        if lowered.startswith("0x") and len(part) > 2:
            base, digits = 16, part[2:]
        elif len(part) > 1 and part.startswith("0"):
            base = 8
        if base == 10 and _DEC_PART.fullmatch(digits) is None:
            return None
        try:
            numbers.append(int(digits, base))
        except ValueError:
            return None
    if any(n < 0 for n in numbers):
        return None
    packed: int | None = None
    if len(numbers) == 1:
        if numbers[0] <= 0xFFFFFFFF:
            packed = numbers[0]
    elif len(numbers) == 2:
        if numbers[0] <= 0xFF and numbers[1] <= 0xFFFFFF:
            packed = (numbers[0] << 24) | numbers[1]
    elif len(numbers) == 3:
        if numbers[0] <= 0xFF and numbers[1] <= 0xFF and numbers[2] <= 0xFFFF:
            packed = (numbers[0] << 24) | (numbers[1] << 16) | numbers[2]
    elif all(n <= 0xFF for n in numbers):
        packed = (numbers[0] << 24) | (numbers[1] << 16) | (numbers[2] << 8) | numbers[3]
    if packed is None:
        return None
    return ipaddress.IPv4Address(packed)


def _parse_literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    text = host.strip("[]")
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return _parse_legacy_ipv4(text)


def _resolve_host(host: str, port: int) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlBlockedError("host could not be resolved", code="FETCH_FAILED") from exc
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        try:
            addresses.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            raise UrlBlockedError("host resolved badly", code="FETCH_FAILED") from None
    if not addresses:
        raise UrlBlockedError("host has no addresses", code="FETCH_FAILED")
    return addresses


def validate_url(raw_url: str) -> str:
    """Check a URL for SSRF risk and return its normalized form.

    Rejects non-http schemes, userinfo, localhost, and any host whose
    literal or resolved address falls in a blocked range.
    """
    url = (raw_url or "").strip()
    if not url:
        raise UrlBlockedError("empty URL")
    if any(char in url for char in ("\x00", "\n", "\r", "\t", " ")):
        raise UrlBlockedError("URL has whitespace or control characters")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise UrlBlockedError("malformed URL") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UrlBlockedError("only http and https URLs are allowed")
    if parts.username or parts.password or "@" in parts.netloc:
        raise UrlBlockedError("credentials in URL are not allowed")
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise UrlBlockedError("URL has no host")
    if host == "localhost" or host.endswith(".localhost"):
        raise UrlBlockedError("localhost is not allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise UrlBlockedError("URL has an invalid port") from exc
    if port == 0:
        raise UrlBlockedError("URL has an invalid port")

    literal = _parse_literal_ip(host)
    if literal is not None:
        if _ip_is_blocked(literal):
            raise UrlBlockedError("IP address is not allowed")
    else:
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except (UnicodeError, ValueError) as exc:
            raise UrlBlockedError("host name is invalid") from exc
        if len(ascii_host) > 253:
            raise UrlBlockedError("host name is too long")
        for resolved in _resolve_host(ascii_host, port or _DEFAULT_PORTS[scheme]):
            if _ip_is_blocked(resolved):
                raise UrlBlockedError("host resolves to a blocked address")

    netloc = host
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        netloc = f"{netloc}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "", parts.query, ""))


def _charset_from_content_type(content_type: str) -> str:
    match = _CHARSET.search(content_type or "")
    if match:
        try:
            codecs.lookup(match.group(1))
            return match.group(1)
        except LookupError:
            pass
    return "utf-8"


async def _fetch_loop(
    client: httpx.AsyncClient, url: str, max_redirects: int, max_bytes: int, user_agent: str
) -> FetchResult:
    current = url
    redirects = 0
    headers = {"User-Agent": user_agent, "Accept": "text/html,*/*;q=0.8"}
    while True:
        checked = await asyncio.to_thread(validate_url, current)
        try:
            async with client.stream("GET", checked, headers=headers) as response:
                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise UrlBlockedError("redirect has no target", code="FETCH_FAILED")
                    redirects += 1
                    if redirects > max_redirects:
                        raise UrlBlockedError("too many redirects", code="TOO_MANY_REDIRECTS")
                    current = urljoin(checked, location)
                    continue
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        raise UrlBlockedError("response is too large", code="RESPONSE_TOO_LARGE")
                return FetchResult(
                    final_url=checked,
                    status_code=response.status_code,
                    content=bytes(body),
                    content_type=response.headers.get("content-type", ""),
                    headers=dict(response.headers),
                    redirect_count=redirects,
                )
        except httpx.TimeoutException as exc:
            raise UrlBlockedError("fetch timed out", code="FETCH_TIMEOUT") from exc
        except httpx.InvalidURL as exc:
            raise UrlBlockedError("malformed URL") from exc
        except httpx.HTTPError as exc:
            raise UrlBlockedError("fetch failed", code="FETCH_FAILED") from exc


async def fetch_url_guarded(
    url: str,
    *,
    max_redirects: int = MAX_REDIRECTS,
    max_bytes: int = MAX_RESPONSE_BYTES,
    total_timeout: float = TOTAL_TIMEOUT_SECONDS,
    user_agent: str = USER_AGENT,
    client: httpx.AsyncClient | None = None,
) -> FetchResult:
    """Fetch a URL after SSRF checks on the start URL and every redirect.

    Follows at most max_redirects hops, reads at most max_bytes of body,
    and aborts the whole fetch after total_timeout seconds.
    """
    owned = client is None
    active = (
        client
        if client is not None
        else httpx.AsyncClient(follow_redirects=False, timeout=_PER_REQUEST_TIMEOUT)
    )
    try:
        async with asyncio.timeout(total_timeout):
            return await _fetch_loop(active, url, max_redirects, max_bytes, user_agent)
    except TimeoutError as exc:
        raise UrlBlockedError("fetch timed out", code="FETCH_TIMEOUT") from exc
    finally:
        if owned:
            await active.aclose()
