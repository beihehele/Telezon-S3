import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import objects as objects_mod
from app.core.token import get_current_user
from app.crud.blob import crud_create_blob
from app.db.session import get_database
from app.main import app
from app.models.blob import BlobInCreate
from app.models.bucket import Bucket
from app.models.user import User
from tests.conftest import override_get_database


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
async def test_list_objects_rest(mock_db, monkeypatch):
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="docs/readme.txt", file="f1", size=10, content_type="text/plain"),
        "alice",
    )
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="docs/sub/x.bin", file="f2", size=5),
        "alice",
    )

    async def fake_bucket(db, name):
        return _bucket() if name == "alice" else None

    monkeypatch.setattr(objects_mod, "crud_get_bucket_by_name", fake_bucket)
    app.dependency_overrides[get_database] = override_get_database(mock_db)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/buckets/alice/objects",
                params={"prefix": "docs/", "delimiter": "/"},
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["prefix"] == "docs/"
            keys = {item["key"] for item in body["contents"]}
            assert "docs/readme.txt" in keys
            assert "docs/sub/" in body["common_prefixes"] or any(
                p.startswith("docs/sub") for p in body["common_prefixes"]
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_object_metadata_and_delete(mock_db, monkeypatch):
    monkeypatch.setattr("app.s3.object_lifecycle.ENABLE_TRASH", True)
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="gone.txt", file="f1", size=1, message_id=9),
        "alice",
    )

    async def fake_bucket(db, name):
        return _bucket() if name == "alice" else None

    monkeypatch.setattr(objects_mod, "crud_get_bucket_by_name", fake_bucket)
    app.dependency_overrides[get_database] = override_get_database(mock_db)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            meta = await client.get(
                "/api/v1/buckets/alice/objects/gone.txt/metadata",
                headers={"Authorization": "Bearer test"},
            )
            assert meta.status_code == 200
            body = meta.json()
            assert body["key"] == "gone.txt"
            assert body["size"] == 1

            deleted = await client.delete(
                "/api/v1/buckets/alice/objects/gone.txt",
                headers={"Authorization": "Bearer test"},
            )
            assert deleted.status_code == 204

            meta2 = await client.get(
                "/api/v1/buckets/alice/objects/gone.txt/metadata",
                headers={"Authorization": "Bearer test"},
            )
            assert meta2.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_batch_delete_objects(mock_db, monkeypatch):
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="a.txt", file="f1", size=1),
        "alice",
    )
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="b.txt", file="f2", size=1),
        "alice",
    )

    async def fake_bucket(db, name):
        return _bucket() if name == "alice" else None

    monkeypatch.setattr(objects_mod, "crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.object_lifecycle.ENABLE_TRASH", True)
    app.dependency_overrides[get_database] = override_get_database(mock_db)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/buckets/alice/objects/batch-delete",
                json={"keys": ["a.txt", "b.txt", "missing.txt"]},
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert set(body["deleted"]) == {"a.txt", "b.txt"}
            assert len(body["errors"]) == 1
            assert body["errors"][0]["key"] == "missing.txt"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rename_object_rest(mock_db, monkeypatch):
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="old/name.txt", file="f1", size=3),
        "alice",
    )

    async def fake_bucket(db, name):
        return _bucket() if name == "alice" else None

    monkeypatch.setattr(objects_mod, "crud_get_bucket_by_name", fake_bucket)
    app.dependency_overrides[get_database] = override_get_database(mock_db)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/buckets/alice/objects/rename",
                json={"from": "old/name.txt", "to": "new/name.txt"},
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 200
            assert resp.json()["to"] == "new/name.txt"
            meta = await client.get(
                "/api/v1/buckets/alice/objects/new/name.txt/metadata",
                headers={"Authorization": "Bearer test"},
            )
            assert meta.status_code == 200
    finally:
        app.dependency_overrides.clear()
