"""Resolve Telegram chat/message context for downloads."""

from __future__ import annotations

from app.core.config import CID
from app.models.blob import Blob, BlobPart


def resolve_telegram_chat_id(chat_id: str | None) -> str | None:
    if chat_id not in (None, ""):
        return str(chat_id)
    if CID not in (None, ""):
        return str(CID)
    return None


def blob_telegram_chat_id(blob: Blob) -> str | None:
    bucket = getattr(blob, "bucket", None)
    if bucket is None:
        return resolve_telegram_chat_id(None)
    return resolve_telegram_chat_id(getattr(bucket, "telegram_chat_id", None))

def part_telegram_context(blob: Blob, part: BlobPart) -> tuple[str | None, int | None]:
    return blob_telegram_chat_id(blob), part.message_id


def single_telegram_context(blob: Blob) -> tuple[str | None, int | None]:
    return blob_telegram_chat_id(blob), blob.message_id
