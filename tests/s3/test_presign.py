from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_database
from app.main import app
from app.models.blob import Blob
from app.models.bucket import Bucket
from app.models.user import User
from app.s3.auth import _presign_still_valid
from app.s3.presign import create_presigned_url
from starlette.requests import Request


def _bucket():
    owner = User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )
    return Bucket(name="alice", owner=owner, size=0)


@pytest.mark.asyncio
async def test_presign_get_roundtrip(mock_db, fake_storage, monkeypatch):
    blob = Blob(
        path="hello.txt",
        file="file-1",
        content_type="text/plain",
        size=5,
        bucket=_bucket(),
        owner=_bucket().owner,
    )
    fake_storage.files["file-1"] = b"hello"

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_blobs(db, filters):
        return [blob]

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.crud_get_all_blobs", fake_blobs)
    monkeypatch.setattr("app.s3.handlers.object.storage", fake_storage)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        url = create_presigned_url(
            method="GET",
            bucket="alice",
            key="hello.txt",
            access_key="AKIATESTACCESS1",
            secret_key="secretkeysecret",
            host="test",
            expires_in=3600,
            scheme="http",
        )
        parsed = urlparse(url)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(parsed.path + "?" + parsed.query)
            assert resp.status_code == 200, resp.text
            assert resp.content == b"hello"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_presign_rejected_when_verify_fails(mock_db, monkeypatch):
    async def fake_bucket(db, name):
        return _bucket()

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
            resp = await client.get(
                "/alice/hello.txt",
                params={
                    "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
                    "X-Amz-Credential": "AKIATESTACCESS1/20200101/us-east-1/s3/aws4_request",
                    "X-Amz-Date": "20200101T000000Z",
                    "X-Amz-Expires": "1",
                    "X-Amz-SignedHeaders": "host",
                    "X-Amz-Signature": "deadbeef",
                },
            )
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_create_presigned_url_contains_signature():
    url = create_presigned_url(
        method="PUT",
        bucket="b",
        key="k/x",
        access_key="AK",
        secret_key="SK",
        host="localhost:8000",
        expires_in=60,
    )
    qs = parse_qs(urlparse(url).query)
    assert qs["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert "X-Amz-Signature" in qs
    assert int(qs["X-Amz-Expires"][0]) == 60


def test_presign_expiry_one_sided():
    past = (datetime.now(timezone.utc) - timedelta(seconds=120)).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/alice/hello.txt",
        "raw_path": b"/alice/hello.txt",
        "query_string": (
            f"X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Date={past}&X-Amz-Expires=60"
            "&X-Amz-Signature=deadbeef"
        ).encode(),
        "headers": [],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    request = Request(scope)
    assert _presign_still_valid(request) is False

    fresh = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scope["query_string"] = (
        f"X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Date={fresh}&X-Amz-Expires=3600"
        "&X-Amz-Signature=deadbeef"
    ).encode()
    request = Request(scope)
    assert _presign_still_valid(request) is True
