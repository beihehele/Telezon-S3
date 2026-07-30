from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.crud.blob import crud_create_blob
from app.crud.credential import crud_create_credential
from app.db.session import get_database
from app.main import app
from app.models.blob import BlobInCreate
from app.models.credential import ROLE_READONLY, ROLE_READWRITE, CredentialInCreate
from app.s3.xml import rollup_with_delimiter


def test_rollup_delimiter_common_prefixes():
    from app.models.blob import BlobInDb

    blobs = [
        BlobInDb(path="docs/a.txt", file="f1", size=1),
        BlobInDb(path="docs/b.txt", file="f2", size=1),
        BlobInDb(path="docs/nested/c.txt", file="f3", size=1),
        BlobInDb(path="readme.txt", file="f4", size=1),
    ]
    contents, prefixes, truncated, _ = rollup_with_delimiter(
        blobs, prefix="", delimiter="/", max_keys=10
    )
    assert [b.path for b in contents] == ["readme.txt"]
    assert prefixes == ["docs/"]
    assert truncated is False


@pytest.mark.asyncio
async def test_list_v2_delimiter(mock_db, monkeypatch):
    from app.models.bucket import Bucket
    from app.models.user import User

    owner = User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )

    async def fake_bucket(db, name):
        return Bucket(name=name, owner=owner, size=0)

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    for path in ["docs/a.txt", "docs/b.txt", "readme.txt"]:
        await crud_create_blob(
            mock_db, BlobInCreate(path=path, file=path, size=1), "alice"
        )

    monkeypatch.setattr(
        "app.s3.handlers.list_objects.crud_get_bucket_by_name", fake_bucket
    )
    monkeypatch.setattr(
        "app.s3.handlers.list_objects.authorize_request_for_bucket", fake_verify
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/alice?list-type=2&delimiter=/")
            assert resp.status_code == 200
            assert "CommonPrefixes" in resp.text
            assert "<Prefix>docs/</Prefix>" in resp.text
            assert "readme.txt" in resp.text
            assert "x-amz-request-id" in resp.headers
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_versioning_stub(mock_db, monkeypatch):
    from app.models.bucket import Bucket
    from app.models.user import User

    owner = User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )

    async def fake_bucket(db, name):
        return Bucket(name=name, owner=owner, size=0)

    async def fake_verify(bucket, request, db=None, body=None):
        return "ok"

    monkeypatch.setattr(
        "app.s3.handlers.list_objects.crud_get_bucket_by_name", fake_bucket
    )
    monkeypatch.setattr(
        "app.s3.handlers.list_objects.authorize_request_for_bucket", fake_verify
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/alice?versioning")
            assert resp.status_code == 200
            assert "VersioningConfiguration" in resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_credential_rbac_roles(mock_db):
    from app.s3.auth import AccessIdentity, resolve_identity
    from app.models.bucket import Bucket
    from app.models.user import User

    from app.crud.user import crud_create_user
    from app.models.user import UserInCreate

    await crud_create_user(
        mock_db,
        UserInCreate(
            username="alice",
            email="alice@example.com",
            password="secret",
        ),
    )
    from app.db.tables import UserRow

    row = await mock_db.get(UserRow, "alice")
    row.access_key_id = "PRIMARYKEY000001"
    row.secret_key = "primarysecret0001"
    await mock_db.flush()
    ro = await crud_create_credential(
        mock_db,
        "alice",
        CredentialInCreate(role=ROLE_READONLY, buckets=["alice"], label="ro"),
    )
    rw = await crud_create_credential(
        mock_db,
        "alice",
        CredentialInCreate(role=ROLE_READWRITE, buckets=[], label="rw"),
    )

    identity_ro = await resolve_identity(mock_db, ro.access_key_id)
    identity_rw = await resolve_identity(mock_db, rw.access_key_id)
    identity_owner = await resolve_identity(mock_db, "PRIMARYKEY000001")
    assert identity_ro is not None and identity_ro.role == ROLE_READONLY
    assert identity_rw is not None and identity_rw.buckets is None
    assert identity_owner is not None and identity_owner.is_primary

    bucket = Bucket(
        name="alice",
        owner=User(
            username="alice",
            email="alice@example.com",
            access_key_id="PRIMARYKEY000001",
            secret_key="primarysecret0001",
        ),
        size=0,
    )
    assert identity_ro.can_read(bucket) is True
    assert identity_ro.can_write(bucket) is False
    assert identity_rw.can_write(bucket) is True
    assert identity_rw.can_create_bucket() is True
    assert identity_ro.can_create_bucket() is False
    assert isinstance(ro.created_at, datetime) or ro.created_at is None
