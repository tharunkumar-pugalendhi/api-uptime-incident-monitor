import sqlite3
from types import SimpleNamespace

import pytest
import monitor


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"

    def fake_get_conn():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(monitor, "get_conn", fake_get_conn)

    conn = fake_get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE endpoints (
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
        CREATE TABLE check_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            status_code INTEGER,
            latency_ms REAL,
            checked_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint_id INTEGER NOT NULL,
            endpoint_name TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            opened_at TEXT NOT NULL,
            resolved_at TEXT
        )
    """)

    cur.execute(
        "INSERT INTO endpoints (name, url, sla_ms) VALUES (?, ?, ?)",
        ("Test API", "https://example.com", 800),
    )

    conn.commit()
    conn.close()

    return db_path


@pytest.mark.anyio
async def test_server_error_creates_incident(test_db, monkeypatch):

    # Simulate an HTTP 500 response without making a real request
    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=500)

    monkeypatch.setattr(
        monitor.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(),
    )

    result = await monitor.check_single_endpoint(1)

    assert result["status"] == "DOWN"
    assert result["status_code"] == 500

    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row

    # Check historical log
    log = conn.execute(
        "SELECT * FROM check_logs WHERE endpoint_id = 1"
    ).fetchone()

    assert log["status"] == "DOWN"
    assert log["status_code"] == 500

    # Check endpoint's current status
    endpoint = conn.execute(
        "SELECT * FROM endpoints WHERE id = 1"
    ).fetchone()

    assert endpoint["current_status"] == "DOWN"

    # Check incident creation
    incident = conn.execute(
        "SELECT * FROM incidents WHERE endpoint_id = 1"
    ).fetchone()

    assert incident["status"] == "OPEN"
    assert incident["reason"] == "Unexpected HTTP 500"

    conn.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.mark.anyio
async def test_timeout_marks_endpoint_down(test_db, monkeypatch):

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args, **kwargs):
            raise monitor.httpx.TimeoutException("Request timed out")

    monkeypatch.setattr(
        monitor.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(),
    )

    result = await monitor.check_single_endpoint(1)

    assert result["status"] == "DOWN"
    assert result["status_code"] is None

    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row

    log = conn.execute(
        "SELECT * FROM check_logs WHERE endpoint_id = 1"
    ).fetchone()

    assert log["status"] == "DOWN"
    assert log["status_code"] is None

    incident = conn.execute(
        "SELECT * FROM incidents WHERE endpoint_id = 1"
    ).fetchone()

    assert incident["status"] == "OPEN"
    assert incident["reason"] == "Request timed out (>8000ms)"

    conn.close()

@pytest.mark.anyio
async def test_successful_response_marks_endpoint_healthy(test_db, monkeypatch):

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=200)

    monkeypatch.setattr(
        monitor.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(),
    )

    result = await monitor.check_single_endpoint(1)

    assert result["status"] == "HEALTHY"
    assert result["status_code"] == 200

    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row

    endpoint = conn.execute(
        "SELECT * FROM endpoints WHERE id = 1"
    ).fetchone()

    assert endpoint["current_status"] == "HEALTHY"

    log = conn.execute(
        "SELECT * FROM check_logs WHERE endpoint_id = 1"
    ).fetchone()

    assert log["status"] == "HEALTHY"
    assert log["status_code"] == 200

    incident = conn.execute(
        "SELECT * FROM incidents WHERE endpoint_id = 1"
    ).fetchone()

    assert incident is None

    conn.close()    

@pytest.mark.anyio
async def test_recovery_resolves_open_incident(test_db, monkeypatch):

    # First, create an existing OPEN incident
    conn = sqlite3.connect(test_db)

    conn.execute(
        """
        INSERT INTO incidents
        (endpoint_id, endpoint_name, reason, status, opened_at)
        VALUES (?, ?, ?, 'OPEN', ?)
        """,
        (1, "Test API", "Unexpected HTTP 500", "2026-11-25 10:00:00 UTC"),
    )

    conn.commit()
    conn.close()

    # Simulate API recovery with HTTP 200
    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=200)

    monkeypatch.setattr(
        monitor.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(),
    )

    result = await monitor.check_single_endpoint(1)

    assert result["status"] == "HEALTHY"

    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row

    incident = conn.execute(
        "SELECT * FROM incidents WHERE endpoint_id = 1"
    ).fetchone()

    assert incident["status"] == "RESOLVED"
    assert incident["resolved_at"] is not None

    conn.close()

@pytest.mark.anyio
async def test_repeated_failure_does_not_create_duplicate_incidents(
    test_db, monkeypatch
):
    conn = sqlite3.connect(test_db)

    conn.execute(
        """
        INSERT INTO incidents
        (endpoint_id, endpoint_name, reason, status, opened_at)
        VALUES (1, 'Test API', 'Previous failure', 'OPEN', '2026-11-25 10:00:00 UTC')
        """
    )

    conn.commit()
    conn.close()

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=500)

    monkeypatch.setattr(
        monitor.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(),
    )

    result = await monitor.check_single_endpoint(1)

    assert result["status"] == "DOWN"

    conn = sqlite3.connect(test_db)

    count = conn.execute(
        "SELECT COUNT(*) FROM incidents WHERE endpoint_id = 1 AND status = 'OPEN'"
    ).fetchone()[0]

    conn.close()

    assert count == 1   

@pytest.mark.anyio
async def test_slow_response_marks_endpoint_degraded(
    test_db, monkeypatch
):
    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=200)

    monkeypatch.setattr(
        monitor.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(),
    )

    # Simulate an elapsed time of exactly 900 milliseconds
    timestamps = iter([0.0, 0.9])
    monkeypatch.setattr(
        monitor.time,
        "perf_counter",
        lambda: next(timestamps),
    )

    result = await monitor.check_single_endpoint(1)

    assert result["status"] == "DEGRADED"
    assert result["latency_ms"] == 900.0
    assert result["status_code"] == 200

    conn = sqlite3.connect(test_db)

    status = conn.execute(
        "SELECT current_status FROM endpoints WHERE id = 1"
    ).fetchone()[0]

    conn.close()

    assert status == "DEGRADED"

@pytest.mark.anyio
async def test_nonexistent_endpoint_returns_none(test_db):

    result = await monitor.check_single_endpoint(999)

    assert result is None

    conn = sqlite3.connect(test_db)

    log_count = conn.execute(
        "SELECT COUNT(*) FROM check_logs"
    ).fetchone()[0]

    incident_count = conn.execute(
        "SELECT COUNT(*) FROM incidents"
    ).fetchone()[0]

    conn.close()

    assert log_count == 0
    assert incident_count == 0


@pytest.mark.anyio
async def test_connection_error_is_recorded_as_down(test_db, monkeypatch):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, *args, **kwargs):
            raise monitor.httpx.ConnectError("Connection refused")

    monkeypatch.setattr(
        monitor.httpx, "AsyncClient", FakeAsyncClient
    )

    result = await monitor.check_single_endpoint(1)

    assert result["status"] == "DOWN"

    conn = sqlite3.connect(test_db)
    incident = conn.execute(
        "SELECT reason FROM incidents WHERE endpoint_id = 1"
    ).fetchone()
    conn.close()

    assert incident[0] == "Connection error: ConnectError"


@pytest.mark.anyio
async def test_check_all_continues_after_one_endpoint_fails(
    test_db, monkeypatch
):
    conn = sqlite3.connect(test_db)
    conn.execute(
        "INSERT INTO endpoints (name, url, sla_ms) VALUES (?, ?, ?)",
        ("Second API", "https://example.org", 800)
    )
    conn.commit()
    conn.close()

    async def fake_check_single(endpoint_id):
        if endpoint_id == 1:
            raise RuntimeError("Simulated database failure")

        return {"id": endpoint_id, "status": "HEALTHY"}

    monkeypatch.setattr(
        monitor, "check_single_endpoint", fake_check_single
    )

    results = await monitor.check_all_endpoints()

    assert results == [
        {"id": 1, "status": "ERROR", "error": "RuntimeError"},
        {"id": 2, "status": "HEALTHY"}
    ]


@pytest.mark.anyio
async def test_database_write_failure_rolls_back(
    test_db, monkeypatch
):
    conn = sqlite3.connect(test_db)
    conn.execute("""
        CREATE TRIGGER reject_check_log
        BEFORE INSERT ON check_logs
        BEGIN
            SELECT RAISE(ABORT, 'Simulated database failure');
        END;
    """)
    conn.commit()
    conn.close()

    class FakeResponse:
        status_code = 200

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, *args, **kwargs):
            raise monitor.httpx.ConnectError("Connection refused")

    monkeypatch.setattr(
        monitor.httpx, "AsyncClient", FakeAsyncClient
    )

    with pytest.raises(sqlite3.IntegrityError):
        await monitor.check_single_endpoint(1)

    conn = sqlite3.connect(test_db)

    log_count = conn.execute(
        "SELECT COUNT(*) FROM check_logs"
    ).fetchone()[0]

    endpoint_status = conn.execute(
        "SELECT current_status FROM endpoints WHERE id = 1"
    ).fetchone()[0]

    conn.close()

    assert log_count == 0
    assert endpoint_status == "PENDING"
