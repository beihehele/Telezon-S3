"""GET …/content without Range must not pull huge objects through the proxy."""

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import objects as objects_mod
from app.core.media_ticket import create_media_ticket
from app.crud.blob import crud_create_blob
from app.db.session import get_database
from app.main import app
from app.models.blob import BlobInCreate
from app.models.bucket import Bucket
from app.models.user import User
from tests.conftest import override_get_database

_LARGE = 10 * 1024 * 1024  # above default CONTENT_PROXY_MAX_FULL_BYTES (8MB)


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
async def test_content_proxy_rejects_large_full_get_with_media_token(
    mock_db, monkeypatch, fake_storage
):
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="big.bin", file="f1", size=_LARGE, content_type="application/octet-stream"),
        "alice",
    )
    fake_storage.files["f1"] = b"x" * _LARGE

    async def fake_bucket(db, name):
        return _bucket() if name == "alice" else None

    monkeypatch.setattr(objects_mod, "crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.blob_io.storage", fake_storage)
    app.dependency_overrides[get_database] = override_get_database(mock_db)
    try:
        token = create_media_ticket(
            username="alice",
            bucket="alice",
            key="big.bin",
            expires_delta=timedelta(minutes=10),
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/buckets/alice/objects/big.bin/content",
                params={"media_token": token},
            )
            assert resp.status_code == 413
            assert resp.headers.get("accept-ranges") == "bytes"
            assert "*/" in resp.headers.get("content-range", "")

            ranged = await client.get(
                "/api/v1/buckets/alice/objects/big.bin/content",
                params={"media_token": token},
                headers={"Range": "bytes=0-1023"},
            )
            assert ranged.status_code == 206
            assert len(ranged.content) == 1024
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_content_proxy_allows_small_full_get(mock_db, monkeypatch, fake_storage):
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="tiny.txt", file="f1", size=5, content_type="text/plain"),
        "alice",
    )
    fake_storage.files["f1"] = b"hello"

    async def fake_bucket(db, name):
        return _bucket() if name == "alice" else None

    monkeypatch.setattr(objects_mod, "crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.blob_io.storage", fake_storage)
    app.dependency_overrides[get_database] = override_get_database(mock_db)
    try:
        token = create_media_ticket(
            username="alice",
            bucket="alice",
            key="tiny.txt",
            expires_delta=timedelta(minutes=10),
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/buckets/alice/objects/tiny.txt/content",
                params={"media_token": token},
            )
            assert resp.status_code == 200
            assert resp.content == b"hello"
    finally:
        app.dependency_overrides.clear()
