"""Byte-range reads for multipart objects (0.14)."""

from __future__ import annotations

import io
import re
from urllib.parse import quote

from app.models.blob import Blob, BlobInDb, BlobPart
from app.s3.sse import decrypt_sse_c
from app.storage import storage
from app.storage.tg_context import part_telegram_context, single_telegram_context

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_content_disposition(key: str) -> str:
    base = key.rsplit("/", 1)[-1]
    base = "".join(ch for ch in base if ord(ch) >= 32 and ch not in '"\\\r\n')
    ascii_name = _SAFE_FILENAME.sub("_", base) or "download"
    utf8_name = quote(base or "download", safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"


def inline_content_disposition(key: str) -> str:
    base = key.rsplit("/", 1)[-1]
    base = "".join(ch for ch in base if ord(ch) >= 32 and ch not in '"\\\r\n')
    ascii_name = _SAFE_FILENAME.sub("_", base) or "file"
    utf8_name = quote(base or "file", safe="")
    return f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"


def bytes_as_stream(data: bytes):
    return io.BytesIO(data)


def part_byte_spans(parts: list[BlobPart]) -> list[tuple[int, int, BlobPart]]:
    """Inclusive byte spans (start, end) per part, ordered by part_number."""
    ordered = sorted(parts, key=lambda p: p.part_number)
    spans: list[tuple[int, int, BlobPart]] = []
    offset = 0
    for part in ordered:
        size = int(part.size or 0)
        if size <= 0:
            continue
        start = offset
        end = offset + size - 1
        spans.append((start, end, part))
        offset += size
    return spans


async def load_blob_byte_range(
    blob: Blob | BlobInDb,
    start: int,
    end: int,
    *,
    sse_key: str | None = None,
) -> bytes:
    """Load inclusive byte range [start, end] from a blob."""
    if start < 0 or end < start:
        raise ValueError("invalid range")
    want_len = end - start + 1
    if blob.encrypted:
        raw = await load_blob_bytes(blob, sse_key=sse_key)
        return raw[start : end + 1]

    if blob.parts:
        spans = part_byte_spans(blob.parts)
        chunks: list[bytes] = []
        remaining = want_len
        cursor = start
        for pstart, pend, part in spans:
            if pend < start or pstart > end:
                continue
            slice_start = max(cursor, pstart) - pstart
            slice_end = min(end, pend) - pstart
            chat_id, mid = part_telegram_context(blob, part)
            file_obj = await storage.get_file(
                part.file_id, chat_id=chat_id, message_id=mid
            )
            data = file_obj.read() if hasattr(file_obj, "read") else file_obj
            if isinstance(data, memoryview):
                data = data.tobytes()
            if isinstance(data, str):
                data = data.encode()
            part_slice = data[slice_start : slice_end + 1]
            chunks.append(part_slice)
            remaining -= len(part_slice)
            cursor = min(end, pend) + 1
            if remaining <= 0:
                break
        return b"".join(chunks)

    chat_id, mid = single_telegram_context(blob)
    file_obj = await storage.get_file(blob.file, chat_id=chat_id, message_id=mid)
    data = file_obj.read() if hasattr(file_obj, "read") else file_obj
    if isinstance(data, memoryview):
        data = data.tobytes()
    if isinstance(data, str):
        data = data.encode()
    return data[start : end + 1]


async def load_blob_bytes(blob: Blob | BlobInDb, *, sse_key: str | None = None) -> bytes:
    if blob.encrypted:
        if not sse_key:
            raise ValueError("SSE customer key required")
        raw = await _read_single(blob.file)
        return decrypt_sse_c(
            raw,
            sse_key,
            blob.sse_nonce or "",
            blob.sse_tag or "",
            aad=_aad(blob),
        )

    if blob.parts:
        total = int(blob.size or 0)
        if total <= 0:
            spans = part_byte_spans(blob.parts)
            if not spans:
                return b""
            total = spans[-1][1] + 1
        return await load_blob_byte_range(blob, 0, total - 1)

    if str(blob.file).startswith("multipart:"):
        raise ValueError("Multipart object missing parts metadata")

    chat_id, mid = single_telegram_context(blob)
    return await _read_single(blob.file, chat_id=chat_id, message_id=mid)


async def _read_single(
    file_id: str,
    *,
    chat_id: str | None = None,
    message_id: int | None = None,
) -> bytes:
    file_obj = await storage.get_file(
        file_id, chat_id=chat_id, message_id=message_id
    )
    data = file_obj.read() if hasattr(file_obj, "read") else file_obj
    if isinstance(data, memoryview):
        data = data.tobytes()
    if isinstance(data, str):
        data = data.encode()
    return data


def _aad(blob: Blob) -> bytes:
    bucket = getattr(blob, "bucket_name", None) or getattr(
        getattr(blob, "bucket", None), "name", ""
    )
    return f"{bucket}/{blob.path}".encode("utf-8")
