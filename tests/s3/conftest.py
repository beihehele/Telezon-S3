import pytest

from app.s3.auth import AUTH_OK
from app.s3 import stream_upload


@pytest.fixture(autouse=True)
def _default_stream_upload_auth_ok(monkeypatch):
    """Tests mock handler-level authorize; streamed PUT/UploadPart use stream_upload."""

    async def _before_ok(bucket, request, db):
        return AUTH_OK

    async def _finalize_ok(
        bucket, request, db, *, sha256_hex, staging_path, pre_authenticated
    ):
        return AUTH_OK

    monkeypatch.setattr(stream_upload, "authorize_before_stream", _before_ok)
    monkeypatch.setattr(stream_upload, "finalize_streamed_payload", _finalize_ok)
