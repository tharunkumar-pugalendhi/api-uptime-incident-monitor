import sqlite3
import asyncio
import pytest
import main
from fastapi.testclient import TestClient


def test_create_endpoint(monkeypatch, tmp_path):

    # Create a separate temporary database for testing
    db_path = tmp_path / "test.db"

    def fake_get_conn():
        return sqlite3.connect(db_path)

    monkeypatch.setattr(main, "get_conn", fake_get_conn)

    # Create the minimum table needed for this test
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            sla_ms INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

    # Prevent an actual external API request
    async def fake_check_endpoint(endpoint_id):
        pass

    monkeypatch.setattr(
        main,
        "check_single_endpoint",
        fake_check_endpoint
    )

    client = TestClient(main.app)

    response = client.post(
        "/api/endpoints",
        json={
            "name": "GitHub API",
            "url": "https://api.github.com",
            "sla_ms": 800
        }
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Endpoint added and checked"

    # Verify that the endpoint was actually saved
    conn = sqlite3.connect(db_path)
    result = conn.execute(
        "SELECT name, url, sla_ms FROM endpoints"
    ).fetchone()
    conn.close()

    assert result == ("GitHub API", "https://api.github.com/", 800)


def test_create_endpoint_rejects_invalid_url():
    client = TestClient(main.app)

    response = client.post(
        "/api/endpoints",
        json={
            "name": "Test API",
            "url": "ftp://example.com",
            "sla_ms": 800
        }
    )

    assert response.status_code == 422


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_get_status_returns_dashboard_data(monkeypatch):
    fake_endpoints = [{"id": 1, "name": "Test API"}]
    fake_incidents = [{"id": 1, "status": "OPEN"}]

    monkeypatch.setattr(
        main,
        "fetch_dashboard_data",
        lambda: (fake_endpoints, fake_incidents)
    )

    client = TestClient(main.app)
    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json() == {
        "endpoints": fake_endpoints,
        "incidents": fake_incidents
    }


def test_delete_endpoint_success(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "delete_test.db"

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE endpoints (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
    """)
    conn.execute(
        "INSERT INTO endpoints (id, name) VALUES (1, 'Test API')"
    )
    conn.commit()
    conn.close()

    def fake_get_conn():
        connection = sqlite3.connect(db_path)
        return connection

    monkeypatch.setattr(main, "get_conn", fake_get_conn)

    client = TestClient(main.app)
    response = client.delete("/api/endpoints/1")

    assert response.status_code == 200
    assert response.json() == {"deleted": 1}

    conn = sqlite3.connect(db_path)
    remaining = conn.execute(
        "SELECT COUNT(*) FROM endpoints"
    ).fetchone()[0]
    conn.close()

    assert remaining == 0


def test_delete_endpoint_not_found(monkeypatch):
    import sqlite3

    def fake_get_conn():
        conn = sqlite3.connect(
            ":memory:",
            check_same_thread=False
        )
        conn.execute("""
            CREATE TABLE endpoints (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        """)
        return conn

    monkeypatch.setattr(main, "get_conn", fake_get_conn)

    client = TestClient(main.app)
    response = client.delete("/api/endpoints/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Endpoint not found"


def test_trigger_checks_returns_results(monkeypatch):
    expected_results = [
        {"id": 1, "status": "HEALTHY"},
        {"id": 2, "status": "DOWN"}
    ]

    async def fake_check_all():
        return expected_results

    monkeypatch.setattr(
        main,
        "check_all_endpoints",
        fake_check_all
    )

    client = TestClient(main.app)
    response = client.post("/api/checks/run")

    assert response.status_code == 200
    assert response.json() == {
        "checked": 2,
        "results": expected_results
    }


def test_dashboard_returns_html():
    client = TestClient(main.app)
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "API Pulse" in response.text
    assert "Automated Incident Log" in response.text


@pytest.mark.anyio
async def test_lifespan_initializes_and_cancels_background_task(monkeypatch):
    init_called = []
    cancel_called = []

    class FakeTask:
        def cancel(self):
            cancel_called.append(True)

    monkeypatch.setattr(
        main,
        "init_db",
        lambda: init_called.append(True)
    )
    monkeypatch.setattr(
        main.asyncio,
        "create_task",
        lambda coroutine: (
            coroutine.close(),
            FakeTask()
        )[1]
    )

    async with main.lifespan(main.app):
        assert init_called == [True]
        assert cancel_called == []

    assert cancel_called == [True]


@pytest.mark.anyio
async def test_background_monitor_loop_handles_errors(monkeypatch):
    check_called = []

    async def fake_check_all():
        check_called.append(True)
        raise RuntimeError("Simulated monitoring error")

    async def fake_sleep(seconds):
        assert seconds == 60
        raise asyncio.CancelledError()

    monkeypatch.setattr(
        main,
        "check_all_endpoints",
        fake_check_all
    )
    monkeypatch.setattr(
        main.asyncio,
        "sleep",
        fake_sleep
    )

    with pytest.raises(asyncio.CancelledError):
        await main.background_monitor_loop()

    assert check_called == [True]
