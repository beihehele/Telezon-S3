import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_database
from app.main import app
from app.models.bucket import Bucket
from app.models.user import User


def _bucket():
    owner = User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )
    return Bucket(name="alice", owner=owner, size=0)


def _auth_headers():
    return {
        "Authorization": (
            "AWS4-HMAC-SHA256 Credential=AKIATESTACCESS1/20200101/us-east-1/s3/aws4_request, "
            "SignedHeaders=host, Signature=00"
        )
    }


@pytest.mark.asyncio
async def test_multipart_create_upload_part_complete(mock_db, fake_storage, monkeypatch):
    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None, **kwargs):
        return "ok"

    store = {}

    async def fake_get_all(db, filters):
        item = store.get(filters.path)
        return [item] if item else []

    async def fake_create(db, blob, bucket_name, update=False):
        from app.models.blob import Blob

        store[blob.path] = Blob(
            path=blob.path,
            file=blob.file,
            content_type=blob.content_type,
            size=blob.size,
            parts=blob.parts,
            bucket=_bucket(),
            owner=_bucket().owner,
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

    # Multipart metadata in SQL tables (see crud_multipart).
    async def override_db():
        yield mock_db

    headers = _auth_headers()
    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            init = await client.post("/alice/big.bin?uploads", headers=headers)
            assert init.status_code == 200
            assert "<UploadId>" in init.text
            upload_id = init.text.split("<UploadId>")[1].split("</UploadId>")[0]

            p1 = await client.put(
                f"/alice/big.bin?partNumber=1&uploadId={upload_id}",
                content=b"aaa",
                headers=headers,
            )
            p2 = await client.put(
                f"/alice/big.bin?partNumber=2&uploadId={upload_id}",
                content=b"bbb",
                headers=headers,
            )
            assert p1.status_code == 200
            assert p2.status_code == 200
            etag1 = p1.headers["etag"]
            etag2 = p2.headers["etag"]

            complete_xml = (
                "<CompleteMultipartUpload>"
                f"<Part><PartNumber>1</PartNumber><ETag>{etag1}</ETag></Part>"
                f"<Part><PartNumber>2</PartNumber><ETag>{etag2}</ETag></Part>"
                "</CompleteMultipartUpload>"
            )
            done = await client.post(
                f"/alice/big.bin?uploadId={upload_id}",
                content=complete_xml,
                headers=headers,
            )
            assert done.status_code == 200
            assert "CompleteMultipartUploadResult" in done.text

            got = await client.get("/alice/big.bin", headers=headers)
            assert got.status_code == 200
            assert got.content == b"aaabbb"
    finally:
        app.dependency_overrides.clear()
