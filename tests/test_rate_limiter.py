
import asyncio
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from rate_limiter import check_rate_limit, rate_limiters


class FakeLimiter:
    def __init__(self, allowed):
        self.allowed = allowed

    async def limit(self, identifier):
        self.identifier = identifier
        return SimpleNamespace(
            allowed=self.allowed,
            reset=time.time() + 10,
        )


def create_request():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/status",
        "headers": [],
        "query_string": b"",
        "client": ("203.0.113.10", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_rate_limit_allows_request(monkeypatch):
    limiter = FakeLimiter(allowed=True)
    monkeypatch.setitem(rate_limiters, "status", limiter)

    asyncio.run(check_rate_limit(create_request(), "status"))

    assert limiter.identifier == "203.0.113.10"


def test_rate_limit_blocks_excess_request(monkeypatch):
    limiter = FakeLimiter(allowed=False)
    monkeypatch.setitem(rate_limiters, "status", limiter)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(check_rate_limit(create_request(), "status"))

    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


def test_rate_limit_disabled_without_limiter(monkeypatch):
    monkeypatch.delitem(rate_limiters, "status", raising=False)

    # No limiter configured: request is allowed.
    asyncio.run(check_rate_limit(create_request(), "status"))

def test_vercel_uses_forwarded_ip(monkeypatch):
    from rate_limiter import get_client_identifier

    monkeypatch.setenv("VERCEL", "1")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (b"x-forwarded-for", b"203.0.113.20, 10.0.0.1")
        ],
        "client": ("127.0.0.1", 1234),
    }

    request = Request(scope)

    assert get_client_identifier(request) == "203.0.113.20"


def test_vercel_rejects_invalid_forwarded_ip(monkeypatch):
    from rate_limiter import get_client_identifier

    monkeypatch.setenv("VERCEL", "1")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (b"x-forwarded-for", b"invalid-ip")
        ],
        "client": ("127.0.0.1", 1234),
    }

    request = Request(scope)

    assert get_client_identifier(request) == "unknown"