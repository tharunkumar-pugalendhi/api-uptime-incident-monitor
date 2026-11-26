# API Pulse — Real-Time API Uptime & Incident Monitor

A modular backend service built with **Python, FastAPI, Async HTTPX, and SQLite** that continuously monitors external REST APIs, tracks SLA response latency, and automatically opens/resolves outage incidents.

## Architecture & Technical Highlights

- **Asynchronous Health Checks (`httpx.AsyncClient`):** Measures exact round-trip latency (`time.perf_counter()`) and grades endpoints as `HEALTHY`, `DEGRADED` (SLA breach), or `DOWN`.
- **Background Scheduler (`asyncio` + FastAPI `lifespan`):** Runs automated checks every 60 seconds alongside on-demand manual triggers.
- **Automated Incident Lifecycle:** Opens a single incident ticket on failure (avoiding alert fatigue/duplicates) and auto-resolves it once the endpoint recovers.
- **Relational SQLite Aggregation:** Computes live uptime percentages across historical check logs using SQL `LEFT JOIN` and conditional `SUM(CASE WHEN ...)`.

## Configuration

API Pulse supports environment-based configuration using a `.env` file.

### Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`.

3. Update the values in `.env` if required.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MONITOR_INTERVAL_SECONDS` | `60` | Time between automated monitoring cycles |
| `HTTP_TIMEOUT_SECONDS` | `8.0` | Maximum HTTP request timeout |
| `DATABASE_PATH` | `uptime_monitor.db` | SQLite database file location |

Example:

```ini
MONITOR_INTERVAL_SECONDS=30
HTTP_TIMEOUT_SECONDS=5.0
DATABASE_PATH=uptime_monitor.db
```

The application validates configuration values during startup. Invalid values raise a clear configuration error.