"""Cross-bucket CopyObject via Telegram forward (no byte pipe)."""

from __future__ import annotations

import logging

from app.core.config import TG_ALBUM_MAX_ITEMS
from app.models.blob import BlobBase, BlobInCreate, BlobPart, TelegramAlbumMeta
from app.storage import storage
from app.storage.errors import StorageThrottleError, StorageUnavailableError

logger = logging.getLogger(__name__)


def _sorted_parts(blob: BlobBase) -> list[BlobPart]:
    return sorted(blob.parts or [], key=lambda p: p.part_number)


def _album_slices(blob: BlobBase) -> list[tuple[int, int]]:
    if blob.telegram_albums:
        return [(m.part_start, m.part_end) for m in blob.telegram_albums]
    parts = _sorted_parts(blob)
    if not parts:
        return []
    slices: list[tuple[int, int]] = []
    for offset in range(0, len(parts), TG_ALBUM_MAX_ITEMS):
        chunk = parts[offset : offset + TG_ALBUM_MAX_ITEMS]
        slices.append((chunk[0].part_number, chunk[-1].part_number))
    return slices


def _uses_album_forward(blob: BlobBase) -> bool:
    if blob.telegram_albums:
        return True
    parts = blob.parts or []
    return any(p.album_index is not None for p in parts)


def _message_id_for_part(parts: list[BlobPart], part_number: int) -> int | None:
    for part in parts:
        if part.part_number == part_number:
            return part.message_id
    return None


async def _rollback_forwarded_parts(
    parts: list[BlobPart], dest_chat_id: str
) -> None:
    from app.ops.tg_delete import safe_delete_tg_message

    seen: set[int] = set()
    for part in parts:
        mid = part.message_id
        if mid is None or mid in seen:
            continue
        seen.add(mid)
        await safe_delete_tg_message(
            None,
            mid,
            chat_id=dest_chat_id,
            reason="copy_forward_rollback",
        )


async def try_build_cross_bucket_blob_via_forward(
    *,
    src_blob: BlobBase,
    dest_key: str,
    content_type: str,
    source_chat_id: str | None,
    dest_chat_id: str | None,
    dest_topic_id: int | None,
) -> BlobInCreate | None:
    if source_chat_id in (None, "") or dest_chat_id in (None, ""):
        return None
    if not src_blob.message_id and not src_blob.parts:
        return None

    try:
        if src_blob.parts:
            return await _forward_multipart(
                src_blob=src_blob,
                dest_key=dest_key,
                content_type=content_type,
                source_chat_id=source_chat_id,
                dest_chat_id=dest_chat_id,
                dest_topic_id=dest_topic_id,
            )
        return await _forward_single(
            src_blob=src_blob,
            dest_key=dest_key,
            content_type=content_type,
            source_chat_id=source_chat_id,
            dest_chat_id=dest_chat_id,
            dest_topic_id=dest_topic_id,
        )
    except StorageThrottleError:
        raise
    except (StorageUnavailableError, NotImplementedError, AttributeError, TypeError) as exc:
        logger.debug("Cross-bucket forward unavailable: %s", exc)
        return None
    except Exception:
        logger.exception("Cross-bucket forward failed")
        return None


async def _forward_single(
    *,
    src_blob: BlobBase,
    dest_key: str,
    content_type: str,
    source_chat_id: str,
    dest_chat_id: str,
    dest_topic_id: int | None,
) -> BlobInCreate | None:
    mid = src_blob.message_id
    if mid is None:
        return None
    forwarded = await storage.forward_messages(
        source_chat_id,
        mid,
        chat_id=dest_chat_id,
        topic_id=dest_topic_id,
    )
    if not forwarded:
        return None
    res = forwarded[0]
    return BlobInCreate(
        path=dest_key,
        storage_id=src_blob.storage_id,
        telegram_grouped_id=res.grouped_id or src_blob.telegram_grouped_id,
        telegram_albums=src_blob.telegram_albums,
        file=res.file_id,
        content_type=content_type,
        size=int(src_blob.size or 0),
        message_id=res.message_id,
        parts=None,
        sse_nonce=src_blob.sse_nonce,
        sse_tag=src_blob.sse_tag,
        encrypted=bool(src_blob.encrypted),
    )


async def _forward_multipart(
    *,
    src_blob: BlobBase,
    dest_key: str,
    content_type: str,
    source_chat_id: str,
    dest_chat_id: str,
    dest_topic_id: int | None,
) -> BlobInCreate | None:
    parts = _sorted_parts(src_blob)
    part_by_num = {p.part_number: p for p in parts}
    new_parts: list[BlobPart] = []
    albums_meta: list[TelegramAlbumMeta] = []
    telegram_grouped_id = None

    if _uses_album_forward(src_blob):
        album_index = 0
        for part_start, part_end in _album_slices(src_blob):
            anchor = _message_id_for_part(parts, part_start)
            if anchor is None:
                await _rollback_forwarded_parts(new_parts, dest_chat_id)
                return None
            forwarded = await storage.forward_messages(
                source_chat_id,
                anchor,
                chat_id=dest_chat_id,
                topic_id=dest_topic_id,
            )
            expected = part_end - part_start + 1
            if len(forwarded) < expected:
                await _rollback_forwarded_parts(new_parts, dest_chat_id)
                return None
            gid = forwarded[0].grouped_id
            if telegram_grouped_id is None and gid is not None:
                telegram_grouped_id = gid
            albums_meta.append(
                TelegramAlbumMeta(
                    grouped_id=int(gid or 0),
                    part_start=part_start,
                    part_end=part_end,
                )
            )
            for idx, pn in enumerate(range(part_start, part_end + 1)):
                old = part_by_num[pn]
                res = forwarded[idx]
                new_parts.append(
                    BlobPart(
                        part_number=pn,
                        file_id=res.file_id,
                        message_id=res.message_id,
                        size=old.size,
                        etag=old.etag,
                        album_index=album_index,
                    )
                )
            album_index += 1
    else:
        for part in parts:
            if part.message_id is None:
                return None
            forwarded = await storage.forward_messages(
                source_chat_id,
                part.message_id,
                chat_id=dest_chat_id,
                topic_id=dest_topic_id,
            )
            if not forwarded:
                return None
            res = forwarded[0]
            new_parts.append(
                BlobPart(
                    part_number=part.part_number,
                    file_id=res.file_id,
                    message_id=res.message_id,
                    size=part.size,
                    etag=part.etag,
                    album_index=None,
                )
            )

    return BlobInCreate(
        path=dest_key,
        storage_id=src_blob.storage_id,
        telegram_grouped_id=telegram_grouped_id,
        telegram_albums=albums_meta or None,
        file=src_blob.file or "",
        content_type=content_type,
        size=int(src_blob.size or 0),
        message_id=None,
        parts=new_parts,
        sse_nonce=src_blob.sse_nonce,
        sse_tag=src_blob.sse_tag,
        encrypted=bool(src_blob.encrypted),
    )
