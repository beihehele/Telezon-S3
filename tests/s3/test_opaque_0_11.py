"""0.11: opaque names, MPU staging/albums, cross-bucket forward."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_database
from app.main import app
from app.models.blob import Blob, BlobInDb
from app.models.bucket import Bucket
from app.models.user import User
from app.storage.mpu_staging import upload_staging_dir


def _owner():
    return User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )


def _bucket(name="alice", *, chat_id="1001"):
    return Bucket(
        name=name,
        owner=_owner(),
        size=0,
        telegram_chat_id=chat_id,
        telegram_topic_id=1,
    )


def _auth_headers():
    return {
        "Authorization": (
            "AWS4-HMAC-SHA256 Credential=AKIATESTACCESS1/20200101/us-east-1/s3/aws4_request, "
            "SignedHeaders=host, Signature=00"
        )
    }


@pytest.mark.asyncio
async def test_cross_bucket_copy_uses_forward_not_put(mock_db, fake_storage, monkeypatch):
    src = Blob(
        path="src.bin",
        file="file-src",
        content_type="application/octet-stream",
        size=3,
        message_id=77,
        bucket=_bucket("archive", chat_id="2002"),
        owner=_owner(),
    )
    store = {"src.bin": src}
    created = []

    async def fake_bucket(db, name):
        return _bucket(name, chat_id="2002" if name == "archive" else "1001")

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
        created.append(blob)
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
    monkeypatch.setattr("app.s3.copy_forward.storage", fake_storage)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/alice/dst.bin",
                headers={"x-amz-copy-source": "/archive/src.bin"},
            )
            assert resp.status_code == 200
            assert fake_storage.forward_calls
            assert fake_storage.put_calls == 0
            assert created[0].message_id != 77
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_mpu_complete_uses_two_media_groups_for_fifteen_parts(
    mock_db, fake_storage, monkeypatch
):
    monkeypatch.setattr("app.s3.handlers.multipart.MULTIPART_MIN_PART_BYTES", 1)

    async def fake_bucket(db, name):
        return _bucket(name)

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    store = {}

    async def fake_get_all(db, filters):
        item = store.get(filters.path)
        return [item] if item else []

    async def fake_create(db, blob, bucket_name, update=False):
        store[blob.path] = Blob(
            path=blob.path,
            file=blob.file,
            content_type=blob.content_type,
            size=blob.size,
            parts=blob.parts,
            bucket=_bucket(),
            owner=_owner(),
        )
        return blob

    monkeypatch.setattr(
        "app.s3.handlers.multipart.crud_get_bucket_by_name", fake_bucket
    )
    monkeypatch.setattr(
        "app.s3.handlers.multipart.authorize_request_for_bucket", fake_verify
    )
    monkeypatch.setattr("app.s3.handlers.multipart.precheck_request_for_bucket", fake_verify)

    async def fake_owner_ok(upload, bucket, request, db):
        return True

    monkeypatch.setattr(
        "app.s3.handlers.multipart._upload_owner_ok", fake_owner_ok
    )
    monkeypatch.setattr("app.s3.handlers.multipart.storage", fake_storage)
    monkeypatch.setattr("app.s3.handlers.multipart.crud_get_all_blobs", fake_get_all)
    monkeypatch.setattr("app.s3.handlers.multipart.crud_create_blob", fake_create)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_all_blobs", fake_get_all)
    monkeypatch.setattr("app.s3.handlers.object.storage", fake_storage)

    async def override_db():
        yield mock_db

    headers = _auth_headers()
    app.dependency_overrides[get_database] = override_db
    part_etags = []
    upload_id = ""
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            init = await client.post("/alice/big.bin?uploads", headers=headers)
            upload_id = init.text.split("<UploadId>")[1].split("</UploadId>")[0]
            for n in range(1, 16):
                resp = await client.put(
                    f"/alice/big.bin?partNumber={n}&uploadId={upload_id}",
                    content=b"x",
                    headers=headers,
                )
                assert resp.status_code == 200
                part_etags.append((n, resp.headers["etag"]))
            parts_xml = "".join(
                f"<Part><PartNumber>{n}</PartNumber><ETag>{etag}</ETag></Part>"
                for n, etag in part_etags
            )
            done = await client.post(
                f"/alice/big.bin?uploadId={upload_id}",
                content=f"<CompleteMultipartUpload>{parts_xml}</CompleteMultipartUpload>",
                headers=headers,
            )
            assert done.status_code == 200
            assert fake_storage.media_group_calls == 2
            assert not upload_staging_dir(upload_id).exists()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_mpu_complete_failure_rolls_back_partial_tg(
    mock_db, fake_storage, monkeypatch
):
    monkeypatch.setattr("app.s3.handlers.multipart.MULTIPART_MIN_PART_BYTES", 1)
    monkeypatch.setattr("app.s3.handlers.multipart.TG_ALBUM_MAX_ITEMS", 5)
    calls = {"n": 0}
    real_send_group = fake_storage.send_media_group

    async def flaky_media_group(documents, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            from app.storage.errors import StorageUnavailableError

            raise StorageUnavailableError("simulated tg failure")
        return await real_send_group(documents, **kwargs)

    fake_storage.send_media_group = flaky_media_group

    async def fake_bucket(db, name):
        return _bucket(name)

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    monkeypatch.setattr(
        "app.s3.handlers.multipart.crud_get_bucket_by_name", fake_bucket
    )
    monkeypatch.setattr(
        "app.s3.handlers.multipart.authorize_request_for_bucket", fake_verify
    )
    monkeypatch.setattr("app.s3.handlers.multipart.precheck_request_for_bucket", fake_verify)

    async def fake_owner_ok(upload, bucket, request, db):
        return True

    monkeypatch.setattr(
        "app.s3.handlers.multipart._upload_owner_ok", fake_owner_ok
    )
    monkeypatch.setattr("app.s3.handlers.multipart.storage", fake_storage)
    monkeypatch.setattr("app.ops.tg_delete._storage", lambda: fake_storage)
    async def fake_get_all_empty(db, filters):
        return []

    monkeypatch.setattr(
        "app.s3.handlers.multipart.crud_get_all_blobs", fake_get_all_empty
    )
    async def fake_create(db, blob, bucket_name, update=False):
        return blob

    monkeypatch.setattr(
        "app.s3.handlers.multipart.crud_create_blob", fake_create
    )

    async def override_db():
        yield mock_db

    headers = _auth_headers()
    app.dependency_overrides[get_database] = override_db
    upload_id = ""
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            init = await client.post("/alice/big.bin?uploads", headers=headers)
            upload_id = init.text.split("<UploadId>")[1].split("</UploadId>")[0]
            part_etags = []
            for n in range(1, 12):
                resp = await client.put(
                    f"/alice/big.bin?partNumber={n}&uploadId={upload_id}",
                    content=b"x",
                    headers=headers,
                )
                part_etags.append((n, resp.headers["etag"]))
            parts_xml = "".join(
                f"<Part><PartNumber>{n}</PartNumber><ETag>{etag}</ETag></Part>"
                for n, etag in part_etags
            )
            done = await client.post(
                f"/alice/big.bin?uploadId={upload_id}",
                content=f"<CompleteMultipartUpload>{parts_xml}</CompleteMultipartUpload>",
                headers=headers,
            )
            assert done.status_code == 503
            assert calls["n"] == 2
            assert fake_storage.deleted_messages
            assert upload_staging_dir(upload_id).exists()
    finally:
        app.dependency_overrides.clear()
