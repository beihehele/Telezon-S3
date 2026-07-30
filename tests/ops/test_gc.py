from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import DATABASE_NAME
from app.ops.gc import _is_confirmed_object_gone, _sample_dead_blobs, run_gc_once
from app.storage.errors import (
    StorageObjectGoneError,
    StorageThrottleError,
    StorageUnavailableError,
)


@pytest.mark.asyncio
async def test_gc_aborts_stale_multipart_and_expired_shares(mock_db, monkeypatch):
    from app.db import mongodb

    mongodb.db.client = mock_db

    old = datetime.now(timezone.utc) - timedelta(days=2)
    await mock_db[DATABASE_NAME]["multipart_uploads"].insert_one(
        {
            "upload_id": "up-old",
            "bucket": "alice",
            "key": "big.bin",
            "content_type": "application/octet-stream",
            "owner_access_key": "AKIATESTACCESS1",
            "initiated_at": old,
        }
    )
    await mock_db[DATABASE_NAME]["multipart_parts"].insert_one(
        {
            "upload_id": "up-old",
            "part_number": 1,
            "etag": '"x"',
            "size": 3,
            "file_id": "f1",
            "message_id": 99,
        }
    )
    await mock_db[DATABASE_NAME]["shares"].insert_one(
        {
            "token": "tok",
            "bucket": "alice",
            "key": "a.txt",
            "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
            "download_count": 0,
            "owner_username": "alice",
        }
    )

    deleted = []

    class FakeStorage:
        async def delete_message(self, message_id, **kwargs):
            deleted.append(message_id)
            return True

    async def no_bucket(db, name):
        return None

    monkeypatch.setattr("app.ops.gc.storage", FakeStorage())
    monkeypatch.setattr("app.ops.gc.crud_get_bucket_by_name", no_bucket)
    monkeypatch.setattr("app.ops.gc.GC_MULTIPART_MAX_AGE_SECONDS", 3600)
    monkeypatch.setattr("app.ops.gc.GC_ORPHAN_SAMPLE_SIZE", 0)

    result = await run_gc_once()
    assert result["multipart_aborted"] == 1
    assert result["shares_deleted"] == 1
    assert result["pending_tg_cleared"] == 0
    assert result["dead_blobs_removed"] == 0
    assert result["trash_purged"] == 0
    assert deleted == [99]
    assert await mock_db[DATABASE_NAME]["multipart_uploads"].find_one({}) is None


def test_gone_detection_markers():
    assert _is_confirmed_object_gone(StorageObjectGoneError("missing"))
    assert _is_confirmed_object_gone(RuntimeError("FILE_ID_INVALID"))
    assert not _is_confirmed_object_gone(StorageThrottleError("limited"))
    assert not _is_confirmed_object_gone(RuntimeError("connection reset"))


@pytest.mark.asyncio
async def test_orphan_gc_skips_transient_errors(mock_db, monkeypatch):
    await mock_db[DATABASE_NAME]["blobs"].insert_one(
        {
            "path": "keep.txt",
            "file": "fid-live",
            "bucket_name": "alice",
            "size": 1,
        }
    )

    class ThrottledStorage:
        async def get_file(self, file_id: str):
            raise StorageUnavailableError("client down")

    monkeypatch.setattr("app.ops.gc.storage", ThrottledStorage())
    monkeypatch.setattr("app.ops.gc.GC_ORPHAN_SAMPLE_SIZE", 10)

    removed = await _sample_dead_blobs(mock_db)
    assert removed == 0
    assert await mock_db[DATABASE_NAME]["blobs"].find_one({"path": "keep.txt"})


@pytest.mark.asyncio
async def test_orphan_gc_removes_only_confirmed_gone(mock_db, monkeypatch):
    await mock_db[DATABASE_NAME]["blobs"].insert_one(
        {
            "path": "gone.txt",
            "file": "fid-gone",
            "bucket_name": "alice",
            "size": 1,
        }
    )
    await mock_db[DATABASE_NAME]["blobs"].insert_one(
        {
            "path": "weird.txt",
            "file": "fid-weird",
            "bucket_name": "alice",
            "size": 1,
        }
    )

    class SelectiveStorage:
        async def get_file(self, file_id: str):
            if file_id == "fid-gone":
                raise StorageObjectGoneError("FILE_ID_INVALID")
            raise RuntimeError("timeout talking to telegram")

    monkeypatch.setattr("app.ops.gc.storage", SelectiveStorage())
    monkeypatch.setattr("app.ops.gc.GC_ORPHAN_SAMPLE_SIZE", 10)

    removed = await _sample_dead_blobs(mock_db)
    assert removed == 1
    assert await mock_db[DATABASE_NAME]["blobs"].find_one({"path": "gone.txt"}) is None
    assert await mock_db[DATABASE_NAME]["blobs"].find_one({"path": "weird.txt"})
