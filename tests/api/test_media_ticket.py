import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import objects as objects_mod
from app.core.token import get_current_user
from app.crud.blob import crud_create_blob
from app.db.session import get_database
from app.main import app
from app.models.blob import BlobInCreate
from app.models.bucket import Bucket
from app.models.user import User
from tests.conftest import override_get_database


def _user():
    return User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )


def _bucket():
    return Bucket(name="alice", owner=_user(), size=0)


@pytest.mark.asyncio
async def test_content_ticket_and_media_token_get(mock_db, monkeypatch, fake_storage):
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="clip.mp4", file="f1", size=4, content_type="video/mp4"),
        "alice",
    )
    fake_storage.files["f1"] = b"test"

    async def fake_bucket(db, name):
        return _bucket() if name == "alice" else None

    monkeypatch.setattr(objects_mod, "crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.blob_io.storage", fake_storage)
    app.dependency_overrides[get_database] = override_get_database(mock_db)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ticket = await client.post(
                "/api/v1/buckets/alice/objects/clip.mp4/content-ticket",
                headers={"Authorization": "Bearer test"},
            )
            assert ticket.status_code == 200
            media_token = ticket.json()["media_token"]
            assert ticket.json()["expires_in"] >= 60

            got = await client.get(
                "/api/v1/buckets/alice/objects/clip.mp4/content",
                params={"media_token": media_token},
            )
            assert got.status_code == 200
            assert got.content == b"test"

            wrong = await client.get(
                "/api/v1/buckets/alice/objects/other.mp4/content",
                params={"media_token": media_token},
            )
            assert wrong.status_code == 403
    finally:
        app.dependency_overrides.clear()
