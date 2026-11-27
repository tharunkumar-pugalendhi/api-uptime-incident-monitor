import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, HttpUrl, Field
from database import init_db, get_conn, fetch_dashboard_data
from monitor import check_all_endpoints, check_single_endpoint
import logging
from config import MONITOR_INTERVAL_SECONDS
from rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)

async def background_monitor_loop():
    while True:
        try:
            await check_all_endpoints()
        except asyncio.CancelledError:
            logger.info("Background monitoring task cancelled")
            raise
        except Exception:
            logger.exception("Background monitoring cycle failed")

        await asyncio.sleep(MONITOR_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized")

    task = asyncio.create_task(background_monitor_loop())

    try:
        yield
    finally:
        logger.info("Stopping background monitoring task")
        task.cancel()

        with suppress(asyncio.CancelledError):
            await task

        logger.info("Background monitoring task stopped")


app = FastAPI(title="API Pulse — Real-Time Uptime & Incident Monitor", lifespan=lifespan)

class EndpointCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=60)
    url: HttpUrl
    sla_ms: int = Field(default=800, ge=50, le=10000)

@app.get("/api/status")
async def get_status(request: Request):
    await check_rate_limit(request, "status")
    endpoints, incidents = fetch_dashboard_data()
    return {"endpoints": endpoints, "incidents": incidents}

@app.post("/api/endpoints", status_code=201)
async def create_endpoint(payload: EndpointCreate, request: Request):
    await check_rate_limit(request, "create")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO endpoints (name, url, sla_ms) VALUES (?, ?, ?)",
        (payload.name.strip(), str(payload.url), payload.sla_ms),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    await check_single_endpoint(new_id)
    return {"id": new_id, "message": "Endpoint added and checked"}

@app.delete("/api/endpoints/{endpoint_id}")
async def delete_endpoint(endpoint_id: int, request: Request):
    await check_rate_limit(request, "delete")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM endpoints WHERE id = ?", (endpoint_id,))
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Endpoint not found")
    conn.commit()
    conn.close()
    return {"deleted": endpoint_id}

@app.post("/api/checks/run")
async def trigger_checks(request: Request):
    await check_rate_limit(request, "checks")
    results = await check_all_endpoints()
    return {"checked": len(results), "results": results}

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>API Pulse — Uptime & Incident Monitor</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 24px; }
    .container { max-width: 1050px; margin: auto; }
    h1 { margin: 0 0 6px; font-size: 24px; color: #38bdf8; }
    .sub { color: #94a3b8; font-size: 14px; margin-bottom: 20px; }
    .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
    .card { background: #1e293b; padding: 14px; border-radius: 8px; border: 1px solid #334155; }
    .card h3 { margin: 0; font-size: 12px; color: #94a3b8; text-transform: uppercase; }
    .card p { margin: 6px 0 0; font-size: 24px; font-weight: bold; }
    .form-bar { display: flex; gap: 10px; background: #1e293b; padding: 14px; border-radius: 8px; margin-bottom: 20px; flex-wrap: wrap; }
    input { background: #0f172a; border: 1px solid #334155; color: #fff; padding: 8px 12px; border-radius: 6px; flex: 1; min-width: 160px; }
    button { background: #0284c7; color: #fff; border: none; padding: 9px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }
    button:hover { background: #0369a1; }
    .btn-sec { background: #334155; }
    .btn-del { background: #7f1d1d; padding: 4px 10px; font-size: 12px; }
    table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; margin-bottom: 24px; }
    th, td { padding: 12px; text-align: left; border-bottom: 1px solid #334155; font-size: 14px; }
    th { background: #0f172a; color: #94a3b8; font-size: 12px; text-transform: uppercase; }
    .badge { padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
    .HEALTHY, .RESOLVED { background: #065f46; color: #6ee7b7; }
    .DEGRADED { background: #78350f; color: #fcd34d; }
    .DOWN, .OPEN { background: #7f1d1d; color: #fca5a5; }
    .PENDING { background: #334155; color: #cbd5e1; }
  </style>
</head>
<body>
<div class="container">
  <h1>API Pulse — Real-Time Uptime & Incident Monitor</h1>
  <div class="sub">Automated HTTP health checks, SLA latency tracking, and auto-resolving incident engine (Python + FastAPI + SQLite)</div>

  <div class="cards">
    <div class="card"><h3>Monitored APIs</h3><p id="c-total">0</p></div>
    <div class="card"><h3>Healthy</h3><p id="c-healthy" style="color:#34d399">0</p></div>
    <div class="card"><h3>Degraded / Down</h3><p id="c-down" style="color:#f87171">0</p></div>
    <div class="card"><h3>Open Incidents</h3><p id="c-inc" style="color:#fbbf24">0</p></div>
  </div>

  <div class="form-bar">
    <input id="ep-name" placeholder="Service Name (e.g. Partner CKYC API)" />
    <input id="ep-url" placeholder="https://api.example.com/health" />
    <input id="ep-sla" type="number" value="800" placeholder="SLA (ms)" style="max-width:110px" />
    <button onclick="addEndpoint()">+ Add API</button>
    <button class="btn-sec" onclick="runChecks()">Run Check Now</button>
  </div>

  <table>
    <thead>
      <tr><th>Service</th><th>URL</th><th>Status</th><th>HTTP</th><th>Latency / SLA</th><th>Uptime</th><th>Last Checked</th><th>Action</th></tr>
    </thead>
    <tbody id="ep-body"></tbody>
  </table>

  <h2 style="font-size:18px; margin-bottom:10px;">Automated Incident Log</h2>
  <table>
    <thead>
      <tr><th>ID</th><th>Service</th><th>Trigger Reason</th><th>State</th><th>Opened At</th><th>Resolved At</th></tr>
    </thead>
    <tbody id="inc-body"></tbody>
  </table>
</div>

<script>
async function loadData() {
  const res = await fetch('/api/status');
  const data = await res.json();
  const eps = data.endpoints;
  const incs = data.incidents;

  document.getElementById('c-total').innerText = eps.length;
  document.getElementById('c-healthy').innerText = eps.filter(e => e.current_status === 'HEALTHY').length;
  document.getElementById('c-down').innerText = eps.filter(e => e.current_status !== 'HEALTHY').length;
  document.getElementById('c-inc').innerText = incs.filter(i => i.status === 'OPEN').length;

  document.getElementById('ep-body').innerHTML = eps.map(e => `
    <tr>
      <td><strong>${e.name}</strong></td>
      <td style="color:#94a3b8">${e.url}</td>
      <td><span class="badge ${e.current_status}">${e.current_status}</span></td>
      <td>${e.last_status_code ?? '-'}</td>
      <td>${e.last_latency_ms ? e.last_latency_ms + ' ms' : '-'} / ${e.sla_ms} ms</td>
      <td>${e.uptime_pct}%</td>
      <td style="color:#94a3b8">${e.last_checked_at ?? 'Pending'}</td>
      <td><button class="btn-del" onclick="delEndpoint(${e.id})">Delete</button></td>
    </tr>
  `).join('');

  document.getElementById('inc-body').innerHTML = incs.length ? incs.map(i => `
    <tr>
      <td>#${i.id}</td>
      <td>${i.endpoint_name}</td>
      <td>${i.reason}</td>
      <td><span class="badge ${i.status}">${i.status}</span></td>
      <td>${i.opened_at}</td>
      <td>${i.resolved_at ?? 'Active'}</td>
    </tr>
  `).join('') : '<tr><td colspan="6" style="color:#94a3b8">No incidents recorded yet. Try adding an invalid URL (e.g. https://httpbin.org/status/503) to test auto-incident creation!</td></tr>';
}

async function addEndpoint() {
  const name = document.getElementById('ep-name').value;
  const url = document.getElementById('ep-url').value;
  const sla_ms = parseInt(document.getElementById('ep-sla').value || '800');
  if (!name || !url) return alert('Enter both Service Name and URL');
  const res = await fetch('/api/endpoints', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, url, sla_ms})
  });
  if (!res.ok) return alert('Invalid URL format (must start with http:// or https://)');
  document.getElementById('ep-name').value = '';
  document.getElementById('ep-url').value = '';
  loadData();
}

async function delEndpoint(id) {
  await fetch('/api/endpoints/' + id, {method: 'DELETE'});
  loadData();
}

async function runChecks() {
  await fetch('/api/checks/run', {method: 'POST'});
  loadData();
}

loadData();
setInterval(loadData, 15000);
</script>
</body>
</html>
"""