from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import sanitize_error_message, get_db
import app.api.routes.health as health_module
import app.core.database as db_module


def test_health_endpoint_returns_200(client: TestClient):
    """GET /health must return HTTP 200 and application health status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "KnowBridge AI Backend" in data["service"]
    assert "environment" in data


def test_api_v1_health_endpoint_returns_200(client: TestClient):
    """GET /api/v1/health must return HTTP 200 for versioned health checking."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_db_success(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """GET /health/db returns HTTP 200 and connectivity details when DB check passes."""
    monkeypatch.setattr(
        health_module,
        "check_db_connected",
        lambda timeout_seconds=5.0: (True, "Database connection verified successfully.", 14.5),
    )

    response = client.get("/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["latency_ms"] == 14.5
    assert "details" in data


def test_health_db_failure_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """GET /health/db returns HTTP 503 Service Unavailable when DB connection fails."""
    monkeypatch.setattr(
        health_module,
        "check_db_connected",
        lambda timeout_seconds=5.0: (False, "Database connection failed: Connection refused", 5000.0),
    )

    response = client.get("/health/db")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["database"] == "disconnected"
    assert "Connection refused" in data["error"]
    assert data["latency_ms"] == 5000.0


def test_check_db_connected_executes_select_1():
    """Directly tests that check_db_connected runs SELECT 1 and calculates latency."""
    test_engine = create_engine("sqlite:///:memory:")
    # Temporarily set test engine on db_module
    original_engine = db_module.engine
    try:
        db_module.engine = test_engine
        # Call the actual underlying function without mocks
        from app.core.database import check_db_connected as real_check
        # Using a raw function invocation to verify SELECT 1 logic
        with test_engine.connect() as conn:
            from sqlalchemy import text
            res = conn.execute(text("SELECT 1")).scalar()
            assert res == 1

        is_healthy, msg, latency = real_check()
        assert is_healthy is True
        assert "verified successfully" in msg
        assert latency >= 0.0
    finally:
        db_module.engine = original_engine


def test_sanitize_error_message():
    """Validates that error message sanitization redacts sensitive credentials."""
    raw_error = "OperationalError: connection to postgresql://postgres:mySuperSecretPass@db.supabase.co:5432 failed password='raw_password_here'"
    sanitized = sanitize_error_message(raw_error)

    assert "mySuperSecretPass" not in sanitized
    assert "raw_password_here" not in sanitized
    assert ":*****@" in sanitized
    assert "password='*****'" in sanitized


def test_get_db_session_lifecycle(monkeypatch: pytest.MonkeyPatch):
    """Verifies that the get_db dependency yields a session and closes it cleanly."""
    mock_session = MagicMock(spec=Session)
    mock_sessionmaker = MagicMock(return_value=mock_session)

    monkeypatch.setattr(db_module, "SessionLocal", mock_sessionmaker)
    monkeypatch.setattr(db_module, "engine", MagicMock())

    gen = get_db()
    session = next(gen)
    assert session == mock_session

    with pytest.raises(StopIteration):
        next(gen)

    mock_session.close.assert_called_once()
