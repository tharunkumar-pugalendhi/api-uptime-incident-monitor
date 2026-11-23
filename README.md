# API Pulse — Real-Time API Uptime & Incident Monitor

A modular backend service built with **Python, FastAPI, Async HTTPX, and SQLite** that continuously monitors external REST APIs, tracks SLA response latency, and automatically opens/resolves outage incidents.

## Architecture & Technical Highlights

- **Asynchronous Health Checks (`httpx.AsyncClient`):** Measures exact round-trip latency (`time.perf_counter()`) and grades endpoints as `HEALTHY`, `DEGRADED` (SLA breach), or `DOWN`.
- **Background Scheduler (`asyncio` + FastAPI `lifespan`):** Runs automated checks every 60 seconds alongside on-demand manual triggers.
- **Automated Incident Lifecycle:** Opens a single incident ticket on failure (avoiding alert fatigue/duplicates) and auto-resolves it once the endpoint recovers.
- **Relational SQLite Aggregation:** Computes live uptime percentages across historical check logs using SQL `LEFT JOIN` and conditional `SUM(CASE WHEN ...)`.
