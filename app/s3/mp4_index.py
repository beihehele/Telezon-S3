"""MP4 `moov` atom offset cache for faster Range seeks (0.14)."""

from __future__ import annotations

import struct

from app.s3.blob_io import load_blob_byte_range
from app.models.blob import BlobInDb
from app.storage.disk_cache import cache_get, cache_put

_MOOV_PREFIX = "moov:"


def _moov_cache_key(bucket: str, key: str) -> str:
    return f"{_MOOV_PREFIX}{bucket}:{key}"


def _parse_boxes(data: bytes, start: int = 0) -> tuple[int | None, int]:
    """Return (moov_offset, bytes_scanned) within data starting at start offset in file."""
    offset = 0
    moov_at: int | None = None
    while offset + 8 <= len(data):
        size = struct.unpack(">I", data[offset : offset + 4])[0]
        box_type = data[offset + 4 : offset + 8]
        if size < 8:
            break
        if box_type == b"moov":
            moov_at = start + offset
            break
        offset += size
    return moov_at, offset


async def ensure_mp4_moov_offset(
    blob: BlobInDb, bucket: str, key: str, *, probe_bytes: int = 8 * 1024 * 1024
) -> int | None:
    cached = cache_get(bucket, _moov_cache_key(bucket, key))
    if isinstance(cached, int):
        return cached
    ct = (blob.content_type or "").lower()
    if "mp4" not in ct and not key.lower().endswith(".mp4"):
        return None
    total = int(blob.size or 0)
    if total <= 0:
        return None
    end = min(total - 1, probe_bytes - 1)
    head = await load_blob_byte_range(blob, 0, end)
    moov_at, _ = _parse_boxes(head, 0)
    if moov_at is None and total > probe_bytes:
        tail_start = max(0, total - probe_bytes)
        tail = await load_blob_byte_range(blob, tail_start, total - 1)
        moov_at, _ = _parse_boxes(tail, tail_start)
    if moov_at is not None:
        cache_put(bucket, _moov_cache_key(bucket, key), moov_at)
    return moov_at
