import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_database
from app.main import app
from app.models.blob import BlobInDb
from app.models.bucket import Bucket
from app.models.user import User, UserInDb


def _bucket():
    owner = User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )
    return Bucket(name="alice", owner=owner, size=0)


@pytest.mark.asyncio
async def test_list_objects_v2_prefix(mock_db, monkeypatch):
    blobs = [
        BlobInDb(path="a/1", file="a/1", size=1, bucket_name="alice"),
        BlobInDb(path="a/2", file="a/2", size=1, bucket_name="alice"),
        BlobInDb(path="b/1", file="b/1", size=1, bucket_name="alice"),
    ]

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_list(db, bucket_name, prefix="", start_after="", max_keys=1000):
        rows = [b for b in blobs if b.path.startswith(prefix) and b.path > start_after]
        rows.sort(key=lambda item: item.path)
        return rows[:max_keys]

    monkeypatch.setattr(
        "app.s3.handlers.list_objects.crud_get_bucket_by_name", fake_bucket
    )
    monkeypatch.setattr(
        "app.s3.handlers.list_objects.authorize_request_for_bucket", fake_verify
    )
    monkeypatch.setattr(
        "app.s3.handlers.list_objects.crud_list_blobs_for_s3", fake_list
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/alice", params={"list-type": "2", "prefix": "a/"})
            assert resp.status_code == 200
            assert "<Key>a/1</Key>" in resp.text
            assert "<Key>a/2</Key>" in resp.text
            assert "<Key>b/1</Key>" not in resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_objects_v2_continuation(mock_db, monkeypatch):
    blobs = [
        BlobInDb(path="a/1", file="a/1", size=1, bucket_name="alice"),
        BlobInDb(path="a/2", file="a/2", size=1, bucket_name="alice"),
        BlobInDb(path="b/1", file="b/1", size=1, bucket_name="alice"),
    ]

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    async def fake_list(db, bucket_name, prefix="", start_after="", max_keys=1000):
        rows = [b for b in blobs if b.path.startswith(prefix) and b.path > start_after]
        rows.sort(key=lambda item: item.path)
        return rows[:max_keys]

    monkeypatch.setattr(
        "app.s3.handlers.list_objects.crud_get_bucket_by_name", fake_bucket
    )
    monkeypatch.setattr(
        "app.s3.handlers.list_objects.authorize_request_for_bucket", fake_verify
    )
    monkeypatch.setattr(
        "app.s3.handlers.list_objects.crud_list_blobs_for_s3", fake_list
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            page1 = await client.get(
                "/alice", params={"list-type": "2", "max-keys": "1"}
            )
            assert page1.status_code == 200
            assert "<IsTruncated>true</IsTruncated>" in page1.text
            assert "<NextContinuationToken>a/1</NextContinuationToken>" in page1.text
            page2 = await client.get(
                "/alice",
                params={
                    "list-type": "2",
                    "max-keys": "1",
                    "continuation-token": "a/1",
                },
            )
            assert page2.status_code == 200
            assert "<Key>a/2</Key>" in page2.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_buckets(mock_db, monkeypatch):
    from app.s3.auth import AccessIdentity

    async def fake_identity(db, request, body=None):
        return AccessIdentity(
            access_key_id="AKIATESTACCESS1",
            secret_key="secretkeysecret",
            owner_username="alice",
            role="owner",
            buckets=None,
            is_primary=True,
        )

    async def fake_resolve(db, request, body=None):
        return UserInDb(
            username="alice",
            email="alice@example.com",
            access_key_id="AKIATESTACCESS1",
            secret_key="secretkeysecret",
        )

    async def fake_buckets(db, filters):
        return [_bucket()]

    monkeypatch.setattr(
        "app.s3.handlers.list_buckets.resolve_identity_from_request", fake_identity
    )
    monkeypatch.setattr(
        "app.s3.handlers.list_buckets.resolve_user_from_request", fake_resolve
    )
    monkeypatch.setattr(
        "app.s3.handlers.list_buckets.crud_get_all_buckets", fake_buckets
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            assert resp.status_code == 200
            assert "<Name>alice</Name>" in resp.text
            assert "ListAllMyBucketsResult" in resp.text
    finally:
        app.dependency_overrides.clear()
