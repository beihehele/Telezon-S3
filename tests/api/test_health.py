import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.telegram.account_client import account_client_manager


@pytest.fixture
def wired_db(mock_db, monkeypatch):
    async def fake_ping():
        return None

    monkeypatch.setattr("app.api.health.async_session_factory", object())
    monkeypatch.setattr("app.api.health.ping_database", fake_ping)
    yield mock_db


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
