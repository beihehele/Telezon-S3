"""Helpers for Telegram message deletion with retry queue."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import PendingTgDeleteRow

logger = logging.getLogger(__name__)


def _storage():
    import app.storage as storage_pkg

    return storage_pkg.storage


async def enqueue_pending_tg_delete(
    db: AsyncSession,
    *,
    message_id: int,
    chat_id: Optional[str] = None,
    reason: str = "",
) -> None:
    chat_key = chat_id or ""
    result = await db.execute(
        select(PendingTgDeleteRow).where(
            PendingTgDeleteRow.message_id == message_id,
            PendingTgDeleteRow.chat_id_key == chat_key,
        )
    )
    row = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row is None:
        row = PendingTgDeleteRow(
            message_id=message_id,
            chat_id=chat_id,
            chat_id_key=chat_key,
            reason=reason[:200],
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.reason = reason[:200]
        row.updated_at = now
    await db.flush()


async def safe_delete_tg_message(
    db: AsyncSession | None,
    message_id: int | None,
    *,
    chat_id: Optional[str] = None,
    reason: str = "",
) -> bool:
    if message_id is None:
        return True
    if db is not None:
        from app.crud.tg_refs import count_message_id_refs

        refs = await count_message_id_refs(db, int(message_id))
        if refs > 0:
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


async def retry_pending_tg_deletes(db: AsyncSession, *, limit: int = 50) -> int:
    cleared = 0
    result = await db.execute(select(PendingTgDeleteRow).limit(limit))
    rows = list(result.scalars().all())
    for row in rows:
        message_id = row.message_id
        chat_id = row.chat_id
        if message_id is None:
            await db.delete(row)
            continue
        from app.crud.tg_refs import count_message_id_refs

        if await count_message_id_refs(db, int(message_id)) > 0:
            await db.delete(row)
            cleared += 1
            continue
        try:
            ok = await _storage().delete_message(message_id, chat_id=chat_id)
        except Exception:
            ok = False
            row.attempts = int(row.attempts or 0) + 1
            row.updated_at = datetime.now(timezone.utc)
            continue
        if ok:
            await db.delete(row)
            cleared += 1
        else:
            row.attempts = int(row.attempts or 0) + 1
            row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return cleared
