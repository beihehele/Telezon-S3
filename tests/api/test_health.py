import pytest
from httpx import ASGITransport, AsyncClient

from app.db import session as db_session
from app.main import app
from app.storage.telegram.account_client import account_client_manager


@pytest.fixture
def wired_db(mock_db, monkeypatch):
    async def fake_ping():
        return None

    monkeypatch.setattr(db_session, "async_session_factory", object())
    monkeypatch.setattr(db_session, "ping_database", fake_ping)
    yield mock_db


@pytest.mark.asyncio
async def test_health_db_ok_when_factory_set_after_health_module_import(monkeypatch):
    """Regression: must not snapshot async_session_factory at import time."""
    from app.api import health as health_module

    assert health_module is not None

    async def fake_ping():
        return None

    monkeypatch.setattr(db_session, "async_session_factory", object())
    monkeypatch.setattr(db_session, "ping_database", fake_ping)
    monkeypatch.setattr(account_client_manager, "ready", True)
    monkeypatch.setattr(account_client_manager, "last_error", None)

    from app.api.health import health

    resp = await health()
    assert resp.status_code == 200
    assert resp.body  # JSONResponse


@pytest.mark.asyncio
async def test_health_ok_when_db_and_tg_ready(wired_db, monkeypatch):
    monkeypatch.setattr(account_client_manager, "ready", True)
    monkeypatch.setattr(account_client_manager, "last_error", None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"]["ok"] is True


@pytest.mark.asyncio
async def test_health_omits_errors_by_default_when_degraded(wired_db, monkeypatch):
    monkeypatch.setattr(account_client_manager, "ready", False)
    monkeypatch.setattr(account_client_manager, "last_error", "tg down")
    monkeypatch.setattr("app.api.health.HEALTH_EXPOSE_ERRORS", False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["telegram"]["ok"] is False
    assert "error" not in body["telegram"]
    assert "error" not in body["database"]


@pytest.mark.asyncio
async def test_health_includes_errors_when_enabled(wired_db, monkeypatch):
    monkeypatch.setattr(account_client_manager, "ready", False)
    monkeypatch.setattr(account_client_manager, "last_error", "tg down")
    monkeypatch.setattr("app.api.health.HEALTH_EXPOSE_ERRORS", True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    body = resp.json()
    assert body["telegram"]["error"] == "tg down"
