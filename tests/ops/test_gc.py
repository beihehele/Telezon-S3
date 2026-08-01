from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.crud.multipart import crud_upsert_part
from app.crud.share import crud_create_share
from app.db import session as db_session
from app.db.tables import MultipartUploadRow, ShareRow
from app.models.share import ShareInCreate
from app.ops.gc import _sample_dead_blobs, run_gc_once
from app.storage.errors import StorageObjectGoneError, StorageThrottleError


class _SessionCM:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        await self._session.commit()


def _patch_session_factory(mock_db, monkeypatch):
    class _Maker:
        def __call__(self):
            return _SessionCM(mock_db)

    maker = _Maker()
    monkeypatch.setattr(db_session, "async_session_factory", maker)


@pytest.mark.asyncio
async def test_gc_aborts_stale_multipart_and_expired_shares(mock_db, monkeypatch):
    _patch_session_factory(mock_db, monkeypatch)

    old = datetime.now(timezone.utc) - timedelta(days=2)
    upload_id = "up-old"
    mock_db.add(
        MultipartUploadRow(
            upload_id=upload_id,
            bucket="alice",
            key="big.bin",
            content_type="application/octet-stream",
            owner_access_key="AKIATESTACCESS1",
            initiated_at=old,
        )
    )
    await crud_upsert_part(
        mock_db,
        upload_id=upload_id,
        part_number=1,
        etag='"x"',
        size=3,
        file_id="f1",
        message_id=99,
    )
    share = await crud_create_share(
        mock_db,
        ShareInCreate(bucket="alice", key="a.txt", expires_in=3600, password=""),
        "alice",
    )
    share_row = await mock_db.get(ShareRow, share.token)
    share_row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await mock_db.flush()

    async def fake_delete_message(message_id, **kwargs):
        return True

    monkeypatch.setattr("app.ops.gc.storage.delete_message", fake_delete_message)

    result = await run_gc_once()
    assert result["multipart_aborted"] == 1
    assert result["shares_deleted"] >= 1
    rows = (await mock_db.execute(select(MultipartUploadRow))).scalars().all()
    assert not rows


@pytest.mark.asyncio
async def test_orphan_gc_skips_transient_errors(mock_db, monkeypatch):
    from app.crud.blob import crud_create_blob
    from app.models.blob import BlobInCreate
    from tests.conftest import find_blob_row

    await crud_create_blob(
        mock_db, BlobInCreate(path="keep.txt", file="f1", size=1), "b1"
    )
    await mock_db.commit()

    async def raise_throttle(file_id):
        raise StorageThrottleError("slow")

    monkeypatch.setattr("app.ops.gc.storage.get_file", raise_throttle)

    removed = await _sample_dead_blobs(mock_db)
    assert removed == 0
    assert await find_blob_row(mock_db, "b1", "keep.txt") is not None


@pytest.mark.asyncio
async def test_orphan_gc_removes_only_confirmed_gone(mock_db, monkeypatch):
    from app.crud.blob import crud_create_blob
    from app.models.blob import BlobInCreate
    from tests.conftest import find_blob_row

    await crud_create_blob(
        mock_db, BlobInCreate(path="gone.txt", file="f1", size=1), "b1"
    )
    await crud_create_blob(
        mock_db, BlobInCreate(path="weird.txt", file="f2", size=1), "b1"
    )
    await mock_db.commit()

    async def get_file(file_id):
        if file_id == "f1":
            raise StorageObjectGoneError("gone")
        raise RuntimeError("unknown")

    monkeypatch.setattr("app.ops.gc.storage.get_file", get_file)
    monkeypatch.setattr("app.ops.gc.GC_ORPHAN_SAMPLE_SIZE", 10)

    removed = await _sample_dead_blobs(mock_db)
    assert removed == 1
    assert await find_blob_row(mock_db, "b1", "gone.txt") is None
    assert await find_blob_row(mock_db, "b1", "weird.txt") is not None
