"""Shared ListObjectsV2 logic for S3 XML and JWT object REST."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.blob import crud_list_blobs_for_s3
from app.s3.xml import object_etag, rollup_with_delimiter


def _fmt_iso(value) -> str:
    if value is None:
        return ""
    try:
        return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        return str(value)


async def list_objects_page(
    db: AsyncSession,
    bucket_name: str,
    *,
    prefix: str = "",
    delimiter: str = "",
    continuation_token: str | None = None,
    start_after: str = "",
    max_keys: int = 1000,
) -> tuple[list[dict], list[str], bool, str | None]:
    """Return (contents dicts, common_prefixes, is_truncated, next_token)."""
    max_keys = max(1, min(max_keys, 1000))
    effective_start = continuation_token or start_after or ""

    if delimiter:
        fetch_limit = min(5000, max(max_keys * 20, max_keys + 1))
        rows = await crud_list_blobs_for_s3(
            db,
            bucket_name,
            prefix=prefix,
            start_after=effective_start,
            max_keys=fetch_limit,
        )
        page, common_prefixes, rolled_truncated, last_key = rollup_with_delimiter(
            rows, prefix=prefix, delimiter=delimiter, max_keys=max_keys
        )
        is_truncated = rolled_truncated or (
            len(rows) >= fetch_limit and last_key is not None
        )
        next_token = last_key if is_truncated else None
        blobs = page
    else:
        rows = await crud_list_blobs_for_s3(
            db,
            bucket_name,
            prefix=prefix,
            start_after=effective_start,
            max_keys=max_keys + 1,
        )
        is_truncated = len(rows) > max_keys
        blobs = rows[:max_keys]
        common_prefixes = []
        next_token = blobs[-1].path if is_truncated and blobs else None

    contents = [
        {
            "key": blob.path,
            "size": int(blob.size or 0),
            "last_modified": _fmt_iso(
                getattr(blob, "updated_at", None) or getattr(blob, "created_at", None)
            ),
            "etag": object_etag(blob),
            "content_type": blob.content_type or "application/octet-stream",
        }
        for blob in blobs
    ]
    return contents, common_prefixes, is_truncated, next_token
