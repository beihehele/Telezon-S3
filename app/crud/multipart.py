import secrets
from datetime import datetime, timezone
from typing import List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.sql_like import escape_like_prefix
from app.db.tables import MultipartPartRow, MultipartUploadRow


async def crud_create_multipart_upload(
    db: AsyncSession,
    *,
    bucket: str,
    key: str,
    content_type: str,
    owner_access_key: str,
) -> str:
    upload_id = secrets.token_urlsafe(24)
    row = MultipartUploadRow(
        upload_id=upload_id,
        bucket=bucket,
        key=key,
        content_type=content_type,
        owner_access_key=owner_access_key,
        initiated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return upload_id


async def crud_get_multipart_upload(db: AsyncSession, upload_id: str) -> dict | None:
    row = await db.get(MultipartUploadRow, upload_id)
    if not row:
        return None
    return _upload_to_dict(row)


async def crud_delete_multipart_upload(db: AsyncSession, upload_id: str) -> None:
    await db.execute(
        delete(MultipartPartRow).where(MultipartPartRow.upload_id == upload_id)
    )
    row = await db.get(MultipartUploadRow, upload_id)
    if row:
        await db.delete(row)
    await db.flush()


async def crud_get_part(
    db: AsyncSession, upload_id: str, part_number: int
) -> dict | None:
    result = await db.execute(
        select(MultipartPartRow).where(
            MultipartPartRow.upload_id == upload_id,
            MultipartPartRow.part_number == part_number,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return _part_to_dict(row)


async def crud_upsert_part(
    db: AsyncSession,
    *,
    upload_id: str,
    part_number: int,
    etag: str,
    size: int,
    file_id: str,
    message_id: int | None,
) -> dict | None:
    previous = await crud_get_part(db, upload_id, part_number)
    result = await db.execute(
        select(MultipartPartRow).where(
            MultipartPartRow.upload_id == upload_id,
            MultipartPartRow.part_number == part_number,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = MultipartPartRow(
            upload_id=upload_id,
            part_number=part_number,
            etag=etag,
            size=size,
            file_id=file_id,
            message_id=message_id,
        )
        db.add(row)
    else:
        row.etag = etag
        row.size = size
        row.file_id = file_id
        row.message_id = message_id
    await db.flush()
    return previous


async def crud_list_parts(db: AsyncSession, upload_id: str) -> List[dict]:
    result = await db.execute(
        select(MultipartPartRow)
        .where(MultipartPartRow.upload_id == upload_id)
        .order_by(MultipartPartRow.part_number.asc())
    )
    return [_part_to_dict(row) for row in result.scalars().all()]


async def crud_get_parts_for_complete(
    db: AsyncSession, upload_id: str, part_numbers: list[int]
) -> List[dict]:
    result = await db.execute(
        select(MultipartPartRow)
        .where(
            MultipartPartRow.upload_id == upload_id,
            MultipartPartRow.part_number.in_(part_numbers),
        )
        .order_by(MultipartPartRow.part_number.asc())
    )
    return [_part_to_dict(row) for row in result.scalars().all()]


async def crud_list_multipart_uploads(
    db: AsyncSession,
    *,
    bucket: str,
    prefix: str = "",
    key_marker: str = "",
    upload_id_marker: str = "",
    max_uploads: int = 1000,
) -> list[dict]:
    stmt = select(MultipartUploadRow).where(MultipartUploadRow.bucket == bucket)
    if prefix:
        stmt = stmt.where(
            MultipartUploadRow.key.like(
                f"{escape_like_prefix(prefix)}%", escape="\\"
            )
        )
    stmt = stmt.order_by(
        MultipartUploadRow.key.asc(), MultipartUploadRow.upload_id.asc()
    ).limit(max(1, min(max_uploads, 1000)) + 1)
    result = await db.execute(stmt)
    rows = [_upload_to_dict(row) for row in result.scalars().all()]
    if key_marker:
        filtered = []
        for row in rows:
            key = row.get("key", "")
            upload_id = row.get("upload_id", "")
            if key < key_marker:
                continue
            if key == key_marker and upload_id <= upload_id_marker:
                continue
            filtered.append(row)
        rows = filtered
    return rows


async def crud_list_stale_multipart_uploads(
    db: AsyncSession, cutoff: datetime, limit: int = 100
) -> list[dict]:
    result = await db.execute(
        select(MultipartUploadRow)
        .where(MultipartUploadRow.initiated_at < cutoff)
        .limit(limit)
    )
    return [_upload_to_dict(row) for row in result.scalars().all()]


def _upload_to_dict(row: MultipartUploadRow) -> dict:
    return {
        "upload_id": row.upload_id,
        "bucket": row.bucket,
        "key": row.key,
        "content_type": row.content_type,
        "owner_access_key": row.owner_access_key,
        "initiated_at": row.initiated_at,
    }


def _part_to_dict(row: MultipartPartRow) -> dict:
    return {
        "upload_id": row.upload_id,
        "part_number": row.part_number,
        "etag": row.etag,
        "size": row.size,
        "file_id": row.file_id,
        "message_id": row.message_id,
    }
