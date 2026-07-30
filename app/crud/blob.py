from datetime import datetime, timezone
from typing import List

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import DATABASE_NAME
from app.models.blob import Blob, BlobFilterParams, BlobInCreate, BlobInDb

COLLECTION = "blobs"

aggregate_bucket = {
    "$lookup": {
        "from": "buckets",
        "localField": "bucket_name",
        "foreignField": "name",
        "as": "bucket",
    }
}

aggregate_owner = {
    "$lookup": {
        "from": "users",
        "localField": "bucket.owner_username",
        "foreignField": "username",
        "as": "owner",
    }
}


async def crud_get_all_blobs(
    db: AsyncIOMotorClient, filters: BlobFilterParams
) -> List[Blob]:
    blobs: List[Blob] = []
    base_query = {}

    if filters.path:
        paths = filters.path.replace(", ", ",").split(",")
        base_query["path"] = {"$in": paths}

    if filters.bucket_name:
        bucket_names = filters.bucket_name.replace(", ", ",").split(",")
        base_query["bucket_name"] = {"$in": bucket_names}

    blob_docs = db[DATABASE_NAME][COLLECTION].aggregate(
        [
            {"$match": base_query},
            {"$limit": filters.offset + filters.limit},
            {"$skip": filters.offset},
            aggregate_bucket,
            aggregate_owner,
            {"$unwind": {"path": "$bucket"}},
            {"$unwind": {"path": "$owner"}},
        ]
    )

    async for row in blob_docs:
        blobs.append(Blob(**row))

    return blobs


async def crud_create_blob(
    db: AsyncIOMotorClient, blob: BlobInCreate, bucket_name: str, update: bool = False
) -> BlobInDb:
    data_blob = BlobInDb(**blob.model_dump())
    data_blob.bucket_name = bucket_name

    if not update:
        row = await db[DATABASE_NAME][COLLECTION].insert_one(data_blob.model_dump())

        data_blob.created_at = ObjectId(row.inserted_id).generation_time
        data_blob.updated_at = ObjectId(row.inserted_id).generation_time
    else:
        now = datetime.now(timezone.utc)
        data_blob.updated_at = now
        await db[DATABASE_NAME][COLLECTION].update_one(
            {"path": data_blob.path, "bucket_name": bucket_name},
            {"$set": data_blob.model_dump()},
        )

    return data_blob


async def crud_delete_blob(
    db: AsyncIOMotorClient, bucket_name: str, path: str
) -> BlobInDb | None:
    row = await db[DATABASE_NAME][COLLECTION].find_one_and_delete(
        {"bucket_name": bucket_name, "path": path}
    )
    if not row:
        return None
    return BlobInDb(**row)


async def crud_list_blobs_for_s3(
    db: AsyncIOMotorClient,
    bucket_name: str,
    prefix: str = "",
    start_after: str = "",
    max_keys: int = 1000,
) -> List[BlobInDb]:
    query: dict = {"bucket_name": bucket_name}
    path_query: dict = {}

    if prefix:
        path_query["$regex"] = f"^{_escape_regex(prefix)}"

    if start_after:
        path_query["$gt"] = start_after

    if path_query:
        query["path"] = path_query

    cursor = (
        db[DATABASE_NAME][COLLECTION]
        .find(query)
        .sort("path", 1)
        .limit(max_keys)
    )

    blobs: List[BlobInDb] = []
    async for row in cursor:
        blobs.append(BlobInDb(**row))
    return blobs


def _escape_regex(value: str) -> str:
    specials = r"\.^$|*+?()[]{}\\"
    return "".join("\\" + ch if ch in specials else ch for ch in value)
