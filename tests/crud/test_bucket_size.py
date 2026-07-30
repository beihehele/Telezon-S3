import pytest

from app.crud.blob import crud_create_blob
from app.crud.bucket import crud_create_bucket, crud_get_bucket_by_name
from app.crud.user import crud_create_user
from app.models.blob import BlobInCreate
from app.models.bucket import BucketInCreate
from app.models.user import User, UserInCreate


@pytest.mark.asyncio
async def test_bucket_size_sums_without_loading_blob_docs(mock_db):
    owner_db = await crud_create_user(
        mock_db,
        UserInCreate(username="alice", email="alice@example.com", password="secret"),
    )
    owner = User(**owner_db.model_dump())
    await crud_create_bucket(
        mock_db, BucketInCreate(name="alice", owner_username="alice"), owner
    )
    await crud_create_blob(
        mock_db, BlobInCreate(path="a.txt", file="f1", size=10), "alice"
    )
    await crud_create_blob(
        mock_db, BlobInCreate(path="b.txt", file="f2", size=15), "alice"
    )

    bucket = await crud_get_bucket_by_name(mock_db, "alice")
    assert bucket is not None
    assert bucket.size == 25
    assert bucket.owner.username == "alice"
