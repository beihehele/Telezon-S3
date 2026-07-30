import io

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.mongodb import get_database
from app.main import app
from app.models.blob import Blob, BlobInDb
from app.models.bucket import Bucket
from app.models.user import User
from app.storage.storage import PutFileResult


def _bucket():
    owner = User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )
    return Bucket(name="alice", owner=owner, size=0)


@pytest.mark.asyncio
async def test_head_returns_headers_when_authorized(mock_db, fake_storage, monkeypatch):
    blob = Blob(
        path="hello.txt",
        file="file-1",
        content_type="text/plain",
        size=5,
        bucket=_bucket(),
        owner=_bucket().owner,
    )

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
            resp = await client.head("/alice/hello.txt")
            assert resp.status_code == 200
            assert resp.headers["content-length"] == "5"
            assert resp.headers["content-type"] == "text/plain"
            assert "etag" in resp.headers
            assert resp.content == b""
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_head_rejects_unauthorized(mock_db, monkeypatch):
    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "signature"

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.head("/alice/hello.txt")
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_calls_telegram_when_message_id_present(
    mock_db, fake_storage, monkeypatch
):
    from app.core.config import DATABASE_NAME

    deleted = BlobInDb(
        path="hello.txt",
        file="file-1",
        content_type="text/plain",
        size=5,
        bucket_name="alice",
        message_id=42,
    )
    await mock_db[DATABASE_NAME]["blobs"].insert_one(deleted.model_dump())

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    calls = {"n": 0}

    async def fake_delete(db, bucket_name, path):
        calls["n"] += 1
        return deleted if calls["n"] == 1 else None

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.storage", fake_storage)
    monkeypatch.setattr("app.s3.object_lifecycle.ENABLE_TRASH", False)
    monkeypatch.setattr("app.s3.object_lifecycle.crud_delete_blob", fake_delete)

    async def fake_safe_delete(db, message_id, *, chat_id=None, reason=""):
        return await fake_storage.delete_message(message_id, chat_id=chat_id)

    monkeypatch.setattr(
        "app.s3.object_lifecycle.safe_delete_tg_message", fake_safe_delete
    )

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/alice/hello.txt")
            assert resp.status_code == 204
            assert fake_storage.deleted_messages == [42]
            again = await client.delete("/alice/hello.txt")
            assert again.status_code == 204
            assert fake_storage.deleted_messages == [42]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_empty_key_rejected(mock_db, monkeypatch):
    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put("/alice/", content=b"x")
            assert resp.status_code == 400
            assert "InvalidRequest" in resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_without_message_id_skips_telegram(
    mock_db, fake_storage, monkeypatch
):
    from app.core.config import DATABASE_NAME

    deleted = BlobInDb(
        path="hello.txt",
        file="file-1",
        content_type="text/plain",
        size=5,
        bucket_name="alice",
        message_id=None,
    )
    await mock_db[DATABASE_NAME]["blobs"].insert_one(deleted.model_dump())

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_delete(db, bucket_name, path):
        return deleted

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.object_lifecycle.ENABLE_TRASH", False)
    monkeypatch.setattr("app.s3.object_lifecycle.crud_delete_blob", fake_delete)
    monkeypatch.setattr("app.s3.handlers.object.storage", fake_storage)

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/alice/hello.txt")
            assert resp.status_code == 204
            assert fake_storage.deleted_messages == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_overwrite_soft_deletes_previous(mock_db, fake_storage, monkeypatch):
    existing = Blob(
        path="hello.txt",
        file="file-old",
        content_type="text/plain",
        size=1,
        message_id=7,
        bucket=_bucket(),
        owner=_bucket().owner,
    )
    store = {"hello.txt": existing}

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_get_all(db, filters):
        item = store.get(filters.path)
        return [item] if item else []

    async def fake_create(db, blob, bucket_name, update=False):
        store[blob.path] = Blob(
            path=blob.path,
            file=blob.file,
            content_type=blob.content_type,
            size=blob.size,
            message_id=blob.message_id,
            bucket=_bucket(),
            owner=_bucket().owner,
        )
        return BlobInDb(**blob.model_dump(), bucket_name=bucket_name)

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_all_blobs", fake_get_all)
    monkeypatch.setattr("app.s3.handlers.object.crud_create_blob", fake_create)
    monkeypatch.setattr("app.s3.handlers.object.storage", fake_storage)
    monkeypatch.setattr("app.s3.object_lifecycle.ENABLE_TRASH", True)

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put("/alice/hello.txt", content=b"new")
            assert resp.status_code == 200
            assert "etag" in resp.headers
            assert fake_storage.deleted_messages == []
    finally:
        app.dependency_overrides.clear()

    from app.crud.trash import crud_list_trash

    trash = await crud_list_trash(mock_db, bucket_name="alice")
    assert len(trash) == 1
    assert trash[0].message_id == 7


@pytest.mark.asyncio
async def test_put_get_roundtrip(mock_db, fake_storage, monkeypatch):
    store = {}

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_get_all(db, filters):
        item = store.get(filters.path)
        return [item] if item else []

    async def fake_create(db, blob, bucket_name, update=False):
        store[blob.path] = Blob(
            path=blob.path,
            file=blob.file,
            content_type=blob.content_type,
            size=blob.size,
            message_id=blob.message_id,
            bucket=_bucket(),
            owner=_bucket().owner,
        )
        return BlobInDb(**blob.model_dump(), bucket_name=bucket_name)

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_all_blobs", fake_get_all)
    monkeypatch.setattr("app.s3.handlers.object.crud_create_blob", fake_create)
    monkeypatch.setattr("app.s3.handlers.object.storage", fake_storage)

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            put = await client.put(
                "/alice/dir/file.bin",
                content=b"abc123",
                headers={"content-type": "application/octet-stream"},
            )
            assert put.status_code == 200
            got = await client.get("/alice/dir/file.bin")
            assert got.status_code == 200
            assert got.content == b"abc123"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_rejects_entity_too_large(mock_db, monkeypatch):
    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.body.MAX_UPLOAD_BYTES", 4)
    monkeypatch.setattr("app.s3.handlers.object.MAX_UPLOAD_BYTES", 4)

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put("/alice/big.bin", content=b"12345")
            assert resp.status_code == 400
            assert "EntityTooLarge" in resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_rejects_oversized_content_length_early(mock_db, monkeypatch):
    async def fake_bucket(db, name):
        return _bucket()

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.body.MAX_UPLOAD_BYTES", 4)
    monkeypatch.setattr("app.s3.handlers.object.MAX_UPLOAD_BYTES", 4)

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/alice/big.bin",
                content=b"12345",
                headers={"content-length": "5"},
            )
            assert resp.status_code == 400
            assert "EntityTooLarge" in resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_returns_service_unavailable(mock_db, monkeypatch):
    from app.storage.errors import StorageUnavailableError

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_get_all(db, filters):
        return []

    class DownStorage:
        async def put_file(self, file, filename, **kwargs):
            raise StorageUnavailableError("down")

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_all_blobs", fake_get_all)
    monkeypatch.setattr("app.s3.handlers.object.storage", DownStorage())

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put("/alice/x.bin", content=b"abc")
            assert resp.status_code == 503
            assert "ServiceUnavailable" in resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_returns_slow_down_on_throttle(mock_db, monkeypatch):
    from app.storage.errors import StorageThrottleError

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_get_all(db, filters):
        return []

    class ThrottledStorage:
        async def put_file(self, file, filename, **kwargs):
            raise StorageThrottleError("limited")

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_all_blobs", fake_get_all)
    monkeypatch.setattr("app.s3.handlers.object.storage", ThrottledStorage())

    async def override_db():
        return mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put("/alice/x.bin", content=b"abc")
            assert resp.status_code == 503
            assert "SlowDown" in resp.text
    finally:
        app.dependency_overrides.clear()
