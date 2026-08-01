import pytest
from httpx import ASGITransport, AsyncClient

from app.crud.blob import crud_create_blob, crud_get_all_blobs
from app.crud.trash import crud_list_trash
from app.db.session import get_database
from app.main import app
from app.models.blob import BlobFilterParams, BlobInCreate
from app.models.bucket import Bucket
from app.models.user import User
from app.s3.object_lifecycle import delete_live_object
from tests.conftest import find_blob_row


def _bucket():
    return Bucket(
        name="alice",
        owner=User(
            username="alice",
            email="alice@example.com",
            access_key_id="AKIATESTACCESS1",
            secret_key="secretkeysecret",
        ),
        size=0,
    )


@pytest.mark.asyncio
async def test_soft_delete_moves_to_trash(mock_db, monkeypatch):
    monkeypatch.setattr("app.s3.object_lifecycle.ENABLE_TRASH", True)
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="a.txt", file="f1", size=3, message_id=7),
        "alice",
    )

    deleted = await delete_live_object(
        mock_db, bucket_name="alice", key="a.txt", reason="test"
    )
    assert deleted is not None
    assert deleted.message_id == 7

    live = await crud_get_all_blobs(
        mock_db, BlobFilterParams(path="a.txt", bucket_name="alice")
    )
    assert live == []

    trash = await crud_list_trash(mock_db, bucket_name="alice")
    assert len(trash) == 1
    assert trash[0].path == "a.txt"
    assert trash[0].message_id == 7


@pytest.mark.asyncio
async def test_soft_delete_inserts_trash_before_live_delete(mock_db, monkeypatch):
    monkeypatch.setattr("app.s3.object_lifecycle.ENABLE_TRASH", True)
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="order.txt", file="f2", size=2, message_id=8),
        "alice",
    )

    calls: list[str] = []
    from app.crud import trash as trash_mod

    real_insert = trash_mod.crud_insert_trash_from_blob

    async def tracking_insert(*args, **kwargs):
        calls.append("insert_trash")
        live = await find_blob_row(mock_db, "alice", "order.txt")
        assert live, "live row must still exist when trash is inserted"
        return await real_insert(*args, **kwargs)

    async def tracking_delete(db, bucket_name, path):
        calls.append("delete_live")
        from app.crud.blob import crud_delete_blob as real_delete

        return await real_delete(db, bucket_name, path)

    monkeypatch.setattr(
        "app.s3.object_lifecycle.crud_insert_trash_from_blob", tracking_insert
    )
    monkeypatch.setattr("app.s3.object_lifecycle.crud_delete_blob", tracking_delete)

    deleted = await delete_live_object(
        mock_db, bucket_name="alice", key="order.txt", reason="order"
    )
    assert deleted is not None
    assert calls == ["insert_trash", "delete_live"]


@pytest.mark.asyncio
async def test_soft_delete_via_s3_api(mock_db, monkeypatch):
    monkeypatch.setattr("app.s3.object_lifecycle.ENABLE_TRASH", True)

    async def fake_bucket(db, name):
        return _bucket()

    async def fake_verify(bucket, request, db=None, body=None, **kwargs):
        return "ok"

    await crud_create_blob(
        mock_db,
        BlobInCreate(path="hello.txt", file="f1", size=5, message_id=42),
        "alice",
    )

    monkeypatch.setattr("app.s3.handlers.object.crud_get_bucket_by_name", fake_bucket)
    monkeypatch.setattr("app.s3.handlers.object.authorize_request_for_bucket", fake_verify)
    monkeypatch.setattr("app.s3.handlers.object.precheck_request_for_bucket", fake_verify)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_database] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/alice/hello.txt")
            assert resp.status_code == 204
    finally:
        app.dependency_overrides.clear()

    trash = await crud_list_trash(mock_db, bucket_name="alice")
    assert len(trash) == 1
    assert await find_blob_row(mock_db, "alice", "hello.txt") is None


@pytest.mark.asyncio
async def test_restore_from_trash(mock_db, monkeypatch):
    monkeypatch.setattr("app.s3.object_lifecycle.ENABLE_TRASH", True)
    await crud_create_blob(
        mock_db,
        BlobInCreate(path="r.txt", file="f9", size=2, message_id=9),
        "alice",
    )
    await delete_live_object(mock_db, bucket_name="alice", key="r.txt")
    trash = await crud_list_trash(mock_db, bucket_name="alice")
    assert len(trash) == 1

    from app.crud.trash import crud_delete_trash, crud_get_trash
    from app.crud.blob import crud_create_blob as create_blob
    from app.models.blob import BlobInCreate as BIC

    item = trash[0]
    existing = await crud_get_all_blobs(
        mock_db, BlobFilterParams(path=item.path, bucket_name=item.bucket_name)
    )
    assert existing == []
    await create_blob(
        mock_db,
        BIC(
            path=item.path,
            file=item.file,
            content_type=item.content_type,
            size=item.size,
            message_id=item.message_id,
        ),
        item.bucket_name,
    )
    await crud_delete_trash(mock_db, item.trash_id)
    assert await crud_get_trash(mock_db, item.trash_id) is None
    row = await find_blob_row(mock_db, "alice", "r.txt")
    assert row is not None
    assert row.message_id == 9
