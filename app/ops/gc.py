"""Background hygiene: stale multipart uploads and expired shares."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.core.config import (
    DATABASE_NAME,
    GC_INTERVAL_SECONDS,
    GC_MULTIPART_MAX_AGE_SECONDS,
    GC_ORPHAN_SAMPLE_SIZE,
    ENABLE_GC,
    ENABLE_TRASH,
)
from app.crud.blob import crud_delete_blob
from app.crud.bucket import crud_get_bucket_by_name
from app.crud.multipart import crud_delete_multipart_upload, crud_list_parts
from app.crud.trash import crud_delete_trash, crud_list_expired_trash
from app.db.mongodb import db
from app.ops.tg_delete import retry_pending_tg_deletes
from app.s3.object_lifecycle import purge_trash_item
from app.storage import storage
from app.storage.errors import (
    StorageObjectGoneError,
    StorageThrottleError,
    StorageUnavailableError,
)

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None

_GONE_MARKERS = (
    "file_id_invalid",
    "file reference",
    "media_empty",
    "wrong file id",
    "wrong file_id",
    "file not found",
    "no such file",
    "message not found",
    "msg_id_invalid",
    "message_id_invalid",
)


def _is_transient_probe_error(exc: BaseException) -> bool:
    return isinstance(exc, (StorageThrottleError, StorageUnavailableError))


def _is_confirmed_object_gone(exc: BaseException) -> bool:
    if isinstance(exc, StorageObjectGoneError):
        return True
    text = str(exc).lower()
    return any(marker in text for marker in _GONE_MARKERS)


async def _sample_dead_blobs(client) -> int:
    """Drop metadata only when Telegram confirms the file is gone.

    Transient failures (rate limit / client down) and unknown errors must not
    delete live object metadata.
    """
    if GC_ORPHAN_SAMPLE_SIZE <= 0:
        return 0
    removed = 0
    cursor = client[DATABASE_NAME]["blobs"].aggregate(
        [{"$sample": {"size": GC_ORPHAN_SAMPLE_SIZE}}]
    )
    async for row in cursor:
        file_id = row.get("file")
        parts = row.get("parts") or []
        bucket_name = row.get("bucket_name")
        path = row.get("path")
        if not bucket_name or not path:
            continue
        try:
            if parts:
                # Multipart: probe first part only.
                first = parts[0]
                fid = first.get("file_id") if isinstance(first, dict) else None
                if not fid:
                    continue
                await storage.get_file(fid)
            elif file_id and not str(file_id).startswith("multipart:"):
                await storage.get_file(file_id)
            else:
                continue
        except Exception as exc:
            if _is_transient_probe_error(exc):
                logger.info(
                    "GC orphan probe skipped transient error bucket=%s path=%s: %s",
                    bucket_name,
                    path,
                    exc,
                )
                continue
            if not _is_confirmed_object_gone(exc):
                logger.warning(
                    "GC orphan probe inconclusive bucket=%s path=%s: %s",
                    bucket_name,
                    path,
                    exc,
                )
                continue
            await crud_delete_blob(client, bucket_name, path)
            removed += 1
            logger.warning(
                "GC removed dead blob metadata bucket=%s path=%s", bucket_name, path
            )
    return removed


async def _purge_expired_trash(client) -> int:
    if not ENABLE_TRASH:
        return 0
    purged = 0
    expired = await crud_list_expired_trash(client, limit=100)
    for item in expired:
        bucket = await crud_get_bucket_by_name(client, item.bucket_name)
        chat_id = getattr(bucket, "telegram_chat_id", None) if bucket else None
        removed = await crud_delete_trash(client, item.trash_id)
        if removed:
            await purge_trash_item(client, removed, chat_id=chat_id)
            purged += 1
    return purged


async def run_gc_once() -> dict:
    client = db.client
    if client is None:
        return {
            "multipart_aborted": 0,
            "shares_deleted": 0,
            "pending_tg_cleared": 0,
            "dead_blobs_removed": 0,
            "trash_purged": 0,
        }

    now = datetime.now(timezone.utc)
    multipart_cutoff = now - timedelta(seconds=GC_MULTIPART_MAX_AGE_SECONDS)
    aborted = 0
    shares_deleted = 0

    cursor = client[DATABASE_NAME]["multipart_uploads"].find(
        {"initiated_at": {"$lt": multipart_cutoff}}
    ).limit(100)
    async for upload in cursor:
        upload_id = upload.get("upload_id")
        bucket_name = upload.get("bucket")
        if not upload_id:
            continue
        bucket = (
            await crud_get_bucket_by_name(client, bucket_name) if bucket_name else None
        )
        chat_id = getattr(bucket, "telegram_chat_id", None) if bucket else None
        parts = await crud_list_parts(client, upload_id)
        for part in parts:
            if part.get("message_id") is not None:
                try:
                    await storage.delete_message(part["message_id"], chat_id=chat_id)
                except Exception:
                    logger.exception(
                        "GC: failed deleting part message %s", part.get("message_id")
                    )
        await crud_delete_multipart_upload(client, upload_id)
        aborted += 1

    result = await client[DATABASE_NAME]["shares"].delete_many(
        {"expires_at": {"$lt": now}}
    )
    shares_deleted = int(result.deleted_count or 0)
    pending_cleared = await retry_pending_tg_deletes(client, limit=50)
    dead_blobs = await _sample_dead_blobs(client)
    trash_purged = await _purge_expired_trash(client)

    if aborted or shares_deleted or pending_cleared or dead_blobs or trash_purged:
        logger.info(
            "GC finished multipart_aborted=%s shares_deleted=%s "
            "pending_tg_cleared=%s dead_blobs_removed=%s trash_purged=%s",
            aborted,
            shares_deleted,
            pending_cleared,
            dead_blobs,
            trash_purged,
        )
    return {
        "multipart_aborted": aborted,
        "shares_deleted": shares_deleted,
        "pending_tg_cleared": pending_cleared,
        "dead_blobs_removed": dead_blobs,
        "trash_purged": trash_purged,
    }


async def _gc_loop() -> None:
    while True:
        try:
            await run_gc_once()
        except Exception:
            logger.exception("GC loop iteration failed")
        await asyncio.sleep(max(60, GC_INTERVAL_SECONDS))


async def start_gc_if_enabled() -> None:
    global _task
    if not ENABLE_GC:
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_gc_loop(), name="telezon-gc")
    logger.info(
        "Background GC started interval=%ss multipart_max_age=%ss",
        GC_INTERVAL_SECONDS,
        GC_MULTIPART_MAX_AGE_SECONDS,
    )


async def stop_gc() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    finally:
        _task = None
