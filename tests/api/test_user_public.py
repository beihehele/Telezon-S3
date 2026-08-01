import pytest
from httpx import ASGITransport, AsyncClient

from app.core.token import get_current_user
from app.db.session import get_database
from app.main import app
from app.models.user import User, UserPublic
from tests.conftest import override_get_database


@pytest.mark.asyncio
async def test_current_user_excludes_secret_key(mock_db):
    user = User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="super-secret-key-value",
        role="user",
    )
    app.dependency_overrides[get_database] = override_get_database(mock_db)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/auth/current_user",
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "secret_key" not in body
            assert body["username"] == "alice"
            parsed = UserPublic.model_validate(body)
            assert parsed.access_key_id == "AKIATESTACCESS1"
    finally:
        app.dependency_overrides.clear()
