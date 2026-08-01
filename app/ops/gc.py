"""Background hygiene: stale multipart uploads and expired shares."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.core.config import (
    GC_INTERVAL_SECONDS,
    GC_MULTIPART_MAX_AGE_SECONDS,
    GC_ORPHAN_SAMPLE_SIZE,
    ENABLE_GC,
    ENABLE_TRASH,
)
from app.crud.blob import crud_delete_blob, crud_sample_blobs
from app.crud.bucket import crud_get_bucket_by_name
from app.crud.multipart import (
    crud_delete_multipart_upload,
    crud_list_parts,
    crud_list_stale_multipart_uploads,
)
from app.crud.share import crud_delete_expired_shares
from app.crud.trash import crud_delete_trash, crud_list_expired_trash
from app.db import session as db_session
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


async def _sample_dead_blobs(session) -> int:
    if GC_ORPHAN_SAMPLE_SIZE <= 0:
        return 0
    removed = 0
    samples = await crud_sample_blobs(session, GC_ORPHAN_SAMPLE_SIZE)
    for blob in samples:
        file_id = blob.file
        parts = blob.parts or []
        bucket_name = blob.bucket_name
        path = blob.path
        if not bucket_name or not path:
            continue
        try:
            if parts:
                first = parts[0]
                fid = first.file_id if hasattr(first, "file_id") else None
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
            await crud_delete_blob(session, bucket_name, path)
            removed += 1
            logger.warning(
                "GC removed dead blob metadata bucket=%s path=%s", bucket_name, path
            )
    return removed


async def _purge_expired_trash(session) -> int:
    if not ENABLE_TRASH:
        return 0
    purged = 0
    expired = await crud_list_expired_trash(session, limit=100)
    for item in expired:
        bucket = await crud_get_bucket_by_name(session, item.bucket_name)
        chat_id = getattr(bucket, "telegram_chat_id", None) if bucket else None
        removed = await crud_delete_trash(session, item.trash_id)
        if removed:
            await purge_trash_item(session, removed, chat_id=chat_id)
            purged += 1
    return purged


async def run_gc_once() -> dict:
    if db_session.async_session_factory is None:
        return {
            "multipart_aborted": 0,
            "shares_deleted": 0,
            "pending_tg_cleared": 0,
            "dead_blobs_removed": 0,
            "trash_purged": 0,
        }

    async with db_session.async_session_factory() as session:
        now = datetime.now(timezone.utc)
        multipart_cutoff = now - timedelta(seconds=GC_MULTIPART_MAX_AGE_SECONDS)
        aborted = 0

        uploads = await crud_list_stale_multipart_uploads(
            session, multipart_cutoff, limit=100
        )
        for upload in uploads:
            upload_id = upload.get("upload_id")
            bucket_name = upload.get("bucket")
            if not upload_id:
                continue
            bucket = (
                await crud_get_bucket_by_name(session, bucket_name)
                if bucket_name
                else None
            )
            chat_id = getattr(bucket, "telegram_chat_id", None) if bucket else None
            parts = await crud_list_parts(session, upload_id)
            for part in parts:
                if part.get("message_id") is not None:
                    try:
                        await storage.delete_message(
                            part["message_id"], chat_id=chat_id
                        )
                    except Exception:
                        logger.exception(
                            "GC: failed deleting part message %s", part.get("message_id")
                        )
            from app.storage.mpu_staging import remove_upload_staging

            remove_upload_staging(upload_id)
            await crud_delete_multipart_upload(session, upload_id)
            aborted += 1

        shares_deleted = await crud_delete_expired_shares(session, now)
        pending_cleared = await retry_pending_tg_deletes(session, limit=50)
        dead_blobs = await _sample_dead_blobs(session)
        trash_purged = await _purge_expired_trash(session)
        await session.commit()

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
