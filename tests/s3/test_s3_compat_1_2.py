import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_database
from app.main import app
from app.models.blob import Blob, BlobInDb
from app.models.bucket import Bucket
from app.models.user import User
from app.storage.backend import PutFileResult


def _owner():
    return User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )


def _bucket(name="alice"):
    return Bucket(name=name, owner=_owner(), size=0)


@pytest.mark.asyncio
async def test_copy_object(mock_db, fake_storage, monkeypatch):
    src = Blob(
        path="src.txt",
        file="file-src",
        content_type="text/plain",
        size=3,
        bucket=_bucket(),
        owner=_owner(),
    )
    fake_storage.files["file-src"] = b"abc"
    store = {"src.txt": src}

    async def fake_bucket(db, name):
        return _bucket(name)

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_identity(db, request, body=None):
        from app.s3.auth import AccessIdentity

        return AccessIdentity(
            access_key_id=_owner().access_key_id,
            secret_key=_owner().secret_key,
            owner_username=_owner().username,
            role="owner",
            buckets=None,
            is_primary=True,
        )

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
            bucket=_bucket(bucket_name),
            owner=_owner(),
        )
        return BlobInDb(**blob.model_dump(), bucket_name=bucket_name)

    monkeypatch.setattr(
        "app.s3.handlers.copy_object.crud_get_bucket_by_name", fake_bucket
    )
    monkeypatch.setattr(
        "app.s3.handlers.copy_object.authorize_request_for_bucket", fake_verify
    )
    monkeypatch.setattr(
        "app.s3.handlers.copy_object.resolve_identity_from_request", fake_identity
    )
    monkeypatch.setattr("app.s3.handlers.copy_object.crud_get_all_blobs", fake_get_all)
    monkeypatch.setattr("app.s3.handlers.copy_object.crud_create_blob", fake_create)
    monkeypatch.setattr("app.s3.handlers.copy_object.storage", fake_storage)
    monkeypatch.setattr("app.s3.blob_io.storage", fake_storage)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/alice/dst.txt",
                headers={"x-amz-copy-source": "/alice/src.txt"},
            )
            assert resp.status_code == 200
            assert "CopyObjectResult" in resp.text
            assert "dst.txt" in store
            assert store["dst.txt"].size == 3
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_copy_object_rejects_oversized(mock_db, fake_storage, monkeypatch):
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod, "MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr("app.s3.handlers.copy_object.MAX_UPLOAD_BYTES", 10)

    src = Blob(
        path="big.bin",
        file="file-big",
        content_type="application/octet-stream",
        size=100,
        bucket=_bucket("archive"),
        owner=_owner(),
    )
    store = {"big.bin": src}

    async def fake_bucket(db, name):
        return _bucket(name)

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_identity(db, request, body=None):
        from app.s3.auth import AccessIdentity

        return AccessIdentity(
            access_key_id=_owner().access_key_id,
            secret_key=_owner().secret_key,
            owner_username=_owner().username,
            role="owner",
            buckets=None,
            is_primary=True,
        )

    async def fake_get_all(db, filters):
        item = store.get(filters.path)
        return [item] if item else []

    monkeypatch.setattr(
        "app.s3.handlers.copy_object.crud_get_bucket_by_name", fake_bucket
    )
    monkeypatch.setattr(
        "app.s3.handlers.copy_object.authorize_request_for_bucket", fake_verify
    )
    monkeypatch.setattr(
        "app.s3.handlers.copy_object.resolve_identity_from_request", fake_identity
    )
    monkeypatch.setattr("app.s3.handlers.copy_object.crud_get_all_blobs", fake_get_all)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/alice/dst-big.bin",
                headers={"x-amz-copy-source": "/archive/big.bin"},
            )
            assert resp.status_code == 400
            assert "EntityTooLarge" in resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_copy_object_denies_source_outside_scoped_buckets(mock_db, monkeypatch):
    src = Blob(
        path="src.txt",
        file="file-src",
        content_type="text/plain",
        size=3,
        bucket=_bucket("archive"),
        owner=_owner(),
    )
    store = {"src.txt": src}

    async def fake_bucket(db, name):
        return _bucket(name)

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_identity(db, request, body=None):
        from app.models.credential import ROLE_READWRITE
        from app.s3.auth import AccessIdentity

        return AccessIdentity(
            access_key_id="AKIASCOPED",
            secret_key="scopedsecret",
            owner_username=_owner().username,
            role=ROLE_READWRITE,
            buckets=["alice"],
            is_primary=False,
        )

    async def fake_get_all(db, filters):
        item = store.get(filters.path)
        return [item] if item else []

    monkeypatch.setattr(
        "app.s3.handlers.copy_object.crud_get_bucket_by_name", fake_bucket
    )
    monkeypatch.setattr(
        "app.s3.handlers.copy_object.authorize_request_for_bucket", fake_verify
    )
    monkeypatch.setattr(
        "app.s3.handlers.copy_object.resolve_identity_from_request", fake_identity
    )
    monkeypatch.setattr("app.s3.handlers.copy_object.crud_get_all_blobs", fake_get_all)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/alice/dst.txt",
                headers={"x-amz-copy-source": "/archive/src.txt"},
            )
            assert resp.status_code == 403
            assert "AccessDenied" in resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_head_create_delete_bucket(mock_db, monkeypatch):
    owner = _owner()
    buckets = {}

    async def fake_resolve(db, request, body=None):
        from app.models.user import UserInDb

        return UserInDb(
            username=owner.username,
            email=owner.email,
            access_key_id=owner.access_key_id,
            secret_key=owner.secret_key,
        )

    async def fake_get(db, name):
        return buckets.get(name)

    async def fake_create(db, bucket, current_user):
        b = _bucket(bucket.name)
        buckets[bucket.name] = b
        from app.models.bucket import BucketInDb

        return BucketInDb(name=bucket.name, owner_username=current_user.username)

    async def fake_delete(db, name):
        return buckets.pop(name, None) is not None

    async def fake_has_objects(db, name):
        return False

    async def fake_list_uploads(db, **kwargs):
        return []

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_identity(db, request, body=None):
        from app.s3.auth import AccessIdentity

        return AccessIdentity(
            access_key_id=owner.access_key_id,
            secret_key=owner.secret_key,
            owner_username=owner.username,
            role="owner",
            buckets=None,
            is_primary=True,
        )

    monkeypatch.setattr(
        "app.s3.handlers.bucket_ops.resolve_user_from_request", fake_resolve
    )
    monkeypatch.setattr(
        "app.s3.handlers.bucket_ops.resolve_identity_from_request", fake_identity
    )
    monkeypatch.setattr("app.s3.handlers.bucket_ops.crud_get_bucket_by_name", fake_get)
    monkeypatch.setattr("app.s3.handlers.bucket_ops.crud_create_bucket", fake_create)
    monkeypatch.setattr("app.s3.handlers.bucket_ops.crud_delete_bucket", fake_delete)
    monkeypatch.setattr(
        "app.s3.handlers.bucket_ops.crud_bucket_has_objects", fake_has_objects
    )
    monkeypatch.setattr(
        "app.s3.handlers.bucket_ops.crud_list_multipart_uploads", fake_list_uploads
    )
    monkeypatch.setattr(
        "app.s3.handlers.bucket_ops.authorize_request_for_bucket", fake_verify
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.put("/newbucket")
            assert created.status_code == 200
            headed = await client.head("/newbucket")
            assert headed.status_code == 200
            deleted = await client.delete("/newbucket")
            assert deleted.status_code == 204
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_multipart_uploads(mock_db, monkeypatch):
    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_list(db, **kwargs):
        from datetime import datetime, timezone

        return [
            {
                "upload_id": "u1",
                "key": "big.bin",
                "initiated_at": datetime.now(timezone.utc),
            }
        ]

    monkeypatch.setattr(
        "app.s3.handlers.list_objects.crud_get_bucket_by_name", fake_bucket
    )
    monkeypatch.setattr(
        "app.s3.handlers.list_objects.authorize_request_for_bucket", fake_verify
    )
    monkeypatch.setattr(
        "app.s3.handlers.list_objects.crud_list_multipart_uploads", fake_list
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/alice?uploads")
            assert resp.status_code == 200
            assert "ListMultipartUploadsResult" in resp.text
            assert "u1" in resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_simple_bearer_upload(mock_db, fake_storage, monkeypatch):
    import sys

    from app.models.user import UserInDb

    upload_mod = sys.modules["app.api.v1.endpoints.upload"]

    user = UserInDb(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )
    store = {}

    async def fake_user(db, access_key):
        return user if access_key == user.access_key_id else None

    async def fake_bucket(db, name):
        return _bucket(name)

    async def fake_get_all(db, filters):
        item = store.get(filters.path)
        return [item] if item else []

    async def fake_create(db, blob, bucket_name, update=False):
        store[blob.path] = blob
        return BlobInDb(**blob.model_dump(), bucket_name=bucket_name)

    monkeypatch.setattr(upload_mod, "crud_get_user_by_access_key_id", fake_user)
    monkeypatch.setattr(upload_mod, "crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr(upload_mod, "crud_get_all_blobs", fake_get_all)
    monkeypatch.setattr(upload_mod, "crud_create_blob", fake_create)
    monkeypatch.setattr(upload_mod, "storage", fake_storage)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/v1/upload/?bucket=alice&key=hi.txt",
                content=b"hello",
                headers={"Authorization": "Bearer AKIATESTACCESS1:secretkeysecret"},
            )
            assert resp.status_code == 200
            assert resp.json()["ok"] is True
            assert "hi.txt" in store
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_share_password_lockout(mock_db, monkeypatch):
    from app.crud.share_lockout import (
        share_is_locked,
        share_record_password_failure,
    )

    monkeypatch.setattr("app.crud.share_lockout.SHARE_MAX_FAILED_ATTEMPTS", 2)
    monkeypatch.setattr("app.crud.share_lockout.SHARE_LOCKOUT_SECONDS", 600)

    assert await share_record_password_failure(mock_db, "tok", "1.2.3.4") is False
    assert await share_record_password_failure(mock_db, "tok", "1.2.3.4") is True
    assert await share_is_locked(mock_db, "tok", "1.2.3.4") is True
