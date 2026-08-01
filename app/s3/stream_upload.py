"""Stream request bodies to disk and verify SigV4 without buffering the full payload."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.models.bucket import Bucket
from app.s3.auth import AUTH_OK, authorize_request_for_bucket

SHA_MISMATCH = "sha_mismatch"
# Signature must be checked after the body is streamed when no payload hash header is sent.
DEFER_STREAM_AUTH = "defer"


def content_sha256_header(request: Request) -> str | None:
    return request.headers.get("x-amz-content-sha256") or request.headers.get(
        "X-Amz-Content-SHA256"
    )


def payload_sha256_mismatch(header_sha: str | None, sha256_hex: str) -> bool:
    return bool(
        header_sha
        and header_sha != "UNSIGNED-PAYLOAD"
        and header_sha.lower() != sha256_hex
    )


async def authorize_before_stream(
    bucket: Bucket,
    request: Request,
    db: AsyncSession,
) -> str:
    """Verify SigV4 before reading the body when the client declares the payload hash."""
    header_sha = content_sha256_header(request)
    if header_sha == "UNSIGNED-PAYLOAD":
        return await authorize_request_for_bucket(bucket, request, db, body=b"")
    if header_sha:
        return await authorize_request_for_bucket(
            bucket,
            request,
            db,
            body=b"",
            payload_sha256_hex=header_sha.lower(),
        )
    return DEFER_STREAM_AUTH


async def finalize_streamed_payload(
    bucket: Bucket,
    request: Request,
    db: AsyncSession,
    *,
    sha256_hex: str,
    staging_path: Path,
    pre_authenticated: bool,
) -> str:
    """After streaming, confirm payload hash and verify SigV4 if it was deferred."""
    header_sha = content_sha256_header(request)
    if payload_sha256_mismatch(header_sha, sha256_hex):
        staging_path.unlink(missing_ok=True)
        return SHA_MISMATCH
    if pre_authenticated:
        return AUTH_OK
    auth = await authorize_request_for_bucket(
        bucket, request, db, body=b"", payload_sha256_hex=sha256_hex
    )
    if auth != AUTH_OK:
        staging_path.unlink(missing_ok=True)
    return auth
