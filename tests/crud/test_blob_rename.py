import pytest

from app.crud.tg_refs import count_message_id_refs
from app.db.path_digest import blob_path_digest
from app.db.tables import BlobRow
from app.crud.blob import crud_rename_blob


@pytest.mark.asyncio
async def test_rename_blob_updates_path(mock_db):
    mock_db.add(
        BlobRow(
            bucket_name="b",
            path="old.txt",
            path_digest=blob_path_digest("b", "old.txt"),
            file="f1",
            size=1,
        )
    )
    await mock_db.flush()
    row = await crud_rename_blob(mock_db, "b", "old.txt", "new.txt")
    assert row.path == "new.txt"


@pytest.mark.asyncio
async def test_message_id_refcount_live_row(mock_db):
    mock_db.add(
        BlobRow(
            bucket_name="b",
            path="a",
            path_digest=blob_path_digest("b", "a"),
            message_id=42,
            file="f",
            size=1,
        )
    )
    await mock_db.flush()
    assert await count_message_id_refs(mock_db, 42) == 1
