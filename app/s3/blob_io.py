import io
import re
from urllib.parse import quote

from app.models.blob import Blob
from app.s3.sse import decrypt_sse_c
from app.storage import storage


_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_content_disposition(key: str) -> str:
    base = key.rsplit("/", 1)[-1]
    base = "".join(ch for ch in base if ord(ch) >= 32 and ch not in '"\\\r\n')
    ascii_name = _SAFE_FILENAME.sub("_", base) or "download"
    utf8_name = quote(base or "download", safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"


async def load_blob_bytes(blob: Blob, *, sse_key: str | None = None) -> bytes:
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
        chunks: list[bytes] = []
        for part in blob.parts:
            chunks.append(await _read_single(part.file_id))
        return b"".join(chunks)

    if str(blob.file).startswith("multipart:"):
        raise ValueError("Multipart object missing parts metadata")

    return await _read_single(blob.file)


async def _read_single(file_id: str) -> bytes:
    file_obj = await storage.get_file(file_id)
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


def bytes_as_stream(data: bytes):
    return io.BytesIO(data)
