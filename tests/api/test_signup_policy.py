import importlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_database
from app.main import app
from tests.conftest import override_get_database


@pytest.mark.asyncio
async def test_auth_config_allow_signup_default():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/auth/config")
        assert resp.status_code == 200
        assert resp.json()["allow_signup"] is True


@pytest.mark.asyncio
async def test_signup_disabled(mock_db, monkeypatch):
    auth_mod = importlib.import_module("app.api.auth")
    monkeypatch.setattr(auth_mod, "ALLOW_SIGNUP", False)
    app.dependency_overrides[get_database] = override_get_database(mock_db)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/auth/signup",
                json={
                    "username": "newbie",
                    "email": "newbie@example.com",
                    "password": "password123",
                },
            )
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
