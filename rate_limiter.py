
import ipaddress
import logging
import os
import time

from fastapi import HTTPException, Request
from upstash_ratelimit.asyncio import Ratelimit, SlidingWindow
from upstash_redis.asyncio import Redis

from config import (
    UPSTASH_REDIS_REST_URL,
    UPSTASH_REDIS_REST_TOKEN,
    RATE_LIMIT_STATUS,
    RATE_LIMIT_CREATE,
    RATE_LIMIT_DELETE,
    RATE_LIMIT_CHECKS,
)


logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60
rate_limiters = {}

credentials_configured = bool(
    UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN
)

# Never silently disable rate limiting on Vercel.
if os.getenv("VERCEL") == "1" and not credentials_configured:
    raise RuntimeError(
        "Upstash credentials are required for Vercel deployments"
    )

if credentials_configured:
    redis = Redis.from_env()

    limits = {
        "status": RATE_LIMIT_STATUS,
        "create": RATE_LIMIT_CREATE,
        "delete": RATE_LIMIT_DELETE,
        "checks": RATE_LIMIT_CHECKS,
    }

    for name, max_requests in limits.items():
        rate_limiters[name] = Ratelimit(
            redis=redis,
            limiter=SlidingWindow(
                max_requests=max_requests,
                window=WINDOW_SECONDS,
            ),
            prefix=f"api-pulse:{name}",
        )


def get_client_identifier(request: Request) -> str:
    # Vercel overwrites this header with the visitor's public IP.
    if os.getenv("VERCEL") == "1":
        forwarded_for = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded_for.split(",")[0].strip()

        try:
            return str(ipaddress.ip_address(client_ip))
        except ValueError:
            return "unknown"

    # Local development.
    client = request.client
    return client.host if client else "unknown"


async def check_rate_limit(request: Request, limit_name: str):
    limiter = rate_limiters.get(limit_name)

    # Allow local development and tests without Redis.
    if limiter is None:
        return

    identifier = get_client_identifier(request)

    try:
        response = await limiter.limit(identifier)
    except Exception:
        logger.exception("Rate limiter service unavailable")
        raise HTTPException(
            status_code=503,
            detail="Rate limiting service temporarily unavailable",
        )

    if not response.allowed:
        retry_after = max(
            1,
            int(response.reset - time.time()),
        )

        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
