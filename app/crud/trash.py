import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import DATABASE_NAME, TRASH_RETENTION_SECONDS
from app.models.blob import BlobInDb
from app.models.trash import TrashItem

COLLECTION = "trash"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def crud_insert_trash_from_blob(
    db: AsyncIOMotorClient,
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
    await db[DATABASE_NAME][COLLECTION].insert_one(item.model_dump())
    return item


async def crud_get_trash(
    db: AsyncIOMotorClient, trash_id: str
) -> Optional[TrashItem]:
    row = await db[DATABASE_NAME][COLLECTION].find_one({"trash_id": trash_id})
    if not row:
        return None
    return TrashItem(**row)


async def crud_list_trash(
    db: AsyncIOMotorClient,
    *,
    bucket_name: str = "",
    owner_buckets: List[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> List[TrashItem]:
    query: dict = {}
    if bucket_name:
        query["bucket_name"] = bucket_name
    elif owner_buckets is not None:
        query["bucket_name"] = {"$in": owner_buckets}

    cursor = (
        db[DATABASE_NAME][COLLECTION]
        .find(query)
        .sort("deleted_at", -1)
        .skip(max(0, offset))
        .limit(max(1, min(limit, 1000)))
    )
    rows: List[TrashItem] = []
    async for row in cursor:
        rows.append(TrashItem(**row))
    return rows


async def crud_delete_trash(
    db: AsyncIOMotorClient, trash_id: str
) -> Optional[TrashItem]:
    row = await db[DATABASE_NAME][COLLECTION].find_one_and_delete(
        {"trash_id": trash_id}
    )
    if not row:
        return None
    return TrashItem(**row)


async def crud_delete_trash_for_bucket(
    db: AsyncIOMotorClient, bucket_name: str
) -> List[TrashItem]:
    cursor = db[DATABASE_NAME][COLLECTION].find({"bucket_name": bucket_name})
    items: List[TrashItem] = []
    async for row in cursor:
        items.append(TrashItem(**row))
    if items:
        await db[DATABASE_NAME][COLLECTION].delete_many({"bucket_name": bucket_name})
    return items


async def crud_list_expired_trash(
    db: AsyncIOMotorClient, *, limit: int = 100
) -> List[TrashItem]:
    now = _now()
    cursor = (
        db[DATABASE_NAME][COLLECTION]
        .find({"expires_at": {"$lt": now}})
        .limit(limit)
    )
    rows: List[TrashItem] = []
    async for row in cursor:
        rows.append(TrashItem(**row))
    return rows
