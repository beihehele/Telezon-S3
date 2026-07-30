import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_database
from app.main import app
from app.models.blob import Blob
from app.models.bucket import Bucket
from app.models.user import User


def _bucket(*, is_public=False):
    owner = User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )
    return Bucket(
        name="alice",
        owner=owner,
        size=0,
        is_public=is_public,
        telegram_chat_id="-1001",
        telegram_topic_id=42,
    )


@pytest.mark.asyncio
async def test_public_get_without_auth(mock_db, fake_storage, monkeypatch):
    blob = Blob(
        path="hello.txt",
        file="file-1",
        content_type="text/plain",
        size=5,
        bucket=_bucket(is_public=True),
        owner=_bucket().owner,
    )
    fake_storage.files["file-1"] = b"hello"

    async def fake_bucket(db, name):
        return _bucket(is_public=True)

    async def deny(bucket, request, db=None, body=None):
        return "signature"

    async def fake_blobs(db, filters):
        return [blob]

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", deny)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", deny)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_all_blobs", fake_blobs)
    monkeypatch.setattr("app.s3.handlers.object.storage", fake_storage)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/alice/hello.txt")
            assert resp.status_code == 200
            assert resp.content == b"hello"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_public_put_and_delete_still_require_auth(mock_db, monkeypatch):
    async def fake_bucket(db, name):
        return _bucket(is_public=True)

    async def deny(bucket, request, db=None, body=None):
        return "signature"

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", deny)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", deny)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            put = await client.put("/alice/hello.txt", content=b"x")
            delete = await client.delete("/alice/hello.txt")
            assert put.status_code == 403
            assert delete.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_private_get_still_requires_auth(mock_db, monkeypatch):
    async def fake_bucket(db, name):
        return _bucket(is_public=False)

    async def deny(bucket, request, db=None, body=None):
        return "signature"

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", deny)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", deny)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/alice/hello.txt")
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_passes_bucket_telegram_destination(
    mock_db, fake_storage, monkeypatch
):
    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_get_all(db, filters):
        return []

    async def fake_create(db, blob, bucket_name, update=False):
        return blob

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_all_blobs", fake_get_all)
    monkeypatch.setattr("app.s3.handlers.object.crud_create_blob", fake_create)
    monkeypatch.setattr("app.s3.handlers.object.storage", fake_storage)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put("/alice/x.bin", content=b"abc")
            assert resp.status_code == 200
            assert fake_storage.last_put_kwargs["chat_id"] == "-1001"
            assert fake_storage.last_put_kwargs["topic_id"] == 42
    finally:
        app.dependency_overrides.clear()
