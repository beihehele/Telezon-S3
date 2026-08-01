from datetime import datetime, timezone
from typing import List

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mappers import blob_from_row, blob_in_db_from_row, parts_to_json, _albums_to_json
from app.db.path_digest import blob_path_digest
from app.db.sql_like import escape_like_prefix
from app.db.tables import BlobRow, BucketRow, UserRow
from app.models.blob import Blob, BlobFilterParams, BlobInCreate, BlobInDb


async def crud_get_all_blobs(
    db: AsyncSession, filters: BlobFilterParams
) -> List[Blob]:
    stmt = (
        select(BlobRow, BucketRow, UserRow)
        .join(BucketRow, BlobRow.bucket_name == BucketRow.name)
        .join(UserRow, BucketRow.owner_username == UserRow.username)
    )
    if filters.path:
        paths = filters.path.replace(", ", ",").split(",")
        stmt = stmt.where(BlobRow.path.in_(paths))
    if filters.bucket_name:
        bucket_names = filters.bucket_name.replace(", ", ",").split(",")
        stmt = stmt.where(BlobRow.bucket_name.in_(bucket_names))
    stmt = stmt.offset(filters.offset).limit(filters.limit)
    result = await db.execute(stmt)
    blobs: List[Blob] = []
    for blob_row, bucket_row, owner_row in result.all():
        blobs.append(blob_from_row(blob_row, bucket_row, owner_row))
    return blobs


async def crud_create_blob(
    db: AsyncSession, blob: BlobInCreate, bucket_name: str, update: bool = False
) -> BlobInDb:
    data_blob = BlobInDb(**blob.model_dump())
    data_blob.bucket_name = bucket_name
    now = datetime.now(timezone.utc)

    if not update:
        row = BlobRow(
            bucket_name=bucket_name,
            path=data_blob.path,
            path_digest=blob_path_digest(bucket_name, data_blob.path),
            storage_id=data_blob.storage_id,
            telegram_grouped_id=data_blob.telegram_grouped_id,
            telegram_albums=_albums_to_json(data_blob.telegram_albums),
            file=data_blob.file or "",
            content_type=data_blob.content_type or "",
            size=int(data_blob.size or 0),
            message_id=data_blob.message_id,
            parts=parts_to_json(data_blob.parts),
            sse_nonce=data_blob.sse_nonce,
            sse_tag=data_blob.sse_tag,
            encrypted=bool(data_blob.encrypted),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        await db.flush()
        data_blob.created_at = row.created_at
        data_blob.updated_at = row.updated_at
    else:
        data_blob.updated_at = now
        result = await db.execute(
            select(BlobRow).where(
                BlobRow.path == data_blob.path,
                BlobRow.bucket_name == bucket_name,
            )
        )
        row = result.scalar_one()
        row.storage_id = data_blob.storage_id
        row.telegram_grouped_id = data_blob.telegram_grouped_id
        row.telegram_albums = _albums_to_json(data_blob.telegram_albums)
        row.file = data_blob.file or ""
        row.content_type = data_blob.content_type or ""
        row.size = int(data_blob.size or 0)
        row.message_id = data_blob.message_id
        row.parts = parts_to_json(data_blob.parts)
        row.sse_nonce = data_blob.sse_nonce
        row.sse_tag = data_blob.sse_tag
        row.encrypted = bool(data_blob.encrypted)
        row.updated_at = now
        await db.flush()

    return data_blob


async def crud_delete_blob(
    db: AsyncSession, bucket_name: str, path: str
) -> BlobInDb | None:
    result = await db.execute(
        select(BlobRow).where(
            BlobRow.bucket_name == bucket_name,
            BlobRow.path == path,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    doc = blob_in_db_from_row(row)
    await db.delete(row)
    await db.flush()
    return doc


async def crud_list_blobs_for_s3(
    db: AsyncSession,
    bucket_name: str,
    prefix: str = "",
    start_after: str = "",
    max_keys: int = 1000,
) -> List[BlobInDb]:
    stmt = select(BlobRow).where(BlobRow.bucket_name == bucket_name)
    if prefix:
        stmt = stmt.where(
            BlobRow.path.like(f"{escape_like_prefix(prefix)}%", escape="\\")
        )
    if start_after:
        stmt = stmt.where(BlobRow.path > start_after)
    stmt = stmt.order_by(BlobRow.path.asc()).limit(max_keys)
    result = await db.execute(stmt)
    return [blob_in_db_from_row(row) for row in result.scalars().all()]


async def crud_rename_blob(
    db: AsyncSession,
    bucket_name: str,
    old_path: str,
    new_path: str,
) -> BlobInDb:
    if old_path == new_path:
        raise ValueError("paths must differ")
    result = await db.execute(
        select(BlobRow).where(
            BlobRow.bucket_name == bucket_name,
            BlobRow.path == old_path,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise LookupError("source not found")
    conflict = await db.execute(
        select(BlobRow.id).where(
            BlobRow.bucket_name == bucket_name,
            BlobRow.path == new_path,
        )
    )
    if conflict.scalar_one_or_none() is not None:
        raise FileExistsError(new_path)
    row.path = new_path
    row.path_digest = blob_path_digest(bucket_name, new_path)
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return blob_in_db_from_row(row)


async def crud_sample_blobs(db: AsyncSession, limit: int) -> List[BlobInDb]:
    if limit <= 0:
        return []
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else "mysql"
    order = func.rand() if dialect == "mysql" else func.random()
    stmt = select(BlobRow).order_by(order).limit(limit)
    result = await db.execute(stmt)
    return [blob_in_db_from_row(row) for row in result.scalars().all()]
