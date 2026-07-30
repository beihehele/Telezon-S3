import pytest

from app.models.blob import Blob, BlobPart
from app.models.bucket import Bucket
from app.models.user import User
from app.s3.blob_io import load_blob_bytes, safe_content_disposition


def _owner():
    return User(
        username="alice",
        email="alice@example.com",
        access_key_id="AKIATESTACCESS1",
        secret_key="secretkeysecret",
    )


def test_safe_content_disposition_strips_injection():
    header = safe_content_disposition('evil\r\nX-Injected: 1".txt')
    assert "\r" not in header
    assert "\n" not in header
    assert "filename=" in header


def test_safe_content_disposition_utf8_filename():
    header = safe_content_disposition("文件夹/报告.pdf")
    assert "filename*=" in header
    assert "UTF-8" in header


@pytest.mark.asyncio
async def test_load_blob_bytes_multipart(fake_storage, monkeypatch):
    monkeypatch.setattr("app.s3.blob_io.storage", fake_storage)
    r1 = await fake_storage.put_file(b"aa", "p1")
    r2 = await fake_storage.put_file(b"bb", "p2")
    blob = Blob(
        path="big.bin",
        file="multipart:upload",
        content_type="application/octet-stream",
        size=4,
        parts=[
            BlobPart(part_number=1, file_id=r1.file_id, size=2),
            BlobPart(part_number=2, file_id=r2.file_id, size=2),
        ],
        bucket=Bucket(name="alice", owner=_owner(), size=0),
        owner=_owner(),
    )
    data = await load_blob_bytes(blob)
    assert data == b"aabb"
