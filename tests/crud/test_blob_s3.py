import pytest

from datetime import datetime

from app.core.config import DATABASE_NAME
from app.crud.blob import crud_create_blob, crud_delete_blob, crud_list_blobs_for_s3
from app.models.blob import BlobInCreate


@pytest.mark.asyncio
async def test_delete_blob_returns_doc(mock_db):
    await crud_create_blob(
        mock_db, BlobInCreate(path="a.txt", file="f1", size=1, message_id=9), "b1"
    )
    deleted = await crud_delete_blob(mock_db, "b1", "a.txt")
    assert deleted is not None
    assert deleted.path == "a.txt"
    assert deleted.message_id == 9
    assert await crud_delete_blob(mock_db, "b1", "a.txt") is None


@pytest.mark.asyncio
async def test_create_blob_update_sets_datetime_updated_at(mock_db):
    first = await crud_create_blob(
        mock_db, BlobInCreate(path="u.txt", file="f1", size=1), "b1"
    )
    second = await crud_create_blob(
        mock_db,
        BlobInCreate(path="u.txt", file="f2", size=2),
        "b1",
        update=True,
    )
    assert isinstance(second.updated_at, datetime)
    assert second.file == "f2"
    row = await mock_db[DATABASE_NAME]["blobs"].find_one(
        {"bucket_name": "b1", "path": "u.txt"}
    )
    assert isinstance(row["updated_at"], datetime)
    assert first.path == "u.txt"


@pytest.mark.asyncio
async def test_list_prefix_and_start_after(mock_db):
    for path in ["a/1", "a/2", "b/1"]:
        await crud_create_blob(
            mock_db, BlobInCreate(path=path, file=path, size=1), "b1"
        )
    rows = await crud_list_blobs_for_s3(
        mock_db, "b1", prefix="a/", start_after="a/1", max_keys=10
    )
    assert [row.path for row in rows] == ["a/2"]


@pytest.mark.asyncio
async def test_list_respects_max_keys(mock_db):
    for index in range(5):
        path = f"p/{index}"
        await crud_create_blob(
            mock_db, BlobInCreate(path=path, file=path, size=1), "b1"
        )
    rows = await crud_list_blobs_for_s3(mock_db, "b1", prefix="p/", max_keys=2)
    assert len(rows) == 2
    assert [row.path for row in rows] == ["p/0", "p/1"]
