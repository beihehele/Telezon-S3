import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TRASH_RETENTION_SECONDS
from app.db.mappers import parts_to_json, trash_from_row
from app.db.tables import TrashRow
from app.models.blob import BlobInDb
from app.models.trash import TrashItem


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def crud_insert_trash_from_blob(
    db: AsyncSession,
    blob: BlobInDb,
    *,
    deleted_by: str = "",
    reason: str = "delete",
    retention_seconds: int | None = None,
) -> TrashItem:
    retention = (
        TRASH_RETENTION_SECONDS if retention_seconds is None else retention_seconds
    )
    now = _now()
    item = TrashItem(
        trash_id=uuid.uuid4().hex,
        bucket_name=blob.bucket_name,
        path=blob.path,
        file=blob.file or "",
        content_type=blob.content_type or "",
        size=int(blob.size or 0),
        message_id=blob.message_id,
        parts=blob.parts,
        sse_nonce=blob.sse_nonce,
        sse_tag=blob.sse_tag,
        encrypted=bool(blob.encrypted),
        deleted_at=now,
        expires_at=now + timedelta(seconds=max(60, retention)),
        deleted_by=deleted_by,
        reason=reason[:64],
        created_at=now,
        updated_at=now,
    )
    row = TrashRow(
        trash_id=item.trash_id,
        bucket_name=item.bucket_name,
        path=item.path,
        file=item.file,
        content_type=item.content_type,
        size=item.size,
        message_id=item.message_id,
        parts=parts_to_json(item.parts),
        sse_nonce=item.sse_nonce,
        sse_tag=item.sse_tag,
        encrypted=item.encrypted,
        deleted_at=item.deleted_at,
        expires_at=item.expires_at,
        deleted_by=item.deleted_by,
        reason=item.reason,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return item


async def crud_get_trash(db: AsyncSession, trash_id: str) -> Optional[TrashItem]:
    row = await db.get(TrashRow, trash_id)
    if not row:
        return None
    return trash_from_row(row)


async def crud_list_trash(
    db: AsyncSession,
    *,
    bucket_name: str = "",
    owner_buckets: List[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> List[TrashItem]:
    stmt = select(TrashRow)
    if bucket_name:
        stmt = stmt.where(TrashRow.bucket_name == bucket_name)
    elif owner_buckets is not None:
        stmt = stmt.where(TrashRow.bucket_name.in_(owner_buckets))
    stmt = (
        stmt.order_by(TrashRow.deleted_at.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 1000)))
    )
    result = await db.execute(stmt)
    return [trash_from_row(row) for row in result.scalars().all()]


async def crud_delete_trash(
    db: AsyncSession, trash_id: str
) -> Optional[TrashItem]:
    row = await db.get(TrashRow, trash_id)
    if not row:
        return None
    item = trash_from_row(row)
    await db.delete(row)
    await db.flush()
    return item


async def crud_delete_trash_for_bucket(
    db: AsyncSession, bucket_name: str
) -> List[TrashItem]:
    result = await db.execute(
        select(TrashRow).where(TrashRow.bucket_name == bucket_name)
    )
    items = [trash_from_row(row) for row in result.scalars().all()]
    if items:
        await db.execute(delete(TrashRow).where(TrashRow.bucket_name == bucket_name))
        await db.flush()
    return items


async def crud_list_expired_trash(
    db: AsyncSession, *, limit: int = 100
) -> List[TrashItem]:
    now = _now()
    result = await db.execute(
        select(TrashRow).where(TrashRow.expires_at < now).limit(limit)
    )
    return [trash_from_row(row) for row in result.scalars().all()]
