"""Simple Bearer upload for scripts/Shortcuts (non-SigV4)."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from app.core.config import MAX_UPLOAD_BYTES
from app.crud.blob import crud_create_blob, crud_get_all_blobs
from app.crud.bucket import crud_get_bucket_by_name
from app.crud.user import crud_get_user_by_access_key_id
from app.db.mongodb import get_database
from app.models.blob import BlobFilterParams, BlobInCreate
from app.s3.body import BodyTooLarge, read_body_capped
from app.storage import storage
from app.storage.disk_cache import cache_delete
from app.storage.errors import StorageThrottleError, StorageUnavailableError

router = APIRouter(prefix="/upload", tags=["SimpleUpload"])


class UploadQuery(BaseModel):
    bucket: str = Field(min_length=1)
    key: str = Field(min_length=1)


async def _user_from_bearer(authorization: str | None, db):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer credentials")
    token = authorization.split(" ", 1)[1].strip()
    if ":" not in token:
        raise HTTPException(
            status_code=401, detail="Bearer must be access_key_id:secret_key"
        )
    access_key, secret_key = token.split(":", 1)
    user = await crud_get_user_by_access_key_id(db, access_key)
    if not user or user.secret_key != secret_key:
        raise HTTPException(status_code=403, detail="Invalid credentials")
    return user


@router.put("/")
async def simple_upload(
    request: Request,
    bucket: str,
    key: str,
    authorization: str | None = Header(default=None),
    db: AsyncIOMotorClient = Depends(get_database),
):
    user = await _user_from_bearer(authorization, db)
    bucket_row = await crud_get_bucket_by_name(db, bucket)
    if not bucket_row:
        raise HTTPException(status_code=404, detail="Bucket not found")
    if bucket_row.owner.username != user.username:
        raise HTTPException(status_code=403, detail="Not bucket owner")

    try:
        body = await read_body_capped(request, MAX_UPLOAD_BYTES)
    except BodyTooLarge as exc:
        raise HTTPException(
            status_code=413, detail=f"Entity too large: {exc.size}"
        ) from None

    existing = await crud_get_all_blobs(
        db, BlobFilterParams(path=key, bucket_name=bucket)
    )
    update = len(existing) > 0
    previous = existing[0] if update else None

    try:
        put_result = await storage.put_file(
            body,
            key,
            chat_id=getattr(bucket_row, "telegram_chat_id", None),
            topic_id=getattr(bucket_row, "telegram_topic_id", None),
        )
    except StorageThrottleError as exc:
        raise HTTPException(status_code=503, detail="SlowDown") from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail="ServiceUnavailable") from exc

    blob = BlobInCreate(
        path=key,
        file=put_result.file_id,
        content_type=request.headers.get("content-type", "application/octet-stream"),
        size=len(body),
        message_id=put_result.message_id,
        parts=None,
    )
    await crud_create_blob(db, blob, bucket, update)
    cache_delete(bucket, key)

    if previous:
        from app.s3.object_lifecycle import retire_previous_version

        await retire_previous_version(
            db,
            previous,
            bucket_name=bucket,
            chat_id=getattr(bucket_row, "telegram_chat_id", None),
            reason="bearer_overwrite",
        )

    return JSONResponse(
        {
            "ok": True,
            "bucket": bucket,
            "key": key,
            "size": len(body),
            "etag": f'"{put_result.file_id}-{len(body)}"',
        }
    )
