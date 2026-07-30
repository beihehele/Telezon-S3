from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_404_NOT_FOUND

from app.crud.user import crud_get_user_by_username
from app.db.mappers import bucket_from_rows, bucket_in_db_from_row
from app.db.tables import BlobRow, BucketRow, UserRow
from app.models.bucket import (
    Bucket,
    BucketFilterParams,
    BucketInCreate,
    BucketInDb,
    BucketInUpdate,
)
from app.models.user import User


async def _bucket_total_size(db: AsyncSession, bucket_name: str) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(BlobRow.size), 0)).where(
            BlobRow.bucket_name == bucket_name
        )
    )
    total = result.scalar_one()
    return int(total or 0)


async def _load_bucket_with_owner(
    db: AsyncSession, bucket_row: BucketRow
) -> Bucket:
    owner = await db.get(UserRow, bucket_row.owner_username)
    if not owner:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Owner {bucket_row.owner_username} not found",
        )
    size = await _bucket_total_size(db, bucket_row.name)
    return bucket_from_rows(bucket_row, owner, size)


async def crud_get_all_buckets(
    db: AsyncSession, filters: BucketFilterParams
) -> List[Bucket]:
    stmt = select(BucketRow)
    if filters.name:
        names = filters.name.replace(", ", ",").split(",")
        stmt = stmt.where(BucketRow.name.in_(names))
    if filters.owner_username:
        owners = filters.owner_username.replace(", ", ",").split(",")
        stmt = stmt.where(BucketRow.owner_username.in_(owners))
    stmt = stmt.offset(filters.offset).limit(filters.limit)
    result = await db.execute(stmt)
    buckets: List[Bucket] = []
    for bucket_row in result.scalars().all():
        buckets.append(await _load_bucket_with_owner(db, bucket_row))
    return buckets


async def crud_get_bucket_by_name(
    db: AsyncSession, name: str
) -> Optional[Bucket]:
    row = await db.get(BucketRow, name)
    if not row:
        return None
    return await _load_bucket_with_owner(db, row)


async def crud_create_bucket(
    db: AsyncSession, bucket: BucketInCreate, current_user: User
) -> BucketInDb:
    data_bucket = BucketInDb(**bucket.model_dump())
    data_bucket.owner_username = bucket.owner_username or current_user.username

    now = datetime.now(timezone.utc)
    row = BucketRow(
        name=data_bucket.name,
        owner_username=data_bucket.owner_username,
        is_public=data_bucket.is_public,
        telegram_chat_id=data_bucket.telegram_chat_id,
        telegram_topic_id=data_bucket.telegram_topic_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return bucket_in_db_from_row(row)


async def crud_update_bucket(
    db: AsyncSession, bucket_name: str, bucket: BucketInUpdate
) -> BucketInDb:
    row = await db.get(BucketRow, bucket_name)
    if not row:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Bucket {bucket_name} not found",
        )

    if bucket.owner_username is not None:
        user_bucket = await crud_get_user_by_username(db, bucket.owner_username)
        if not user_bucket:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Username {bucket.owner_username} not found",
            )
        row.owner_username = bucket.owner_username

    if bucket.is_public is not None:
        row.is_public = bucket.is_public

    if "telegram_chat_id" in bucket.model_fields_set:
        row.telegram_chat_id = bucket.telegram_chat_id or None

    if "telegram_topic_id" in bucket.model_fields_set:
        row.telegram_topic_id = bucket.telegram_topic_id

    row.updated_at = datetime.now(timezone.utc)
    await db.flush()

    refreshed = await crud_get_bucket_by_name(db, bucket_name)
    if not refreshed:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Bucket {bucket_name} not found",
        )
    return BucketInDb(
        name=refreshed.name,
        owner_username=refreshed.owner.username,
        is_public=getattr(refreshed, "is_public", False),
        telegram_chat_id=getattr(refreshed, "telegram_chat_id", None),
        telegram_topic_id=getattr(refreshed, "telegram_topic_id", None),
        created_at=getattr(refreshed, "created_at", None),
        updated_at=getattr(refreshed, "updated_at", None),
    )


async def crud_delete_bucket(db: AsyncSession, bucket_name: str) -> bool:
    row = await db.get(BucketRow, bucket_name)
    if not row:
        return False
    await db.delete(row)
    await db.flush()
    return True


async def crud_bucket_has_objects(db: AsyncSession, bucket_name: str) -> bool:
    result = await db.execute(
        select(BlobRow.id).where(BlobRow.bucket_name == bucket_name).limit(1)
    )
    return result.scalar_one_or_none() is not None
