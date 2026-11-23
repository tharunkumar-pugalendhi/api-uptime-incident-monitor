import sqlite3
from datetime import datetime, timezone

DB_PATH = "uptime_monitor.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            sla_ms INTEGER NOT NULL DEFAULT 800,
            current_status TEXT NOT NULL DEFAULT 'PENDING',
            last_status_code INTEGER,
            last_latency_ms REAL,
            last_checked_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS check_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            status_code INTEGER,
            latency_ms REAL,
            checked_at TEXT NOT NULL,
            FOREIGN KEY (endpoint_id) REFERENCES endpoints(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint_id INTEGER NOT NULL,
            endpoint_name TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            opened_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY (endpoint_id) REFERENCES endpoints(id) ON DELETE CASCADE
        )
    """)

    cur.execute("SELECT COUNT(*) FROM endpoints")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO endpoints (name, url, sla_ms) VALUES (?, ?, ?)",
            [
                ("GitHub Public API", "https://api.github.com", 800),
                ("JSONPlaceholder Mock API", "https://jsonplaceholder.typicode.com/posts/1", 600),
            ],
        )

    conn.commit()
    conn.close()

def fetch_dashboard_data():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            e.*,
            COUNT(c.id) AS total_checks,
            SUM(CASE WHEN c.status IN ('HEALTHY', 'DEGRADED') THEN 1 ELSE 0 END) AS up_checks
        FROM endpoints e
        LEFT JOIN check_logs c ON e.id = c.endpoint_id
        GROUP BY e.id
        ORDER BY e.id DESC
    """)
    endpoints = []
    for row in cur.fetchall():
        item = dict(row)
        total = item["total_checks"] or 0
        up = item["up_checks"] or 0
        item["uptime_pct"] = round((up / total) * 100, 1) if total > 0 else 100.0
        endpoints.append(item)

    cur.execute("SELECT * FROM incidents ORDER BY id DESC LIMIT 15")
    incidents = [dict(r) for r in cur.fetchall()]

    conn.close()
    return endpoints, incidents

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
