import pytest
from httpx import ASGITransport, AsyncClient

from app.db.mongodb import db
from app.main import app
from app.storage.telegram.account_client import account_client_manager


@pytest.fixture
def wired_db(mock_db):
    db.client = mock_db
    yield mock_db
    db.client = None


@pytest.mark.asyncio
async def test_health_degraded_without_telegram(wired_db):
    account_client_manager.ready = False
    account_client_manager.last_error = "not started"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["mongodb"]["ok"] is True
    assert body["telegram"]["ok"] is False


@pytest.mark.asyncio
async def test_health_ok_when_telegram_ready(wired_db):
    account_client_manager.ready = True
    account_client_manager.last_error = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
