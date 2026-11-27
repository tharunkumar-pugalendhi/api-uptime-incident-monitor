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

## API Rate Limiting

API Pulse uses **Upstash Redis** to enforce per-IP rate limits with a sliding 60-second window.

| Endpoint | Default limit |
|---|---:|
| `GET /api/status` | 60 requests/minute |
| `POST /api/endpoints` | 10 requests/minute |
| `DELETE /api/endpoints/{endpoint_id}` | 10 requests/minute |
| `POST /api/checks/run` | 5 requests/minute |

### Redis Configuration

Set these environment variables in your local `.env` file and your deployment environment:

```ini
UPSTASH_REDIS_REST_URL=your_upstash_redis_rest_url
UPSTASH_REDIS_REST_TOKEN=your_upstash_redis_rest_token
```

You can optionally customize the limits:

```ini
RATE_LIMIT_STATUS=60
RATE_LIMIT_CREATE=10
RATE_LIMIT_DELETE=10
RATE_LIMIT_CHECKS=5
```

- Requests exceeding a limit receive HTTP `429 Too Many Requests`, with a `Retry-After` header.
- If Redis is unavailable, rate-limited requests receive HTTP `503 Service Unavailable`.
- Local development and tests can run without Redis credentials.
- Both Upstash credentials are required for Vercel deployments.

**Security:** Never commit your `.env` file or expose your Redis credentials.