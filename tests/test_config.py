
import importlib
import pytest
import config


def test_default_configuration(monkeypatch):
    monkeypatch.delenv("MONITOR_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("HTTP_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)

    settings = importlib.reload(config)

    assert settings.MONITOR_INTERVAL_SECONDS == 60
    assert settings.HTTP_TIMEOUT_SECONDS == 8.0
    assert settings.DATABASE_PATH == "uptime_monitor.db"


def test_custom_configuration(monkeypatch):
    monkeypatch.setenv("MONITOR_INTERVAL_SECONDS", "30")
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "5.5")
    monkeypatch.setenv("DATABASE_PATH", "custom.db")

    settings = importlib.reload(config)

    assert settings.MONITOR_INTERVAL_SECONDS == 30
    assert settings.HTTP_TIMEOUT_SECONDS == 5.5
    assert settings.DATABASE_PATH == "custom.db"


@pytest.mark.parametrize(
    "variable,value",
    [
        ("MONITOR_INTERVAL_SECONDS", "invalid"),
        ("MONITOR_INTERVAL_SECONDS", "0"),
        ("HTTP_TIMEOUT_SECONDS", "invalid"),
        ("HTTP_TIMEOUT_SECONDS", "-1"),
        ("DATABASE_PATH", "   "),
    ],
)
def test_invalid_configuration(variable, value, monkeypatch):
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValueError):
        importlib.reload(config)
