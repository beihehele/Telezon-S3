from typing import List, Optional

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.status import HTTP_404_NOT_FOUND

from app.core.config import DATABASE_NAME
from app.crud.user import crud_get_user_by_username
from app.models.bucket import (
    Bucket,
    BucketFilterParams,
    BucketInCreate,
    BucketInDb,
    BucketInUpdate,
)
from app.models.user import User

COLLECTION = "buckets"

aggregate_owner = {
    "$lookup": {
        "from": "users",
        "localField": "owner_username",
        "foreignField": "username",
        "as": "owner",
    },
}

project = {
    "$project": {
        "name": 1,
        "owner": 1,
        "created_at": 1,
        "updated_at": 1,
        "is_public": {"$ifNull": ["$is_public", False]},
        "telegram_chat_id": 1,
        "telegram_topic_id": 1,
    }
}


async def _bucket_total_size(db: AsyncIOMotorClient, bucket_name: str) -> int:
    """Sum object sizes without embedding blob documents on the bucket row."""
    cursor = db[DATABASE_NAME]["blobs"].aggregate(
        [
            {"$match": {"bucket_name": bucket_name}},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$size", 0]}}}},
        ]
    )
    async for row in cursor:
        return int(row.get("total") or 0)
    return 0


async def crud_get_all_buckets(
    db: AsyncIOMotorClient, filters: BucketFilterParams
) -> List[Bucket]:
    buckets: List[Bucket] = []
    base_query = {}

    if filters.name:
        names = filters.name.replace(", ", ",").split(",")
        base_query["name"] = {"$in": names}

    if filters.owner_username:
        owners = filters.owner_username.replace(", ", ",").split(",")
        base_query["owner_username"] = {"$in": owners}

    bucket_docs = db[DATABASE_NAME][COLLECTION].aggregate(
        [
            {"$match": base_query},
            {"$limit": filters.offset + filters.limit},
            {"$skip": filters.offset},
            aggregate_owner,
            {"$unwind": {"path": "$owner"}},
            project,
        ]
    )

    async for row in bucket_docs:
        size = await _bucket_total_size(db, row["name"])
        buckets.append(Bucket(**{**row, "size": size}))

    return buckets


async def crud_get_bucket_by_name(
    db: AsyncIOMotorClient, name: str
) -> Optional[Bucket]:
    base_query = {"name": {"$in": [name]}}
    bucket_docs = db[DATABASE_NAME][COLLECTION].aggregate(
        [
            {"$match": base_query},
            aggregate_owner,
            {"$unwind": {"path": "$owner"}},
            project,
        ]
    )

    async for row in bucket_docs:
        size = await _bucket_total_size(db, name)
        return Bucket(**{**row, "size": size})
    return None


async def crud_create_bucket(
    db: AsyncIOMotorClient, bucket: BucketInCreate, current_user: User
) -> BucketInDb:
    data_bucket = BucketInDb(**bucket.model_dump())
    data_bucket.owner_username = bucket.owner_username or current_user.username

    row = await db[DATABASE_NAME][COLLECTION].insert_one(data_bucket.model_dump())

    data_bucket.created_at = ObjectId(row.inserted_id).generation_time
    data_bucket.updated_at = ObjectId(row.inserted_id).generation_time

    return data_bucket


async def crud_update_bucket(
    db: AsyncIOMotorClient, bucket_name: str, bucket: BucketInUpdate
) -> BucketInDb:
    simple_bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not simple_bucket:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Bucket {bucket_name} not found",
        )

    updates: dict = {}

    if bucket.owner_username is not None:
        user_bucket = await crud_get_user_by_username(db, bucket.owner_username)
        if not user_bucket:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Username {bucket.owner_username} not found",
            )
        updates["owner_username"] = bucket.owner_username

    if bucket.is_public is not None:
        updates["is_public"] = bucket.is_public

    if "telegram_chat_id" in bucket.model_fields_set:
        updates["telegram_chat_id"] = bucket.telegram_chat_id or None

    if "telegram_topic_id" in bucket.model_fields_set:
        updates["telegram_topic_id"] = bucket.telegram_topic_id

    if updates:
        await db[DATABASE_NAME][COLLECTION].update_one(
            {"name": bucket_name}, {"$set": updates}
        )

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


async def crud_delete_bucket(db: AsyncIOMotorClient, bucket_name: str) -> bool:
    result = await db[DATABASE_NAME][COLLECTION].delete_one({"name": bucket_name})
    return result.deleted_count > 0


async def crud_bucket_has_objects(db: AsyncIOMotorClient, bucket_name: str) -> bool:
    row = await db[DATABASE_NAME]["blobs"].find_one(
        {"bucket_name": bucket_name}, projection={"_id": 1}
    )
    return row is not None
