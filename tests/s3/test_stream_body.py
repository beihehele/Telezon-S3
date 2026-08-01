import hashlib

import pytest
from starlette.requests import Request

from app.s3.body import BodyTooLarge, stream_body_to_file


async def _request_with_body(data: bytes) -> Request:
    scope = {
        "type": "http",
        "method": "PUT",
        "path": "/",
        "headers": [],
    }
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": data, "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_stream_body_to_file_hashes_and_size(tmp_path):
    data = b"hello multipart staging"
    path = tmp_path / "part-1"
    request = await _request_with_body(data)
    size, md5_hex, sha_hex = await stream_body_to_file(request, path, max_bytes=1024)
    assert size == len(data)
    assert md5_hex == hashlib.md5(data).hexdigest()
    assert sha_hex == hashlib.sha256(data).hexdigest()
    assert path.read_bytes() == data


@pytest.mark.asyncio
async def test_stream_body_to_file_enforces_cap(tmp_path):
    request = await _request_with_body(b"too long")
    path = tmp_path / "part-1"
    with pytest.raises(BodyTooLarge):
        await stream_body_to_file(request, path, max_bytes=3)
    assert not path.exists()
