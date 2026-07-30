"""Helpers for Telegram message deletion with retry queue."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import DATABASE_NAME

logger = logging.getLogger(__name__)

COLLECTION = "pending_tg_deletes"


def _storage():
    # Attribute access on the package (not `from app.storage import storage`)
    # so the lazy instance wins over the `storage.py` submodule.
    import app.storage as storage_pkg

    return storage_pkg.storage


async def enqueue_pending_tg_delete(
    db: AsyncIOMotorClient,
    *,
    message_id: int,
    chat_id: Optional[str] = None,
    reason: str = "",
) -> None:
    await db[DATABASE_NAME][COLLECTION].update_one(
        {"message_id": message_id, "chat_id": chat_id},
        {
            "$set": {
                "message_id": message_id,
                "chat_id": chat_id,
                "reason": reason[:200],
                "updated_at": datetime.now(timezone.utc),
            },
            "$setOnInsert": {"created_at": datetime.now(timezone.utc), "attempts": 0},
        },
        upsert=True,
    )


async def safe_delete_tg_message(
    db: AsyncIOMotorClient | None,
    message_id: int | None,
    *,
    chat_id: Optional[str] = None,
    reason: str = "",
) -> bool:
    if message_id is None:
        return True
    try:
        ok = await _storage().delete_message(message_id, chat_id=chat_id)
        if ok:
            return True
    except Exception:
        logger.exception("TG delete failed message_id=%s", message_id)
        ok = False
    if db is not None:
        await enqueue_pending_tg_delete(
            db, message_id=message_id, chat_id=chat_id, reason=reason or "delete_failed"
        )
    return False


async def retry_pending_tg_deletes(
    db: AsyncIOMotorClient, *, limit: int = 50
) -> int:
    cleared = 0
    cursor = db[DATABASE_NAME][COLLECTION].find({}).limit(limit)
    async for row in cursor:
        message_id = row.get("message_id")
        chat_id = row.get("chat_id")
        if message_id is None:
            await db[DATABASE_NAME][COLLECTION].delete_one({"_id": row["_id"]})
            continue
        try:
            ok = await _storage().delete_message(message_id, chat_id=chat_id)
        except Exception:
            ok = False
            await db[DATABASE_NAME][COLLECTION].update_one(
                {"_id": row["_id"]},
                {
                    "$inc": {"attempts": 1},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
            )
            continue
        if ok:
            await db[DATABASE_NAME][COLLECTION].delete_one({"_id": row["_id"]})
            cleared += 1
        else:
            await db[DATABASE_NAME][COLLECTION].update_one(
                {"_id": row["_id"]},
                {
                    "$inc": {"attempts": 1},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
            )
    return cleared
