from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

from app.api.auth.utils import is_admin
from app.core.token import get_current_user
from app.crud.blob import crud_create_blob, crud_get_all_blobs
from app.crud.bucket import crud_get_all_buckets, crud_get_bucket_by_name
from app.crud.trash import (
    crud_delete_trash,
    crud_delete_trash_for_bucket,
    crud_get_trash,
    crud_list_trash,
)
from app.db.mongodb import get_database
from app.models.blob import BlobFilterParams, BlobInCreate
from app.models.bucket import BucketFilterParams
from app.models.trash import TrashEmptyRequest, TrashPublic, TrashRestoreRequest
from app.models.user import User
from app.s3.object_lifecycle import purge_trash_item

router = APIRouter(prefix="/trash", tags=["Trash"])


def _to_public(item) -> TrashPublic:
    return TrashPublic(
        trash_id=item.trash_id,
        bucket=item.bucket_name,
        key=item.path,
        size=item.size,
        content_type=item.content_type,
        deleted_at=item.deleted_at,
        expires_at=item.expires_at,
        reason=item.reason,
    )


async def _owned_bucket_names(db, user: User) -> list[str]:
    if is_admin(user):
        rows = await crud_get_all_buckets(
            db, BucketFilterParams(limit=1000, offset=0)
        )
        return [b.name for b in rows]
    rows = await crud_get_all_buckets(
        db,
        BucketFilterParams(owner_username=user.username, limit=1000, offset=0),
    )
    return [b.name for b in rows]


async def _assert_can_manage_trash(db, user: User, bucket_name: str) -> None:
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not bucket:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Bucket not found")
    if not is_admin(user) and bucket.owner.username != user.username:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Not bucket owner")


@router.get("/", response_model=list[TrashPublic])
async def list_trash(
    bucket: str = "",
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    if bucket:
        await _assert_can_manage_trash(db, current_user, bucket)
        rows = await crud_list_trash(
            db, bucket_name=bucket, limit=limit, offset=offset
        )
    else:
        owned = await _owned_bucket_names(db, current_user)
        rows = await crud_list_trash(
            db, owner_buckets=owned, limit=limit, offset=offset
        )
    return [_to_public(row) for row in rows]


@router.post("/restore", response_model=TrashPublic)
async def restore_trash(
    payload: TrashRestoreRequest,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    item = await crud_get_trash(db, payload.trash_id)
    if not item:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Trash item not found")
    await _assert_can_manage_trash(db, current_user, item.bucket_name)

    existing = await crud_get_all_blobs(
        db, BlobFilterParams(path=item.path, bucket_name=item.bucket_name)
    )
    if existing:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail="Live object already exists at this key; delete or rename first",
        )

    await crud_create_blob(
        db,
        BlobInCreate(
            path=item.path,
            file=item.file,
            content_type=item.content_type,
            size=item.size,
            message_id=item.message_id,
            parts=item.parts,
            sse_nonce=item.sse_nonce,
            sse_tag=item.sse_tag,
            encrypted=item.encrypted,
        ),
        item.bucket_name,
        update=False,
    )
    await crud_delete_trash(db, item.trash_id)
    return _to_public(item)


@router.delete("/{trash_id}")
async def permanent_delete_trash(
    trash_id: str,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    item = await crud_get_trash(db, trash_id)
    if not item:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Trash item not found")
    await _assert_can_manage_trash(db, current_user, item.bucket_name)

    bucket = await crud_get_bucket_by_name(db, item.bucket_name)
    chat_id = getattr(bucket, "telegram_chat_id", None) if bucket else None
    removed = await crud_delete_trash(db, trash_id)
    if removed:
        await purge_trash_item(db, removed, chat_id=chat_id)
    return {"ok": True}


@router.post("/empty")
async def empty_trash(
    payload: TrashEmptyRequest,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    await _assert_can_manage_trash(db, current_user, payload.bucket)
    bucket = await crud_get_bucket_by_name(db, payload.bucket)
    chat_id = getattr(bucket, "telegram_chat_id", None) if bucket else None
    items = await crud_delete_trash_for_bucket(db, payload.bucket)
    for item in items:
        await purge_trash_item(db, item, chat_id=chat_id)
    return {"ok": True, "purged": len(items)}
