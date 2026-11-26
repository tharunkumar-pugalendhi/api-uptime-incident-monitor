
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
