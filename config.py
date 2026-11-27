
import os
from dotenv import load_dotenv

# Load values from the local .env file
load_dotenv()


def get_positive_int(name, default):
    value = os.getenv(name, str(default))

    try:
        result = int(value)
    except ValueError:
        raise ValueError(f"{name} must be a valid integer")

    if result <= 0:
        raise ValueError(f"{name} must be greater than zero")

    return result


def get_positive_float(name, default):
    value = os.getenv(name, str(default))

    try:
        result = float(value)
    except ValueError:
        raise ValueError(f"{name} must be a valid number")

    if result <= 0:
        raise ValueError(f"{name} must be greater than zero")

    return result


MONITOR_INTERVAL_SECONDS = get_positive_int(
    "MONITOR_INTERVAL_SECONDS", 60
)

HTTP_TIMEOUT_SECONDS = get_positive_float(
    "HTTP_TIMEOUT_SECONDS", 8.0
)

DATABASE_PATH = os.getenv(
    "DATABASE_PATH", "uptime_monitor.db"
).strip()

if not DATABASE_PATH:
    raise ValueError("DATABASE_PATH cannot be empty")

# Upstash Redis configuration
UPSTASH_REDIS_REST_URL = os.getenv(
    "UPSTASH_REDIS_REST_URL", ""
).strip()

UPSTASH_REDIS_REST_TOKEN = os.getenv(
    "UPSTASH_REDIS_REST_TOKEN", ""
).strip()

if bool(UPSTASH_REDIS_REST_URL) != bool(UPSTASH_REDIS_REST_TOKEN):
    raise ValueError(
        "Both UPSTASH_REDIS_REST_URL and "
        "UPSTASH_REDIS_REST_TOKEN must be configured"
    )


# API rate limits (requests per minute)
RATE_LIMIT_STATUS = get_positive_int("RATE_LIMIT_STATUS", 60)
RATE_LIMIT_CREATE = get_positive_int("RATE_LIMIT_CREATE", 10)
RATE_LIMIT_DELETE = get_positive_int("RATE_LIMIT_DELETE", 10)
RATE_LIMIT_CHECKS = get_positive_int("RATE_LIMIT_CHECKS", 5)