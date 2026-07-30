import base64
import hashlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.mongodb import get_database
from app.main import app
from app.models.blob import Blob, BlobInDb
from app.models.bucket import Bucket
from app.models.user import User
from app.s3.xml import object_etag


def _bucket():
    owner = User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )
    return Bucket(name="alice", owner=owner, size=0)


def _md5_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.md5(data).digest()).decode("ascii")


@pytest.mark.asyncio
async def test_get_supports_range_and_if_none_match(
    mock_db, fake_storage, monkeypatch
):
    blob = Blob(
        path="hello.txt",
        file="file-1",
        content_type="text/plain",
        size=5,
        bucket=_bucket(),
        owner=_bucket().owner,
    )
    fake_storage.files["file-1"] = b"abcde"

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_blobs(db, filters):
        return [blob]

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_all_blobs", fake_blobs)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.storage", fake_storage)

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ranged = await client.get(
                "/alice/hello.txt", headers={"Range": "bytes=1-3"}
            )
            assert ranged.status_code == 206
            assert ranged.content == b"bcd"
            assert ranged.headers["content-range"] == "bytes 1-3/5"

            etag = object_etag(blob)
            cached = await client.get(
                "/alice/hello.txt", headers={"If-None-Match": etag}
            )
            assert cached.status_code == 304
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_acl_subresource_returns_501(mock_db, monkeypatch):
    async def fake_bucket(db, name):
        return _bucket()

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put("/alice/hello.txt?acl", content=b"<AccessControl/>")
            assert resp.status_code == 501
            assert "NotImplemented" in resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_objects_batch(mock_db, fake_storage, monkeypatch):
    from app.core.config import DATABASE_NAME

    store = {
        "a.txt": BlobInDb(
            path="a.txt",
            file="f1",
            content_type="text/plain",
            size=1,
            bucket_name="alice",
            message_id=11,
        ),
        "b.txt": BlobInDb(
            path="b.txt",
            file="f2",
            content_type="text/plain",
            size=1,
            bucket_name="alice",
            message_id=12,
        ),
    }
    for blob in store.values():
        await mock_db[DATABASE_NAME]["blobs"].insert_one(blob.model_dump())

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_delete(db, bucket_name, path):
        return store.pop(path, None)

    monkeypatch.setattr(
        "app.s3.handlers.delete_objects.crud_get_bucket_by_name", fake_bucket
    )
    monkeypatch.setattr(
        "app.s3.handlers.delete_objects.authorize_request_for_bucket", fake_verify
    )
    monkeypatch.setattr("app.s3.handlers.delete_objects.precheck_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.object_lifecycle.ENABLE_TRASH", False)
    monkeypatch.setattr("app.s3.object_lifecycle.crud_delete_blob", fake_delete)

    async def fake_safe_delete(db, message_id, *, chat_id=None, reason=""):
        return await fake_storage.delete_message(message_id, chat_id=chat_id)

    monkeypatch.setattr(
        "app.s3.object_lifecycle.safe_delete_tg_message", fake_safe_delete
    )

    async def override_db():
        return mock_db

    body = (
        b"<Delete><Object><Key>a.txt</Key></Object>"
        b"<Object><Key>b.txt</Key></Object></Delete>"
    )
    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/alice?delete",
                content=body,
                headers={"Content-MD5": _md5_b64(body)},
            )
            assert resp.status_code == 200
            assert "<Deleted><Key>a.txt</Key></Deleted>" in resp.text
            assert "<Deleted><Key>b.txt</Key></Deleted>" in resp.text
            assert fake_storage.deleted_messages == [11, 12]
    finally:
        app.dependency_overrides.clear()
