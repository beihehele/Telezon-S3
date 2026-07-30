import secrets
from datetime import datetime, timezone
from typing import List

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import DATABASE_NAME

UPLOADS = "multipart_uploads"
PARTS = "multipart_parts"


async def crud_create_multipart_upload(
    db: AsyncIOMotorClient,
    *,
    bucket: str,
    key: str,
    content_type: str,
    owner_access_key: str,
) -> str:
    upload_id = secrets.token_urlsafe(24)
    await db[DATABASE_NAME][UPLOADS].insert_one(
        {
            "upload_id": upload_id,
            "bucket": bucket,
            "key": key,
            "content_type": content_type,
            "owner_access_key": owner_access_key,
            "initiated_at": datetime.now(timezone.utc),
        }
    )
    return upload_id


async def crud_get_multipart_upload(db: AsyncIOMotorClient, upload_id: str) -> dict | None:
    return await db[DATABASE_NAME][UPLOADS].find_one({"upload_id": upload_id})


async def crud_delete_multipart_upload(db: AsyncIOMotorClient, upload_id: str) -> None:
    await db[DATABASE_NAME][UPLOADS].delete_one({"upload_id": upload_id})
    await db[DATABASE_NAME][PARTS].delete_many({"upload_id": upload_id})


async def crud_get_part(
    db: AsyncIOMotorClient, upload_id: str, part_number: int
) -> dict | None:
    return await db[DATABASE_NAME][PARTS].find_one(
        {"upload_id": upload_id, "part_number": part_number}
    )


async def crud_upsert_part(
    db: AsyncIOMotorClient,
    *,
    upload_id: str,
    part_number: int,
    etag: str,
    size: int,
    file_id: str,
    message_id: int | None,
) -> dict | None:
    """Upsert part; return previous part doc if any (for TG cleanup)."""
    previous = await crud_get_part(db, upload_id, part_number)
    await db[DATABASE_NAME][PARTS].update_one(
        {"upload_id": upload_id, "part_number": part_number},
        {
            "$set": {
                "upload_id": upload_id,
                "part_number": part_number,
                "etag": etag,
                "size": size,
                "file_id": file_id,
                "message_id": message_id,
            }
        },
        upsert=True,
    )
    return previous


async def crud_list_parts(db: AsyncIOMotorClient, upload_id: str) -> List[dict]:
    cursor = db[DATABASE_NAME][PARTS].find({"upload_id": upload_id}).sort(
        "part_number", 1
    )
    return [row async for row in cursor]


async def crud_get_parts_for_complete(
    db: AsyncIOMotorClient, upload_id: str, part_numbers: list[int]
) -> List[dict]:
    cursor = db[DATABASE_NAME][PARTS].find(
        {"upload_id": upload_id, "part_number": {"$in": part_numbers}}
    ).sort("part_number", 1)
    return [row async for row in cursor]


async def crud_list_multipart_uploads(
    db: AsyncIOMotorClient,
    *,
    bucket: str,
    prefix: str = "",
    key_marker: str = "",
    upload_id_marker: str = "",
    max_uploads: int = 1000,
) -> list[dict]:
    query: dict = {"bucket": bucket}
    if prefix:
        query["key"] = {"$regex": f"^{prefix}"}
    cursor = (
        db[DATABASE_NAME][UPLOADS]
        .find(query)
        .sort([("key", 1), ("upload_id", 1)])
        .limit(max(1, min(max_uploads, 1000)) + 1)
    )
    rows = [row async for row in cursor]
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
