import sqlite3
import database

def test_now_utc_returns_valid_timestamp():
    result = database.now_utc()

    assert result.endswith(" UTC")
    assert len(result) == 23


def test_init_db_creates_tables_and_default_endpoints(tmp_path, monkeypatch):
    # Use a temporary database instead of the real one
    db_path = tmp_path / "test.db"

    monkeypatch.setattr(database, "DB_PATH", str(db_path))

    # Initialize database
    database.init_db()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check tables
    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()

    table_names = [table[0] for table in tables]

    assert "endpoints" in table_names
    assert "check_logs" in table_names
    assert "incidents" in table_names

    # Check default endpoints
    endpoints = cur.execute(
        "SELECT COUNT(*) FROM endpoints"
    ).fetchone()[0]

    assert endpoints == 2

    conn.close()

def test_fetch_dashboard_data_calculates_uptime(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))

    database.init_db()

    conn = database.get_conn()
    cur = conn.cursor()

    # Get the first default endpoint
    endpoint_id = cur.execute(
        "SELECT id FROM endpoints LIMIT 1"
    ).fetchone()["id"]

    # Insert 2 successful checks and 1 failed check
    cur.executemany(
        """
        INSERT INTO check_logs
        (endpoint_id, status, status_code, latency_ms, checked_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (endpoint_id, "HEALTHY", 200, 100, "2026-11-25 10:00:00 UTC"),
            (endpoint_id, "HEALTHY", 200, 120, "2026-11-25 10:01:00 UTC"),
            (endpoint_id, "DOWN", 500, 200, "2026-11-25 10:02:00 UTC"),
        ],
    )

    conn.commit()
    conn.close()

    endpoints, incidents = database.fetch_dashboard_data()

    endpoint = next(e for e in endpoints if e["id"] == endpoint_id)

    assert endpoint["total_checks"] == 3
    assert endpoint["up_checks"] == 2
    assert endpoint["uptime_pct"] == 66.7
    assert incidents == []

def test_dashboard_returns_100_percent_when_no_checks_exist(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "empty.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))

    database.init_db()

    endpoints, incidents = database.fetch_dashboard_data()

    assert len(endpoints) == 2

    for endpoint in endpoints:
        assert endpoint["uptime_pct"] == 100.0
        assert endpoint["total_checks"] == 0

    assert incidents == []

def test_dashboard_returns_incidents(tmp_path, monkeypatch):
    db_path = tmp_path / "incidents.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))

    database.init_db()

    conn = database.get_conn()

    endpoint = conn.execute(
        "SELECT id, name FROM endpoints LIMIT 1"
    ).fetchone()

    conn.execute(
        """
        INSERT INTO incidents
        (endpoint_id, endpoint_name, reason, status, opened_at)
        VALUES (?, ?, ?, 'OPEN', ?)
        """,
        (
            endpoint["id"],
            endpoint["name"],
            "Unexpected HTTP 500",
            "2026-11-25 10:00:00 UTC",
        ),
    )

    conn.commit()
    conn.close()

    endpoints, incidents = database.fetch_dashboard_data()

    assert len(incidents) == 1
    assert incidents[0]["status"] == "OPEN"
    assert incidents[0]["reason"] == "Unexpected HTTP 500"

def test_init_db_does_not_duplicate_default_endpoints(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "repeat.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))

    database.init_db()
    database.init_db()

    conn = database.get_conn()

    count = conn.execute(
        "SELECT COUNT(*) FROM endpoints"
    ).fetchone()[0]

    conn.close()

    assert count == 2