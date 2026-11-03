"""Fix It Proper backend: analyze, contact, saved reports, locked CORS, contract errors."""

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.analyze import run_analysis
from app.brand import NAME, SLUG
from app.cache.store import FetchCache
from app.config import Settings, get_settings
from app.db import (
    AuthError,
    ContactMessageDoc,
    Database,
    ReportDoc,
    VerifiedUser,
    build_database,
    delete_auth_user,
    normalize_report_url,
    verify_id_token,
)
from app.fetcher.models import FetchError
from app.fetcher.playwright_fetcher import BrowserManager
from app.json_logging import request_id_var, setup_logging
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ContactRequest,
    ErrorResponse,
    ReportListResponse,
    ReportSummary,
    StatusResponse,
)
from app.security.rate_limit import RateLimiter, RateLimitExceeded
from app.security.url_guard import UrlBlockedError

logger = logging.getLogger(SLUG)

_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{1,64}")

_GUARD_STATUS = {
    "URL_BLOCKED": 400,
    "TOO_MANY_REDIRECTS": 422,
    "RESPONSE_TOO_LARGE": 422,
    "FETCH_TIMEOUT": 504,
    "FETCH_FAILED": 502,
    "NOT_HTML": 422,
    "FETCH_BLOCKED": 502,
    "UNSUPPORTED_SITE": 422,
}
_GUARD_MESSAGE = {
    "URL_BLOCKED": "URL is not allowed for analysis.",
    "TOO_MANY_REDIRECTS": "URL redirected too many times.",
    "RESPONSE_TOO_LARGE": "Page is larger than 3 MB and was not fetched.",
    "FETCH_TIMEOUT": "Fetching the page timed out.",
    "FETCH_FAILED": "Page could not be fetched.",
}
_GUARD_RETRYABLE = {"FETCH_TIMEOUT", "FETCH_FAILED"}


def _error_payload(code: str, message: str, retryable: bool) -> dict[str, object]:
    return ErrorResponse(code=code, message=message, retryable=retryable).model_dump(mode="json")


class AuthRequiredError(Exception):
    """Raised when a protected route gets no usable bearer token."""


class ServiceUnavailableError(Exception):
    """Raised when Firebase is unreachable or unconfigured."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BadRequestError(Exception):
    """Raised for 422 failures with a specific contract code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request_id to every request and log one JSON access line."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = int((time.perf_counter() - start) * 1000)
                logger.exception(
                    "request failed",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": duration_ms,
                        "client_ip": _client_ip(request),
                    },
                )
                raise
            duration_ms = int((time.perf_counter() - start) * 1000)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": _client_ip(request),
                },
            )
            return response
        finally:
            request_id_var.reset(token)


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")


def _clean_text(value: str) -> str:
    """Strip markup and collapse whitespace from contact input."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", value)).strip()


def _to_summary(doc: ReportDoc) -> ReportSummary:
    """Project a stored report to its list shape, tolerating odd payloads."""
    payload = doc.response
    summary = payload.get("summary")
    issues = payload.get("issues")
    score = payload.get("score")
    score_value: float | None = None
    if isinstance(score, dict):
        raw_value = score.get("value")
        if isinstance(raw_value, (int, float)):
            score_value = min(100.0, max(0.0, float(raw_value)))
    return ReportSummary(
        id=doc.request_id,
        url=doc.url,
        data_quality=doc.data_quality,
        summary=summary if isinstance(summary, str) else "",
        issue_count=len(issues) if isinstance(issues, list) else 0,
        score_value=score_value,
        created_at=doc.created_at,
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.browser.aclose()


def _enforce_analyze_rate_limit(request: Request) -> None:
    limiter: RateLimiter = request.app.state.limiter
    limiter.check(_client_ip(request))


def _enforce_contact_rate_limit(request: Request) -> None:
    limiter: RateLimiter = request.app.state.contact_limiter
    limiter.check(_client_ip(request))


def _require_db(request: Request) -> Database:
    db: Database = request.app.state.db
    if not db.enabled:
        raise ServiceUnavailableError("Database is unavailable. Try again later.")
    return db


async def _current_user(request: Request) -> VerifiedUser:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthRequiredError
    db: Database = request.app.state.db
    if not db.enabled or db.app is None:
        raise ServiceUnavailableError("Sign in service is unavailable. Try again later.")
    try:
        return await verify_id_token(db.app, token.strip())
    except AuthError:
        raise AuthRequiredError from None


async def _optional_user(request: Request) -> VerifiedUser | None:
    """Best effort identity for analyze autosave. Never raises."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    db: Database = request.app.state.db
    if not db.enabled or db.app is None:
        return None
    try:
        return await verify_id_token(db.app, token.strip())
    except AuthError:
        logger.warning("ignoring invalid auth token on analyze")
        return None


async def _maybe_save_report(request: Request, response: AnalyzeResponse) -> None:
    """Save a signed in user's report. Failures only log, never break analyze."""
    try:
        user = await _optional_user(request)
        if user is None:
            return
        db: Database = request.app.state.db
        if not db.enabled:
            return
        settings: Settings = request.app.state.settings
        now = datetime.now(UTC)
        await db.users.upsert(user.uid, user.email or "", now)
        doc = ReportDoc(
            user_id=user.uid,
            request_id=response.request_id,
            url=normalize_report_url(response.url),
            data_quality=response.data_quality,
            response=response.model_dump(mode="json"),
            created_at=now,
            expires_at=now + timedelta(days=settings.report_retention_days),
        )
        await db.reports.save(doc)
    except Exception:
        logger.exception("report autosave failed", extra={"request_id": response.request_id})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Pass explicit settings in tests, env settings in prod."""
    resolved = settings or get_settings()
    setup_logging(resolved.log_level)

    app = FastAPI(title=NAME, docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)
    app.state.settings = resolved
    app.state.limiter = RateLimiter(limit=resolved.rate_limit_per_hour)
    app.state.contact_limiter = RateLimiter(
        limit=resolved.contact_rate_limit_per_hour,
        exceeded_message="Too many messages from this address. Try again later.",
    )
    app.state.db = build_database(resolved)
    app.state.fetch_cache = FetchCache(
        ttl_seconds=resolved.fetch_cache_ttl_seconds,
        max_total_bytes=resolved.fetch_cache_max_mb * 1024 * 1024,
    )
    app.state.pagespeed_cache = FetchCache(ttl_seconds=86400, max_total_bytes=32 * 1024 * 1024)
    app.state.analysis_cache = FetchCache(
        ttl_seconds=resolved.fetch_cache_ttl_seconds,
        max_total_bytes=resolved.fetch_cache_max_mb * 1024 * 1024,
    )
    app.state.browser = BrowserManager()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        logger.warning("rate limited", extra={"client_ip": _client_ip(request)})
        return JSONResponse(
            status_code=429,
            content=_error_payload(
                "RATE_LIMITED",
                exc.message or "Too many analyses from this address. Try again later.",
                True,
            ),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )

    @app.exception_handler(AuthRequiredError)
    async def _auth_handler(request: Request, exc: AuthRequiredError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=_error_payload("UNAUTHORIZED", "Sign in is required.", False),
        )

    @app.exception_handler(ServiceUnavailableError)
    async def _unavailable_handler(request: Request, exc: ServiceUnavailableError) -> JSONResponse:
        logger.warning("dependency unavailable", extra={"detail": exc.message})
        return JSONResponse(
            status_code=503,
            content=_error_payload("SERVICE_UNAVAILABLE", exc.message, True),
        )

    @app.exception_handler(BadRequestError)
    async def _bad_request_handler(request: Request, exc: BadRequestError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_payload(exc.code, exc.message, False),
        )

    @app.exception_handler(UrlBlockedError)
    async def _url_blocked_handler(request: Request, exc: UrlBlockedError) -> JSONResponse:
        logger.warning("url rejected", extra={"reason": exc.reason})
        if isinstance(exc, FetchError):
            message, retryable = exc.public_message, exc.retryable
        else:
            message = _GUARD_MESSAGE.get(exc.code, "URL is not allowed for analysis.")
            retryable = exc.code in _GUARD_RETRYABLE
        return JSONResponse(
            status_code=_GUARD_STATUS.get(exc.code, 400),
            content=_error_payload(exc.code, message, retryable),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        all_missing = bool(errors) and all(err.get("type") == "missing" for err in errors)
        touches_url = any("url" in err.get("loc", ()) for err in errors)
        if touches_url and not all_missing:
            payload = _error_payload(
                "INVALID_URL", "URL must start with http:// or https://.", False
            )
        else:
            payload = _error_payload("INVALID_REQUEST", "Request validation failed.", False)
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            payload = _error_payload("NOT_FOUND", "Not found.", False)
        elif exc.status_code == 405:
            payload = _error_payload("METHOD_NOT_ALLOWED", "Method not allowed.", False)
        else:
            payload = _error_payload("HTTP_ERROR", "Request failed.", False)
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        return JSONResponse(
            status_code=500,
            content=_error_payload("INTERNAL_ERROR", "Something went wrong.", True),
        )

    @app.get("/api/health")
    async def _health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/analyze",
        response_model=AnalyzeResponse,
        dependencies=[Depends(_enforce_analyze_rate_limit)],
    )
    async def _analyze(
        body: AnalyzeRequest,
        request: Request,
        brand_voice: str = Query(default="", max_length=2000),
    ) -> AnalyzeResponse:
        request_id = getattr(request.state, "request_id", "") or uuid.uuid4().hex
        response = await run_analysis(
            str(body.url),
            request_id=request_id,
            brand_voice=brand_voice,
            settings=request.app.state.settings,
            fetch_cache=request.app.state.fetch_cache,
            pagespeed_cache=request.app.state.pagespeed_cache,
            analysis_cache=request.app.state.analysis_cache,
            browser_manager=request.app.state.browser,
        )
        await _maybe_save_report(request, response)
        return response

    @app.post(
        "/api/contact",
        response_model=StatusResponse,
        dependencies=[Depends(_enforce_contact_rate_limit)],
    )
    async def _contact(body: ContactRequest, request: Request) -> StatusResponse:
        if body.company.strip():
            return StatusResponse(status="received")
        try:
            clean = ContactRequest(
                name=_clean_text(body.name),
                email=_clean_text(body.email),
                message=_clean_text(body.message),
            )
        except PydanticValidationError:
            raise BadRequestError(
                "INVALID_REQUEST",
                "Name, email, and message must stay valid after removing markup.",
            ) from None
        db = _require_db(request)
        await db.contacts.save(
            ContactMessageDoc(
                name=clean.name,
                email=clean.email,
                message=clean.message,
                created_at=datetime.now(UTC),
            )
        )
        return StatusResponse(status="received")

    @app.get("/api/reports", response_model=ReportListResponse)
    async def _list_reports(
        request: Request, user: VerifiedUser = Depends(_current_user)
    ) -> ReportListResponse:
        db = _require_db(request)
        await db.users.upsert(user.uid, user.email or "", datetime.now(UTC))
        docs = await db.reports.list_by_user(user.uid)
        return ReportListResponse(reports=[_to_summary(doc) for doc in docs])

    @app.delete("/api/reports/{report_id}", response_model=StatusResponse)
    async def _delete_report(
        report_id: str, request: Request, user: VerifiedUser = Depends(_current_user)
    ) -> StatusResponse:
        db = _require_db(request)
        doc = await db.reports.get(report_id)
        if doc is None or doc.user_id != user.uid:
            raise StarletteHTTPException(status_code=404)
        await db.reports.delete(report_id)
        return StatusResponse(status="deleted")

    @app.delete("/api/account", response_model=StatusResponse)
    async def _delete_account(
        request: Request, user: VerifiedUser = Depends(_current_user)
    ) -> StatusResponse:
        db = _require_db(request)
        await db.reports.delete_by_user(user.uid)
        if user.email:
            await db.contacts.delete_by_email(user.email)
        await db.users.delete(user.uid)
        app_handle = db.app
        assert app_handle is not None
        # Auth deletion runs last so a retry finishes the job idempotently.
        await delete_auth_user(app_handle, user.uid)
        return StatusResponse(status="deleted")

    return app


app = create_app()
