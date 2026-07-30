"""Soft-delete vs hard-delete policy for live objects."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import ENABLE_TRASH
from app.crud.blob import crud_delete_blob
from app.crud.trash import crud_insert_trash_from_blob
from app.db.mappers import blob_in_db_from_row
from app.db.tables import BlobRow
from app.models.blob import BlobInDb
from app.models.trash import TrashItem
from app.ops.tg_delete import safe_delete_tg_message
from app.storage.disk_cache import cache_delete


def bypass_trash_requested(request: Request | None) -> bool:
    if request is None:
        return False
    value = request.headers.get("x-telezon-bypass-trash", "")
    return value.strip().lower() in {"1", "true", "yes"}


def _as_blob_in_db(live, bucket_name: str, key: str | None = None) -> BlobInDb:
    return BlobInDb(
        path=key or live.path,
        file=getattr(live, "file", "") or "",
        content_type=getattr(live, "content_type", "") or "",
        size=int(getattr(live, "size", 0) or 0),
        message_id=getattr(live, "message_id", None),
        parts=getattr(live, "parts", None),
        sse_nonce=getattr(live, "sse_nonce", None),
        sse_tag=getattr(live, "sse_tag", None),
        encrypted=bool(getattr(live, "encrypted", False)),
        bucket_name=bucket_name,
        created_at=getattr(live, "created_at", None),
        updated_at=getattr(live, "updated_at", None),
    )


async def _purge_tg_for_blob(
    db: AsyncSession,
    blob: BlobInDb | TrashItem,
    *,
    chat_id: str | None,
    reason: str,
) -> None:
    if getattr(blob, "parts", None):
        for part in blob.parts or []:
            mid = getattr(part, "message_id", None)
            if mid is not None:
                await safe_delete_tg_message(
                    db, mid, chat_id=chat_id, reason=reason
                )
    elif getattr(blob, "message_id", None) is not None:
        await safe_delete_tg_message(
            db, blob.message_id, chat_id=chat_id, reason=reason
        )


async def delete_live_object(
    db: AsyncSession,
    *,
    bucket_name: str,
    key: str,
    chat_id: str | None = None,
    deleted_by: str = "",
    reason: str = "delete",
    bypass_trash: bool = False,
) -> BlobInDb | None:
    """Remove a live object: soft-delete to trash by default, else hard-delete TG.

    Soft-delete inserts trash **before** removing the live row so a failed trash
    write cannot strand an object with neither listing nor restore path.
    """
    from app.crud.trash import crud_delete_trash

    result = await db.execute(
        select(BlobRow).where(
            BlobRow.bucket_name == bucket_name,
            BlobRow.path == key,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None

    snapshot = blob_in_db_from_row(row)
    use_trash = ENABLE_TRASH and not bypass_trash
    trash_item: TrashItem | None = None

    if use_trash:
        trash_item = await crud_insert_trash_from_blob(
            db, snapshot, deleted_by=deleted_by, reason=reason
        )

    deleted = await crud_delete_blob(db, bucket_name, key)
    cache_delete(bucket_name, key)
    if not deleted:
        if trash_item is not None:
            await crud_delete_trash(db, trash_item.trash_id)
        return None

    if not use_trash:
        await _purge_tg_for_blob(
            db, deleted, chat_id=chat_id, reason=reason or "hard_delete"
        )
    return deleted


async def retire_previous_version(
    db: AsyncSession,
    previous,
    *,
    bucket_name: str,
    chat_id: str | None = None,
    deleted_by: str = "",
    bypass_trash: bool = False,
    reason: str = "overwrite",
) -> None:
    """On overwrite: park previous TG-backed object in trash (or hard-delete)."""
    snapshot = _as_blob_in_db(previous, bucket_name)
    if ENABLE_TRASH and not bypass_trash:
        await crud_insert_trash_from_blob(
            db, snapshot, deleted_by=deleted_by, reason=reason
        )
        return
    await _purge_tg_for_blob(
        db, snapshot, chat_id=chat_id, reason=f"{reason}_hard_delete"
    )


async def purge_trash_item(
    db: AsyncSession,
    item: TrashItem,
    *,
    chat_id: str | None = None,
) -> None:
    await _purge_tg_for_blob(db, item, chat_id=chat_id, reason="trash_purge")
