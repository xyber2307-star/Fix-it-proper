"""Shared backend test fixtures."""

import os
import socket

import pytest

from app.config import Settings


def _loops_available() -> bool:
    try:
        first, second = socket.socketpair()
    except OSError:
        return False
    first.close()
    second.close()
    return True


LOOPS_AVAILABLE = _loops_available()


@pytest.fixture
def stub_dns(monkeypatch):
    """Replace DNS with a writable host to IP list mapping.

    Unknown hosts raise gaierror like a real NXDOMAIN. Tests fill the
    returned dict, for example stub_dns["shop.test"] = ["93.184.216.34"].
    """
    mapping: dict[str, list[str]] = {}

    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host not in mapping:
            raise socket.gaierror(8, "Name or service not known")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in mapping[host]]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    return mapping


def skip_without_loop() -> None:
    """Skip the calling test when this box cannot build an event loop."""
    if not LOOPS_AVAILABLE:
        pytest.skip("event loops need socketpair, blocked in this sandbox")


@pytest.fixture
def require_loop():
    """Skip when this box cannot build an event loop.

    Loop construction needs socketpair, which some sandboxes block.
    Skipped tests run normally on any dev machine or CI runner.
    """
    skip_without_loop()


@pytest.fixture
def require_emulator():
    """Skip when no Firestore emulator host is configured.

    Start the emulator first: firebase emulators:start --only firestore,auth
    """
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("needs FIRESTORE_EMULATOR_HOST pointing at the Firestore emulator")


def emulator_settings(**overrides):
    """Settings pointed at the emulator. Never touches production data."""
    values: dict[str, object] = {
        "firestore_emulator_host": os.environ["FIRESTORE_EMULATOR_HOST"],
        "firebase_project_id": "fix-it-proper-test",
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def offline_settings(**overrides):
    """Settings with every Firebase field blanked, so the db stays disabled."""
    values: dict[str, object] = {
        "firebase_project_id": "",
        "firebase_credentials_path": "",
        "firebase_credentials_base64": "",
        "firestore_emulator_host": "",
        "firebase_auth_emulator_host": "",
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]
