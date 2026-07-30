"""Share password failure lockout (per token + client IP)."""

from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

from app.core.config import (
    DATABASE_NAME,
    SHARE_LOCKOUT_SECONDS,
    SHARE_MAX_FAILED_ATTEMPTS,
)

COLLECTION = "share_lockouts"


def _lock_key(token: str, client_ip: str) -> str:
    return f"{token}:{client_ip or 'unknown'}"


async def share_is_locked(
    db: AsyncIOMotorClient, token: str, client_ip: str
) -> bool:
    row = await db[DATABASE_NAME][COLLECTION].find_one(
        {"key": _lock_key(token, client_ip)}
    )
    if not row:
        return False
    locked_until = row.get("locked_until")
    if not locked_until:
        return False
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < locked_until


async def share_record_password_failure(
    db: AsyncIOMotorClient, token: str, client_ip: str
) -> bool:
    """Increment failures; return True if now locked."""
    key = _lock_key(token, client_ip)
    now = datetime.now(timezone.utc)
    row = await db[DATABASE_NAME][COLLECTION].find_one_and_update(
        {"key": key},
        {
            "$inc": {"failures": 1},
            "$setOnInsert": {"key": key, "created_at": now},
            "$set": {"updated_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    failures = int((row or {}).get("failures") or 0)
    if failures >= SHARE_MAX_FAILED_ATTEMPTS:
        await db[DATABASE_NAME][COLLECTION].update_one(
            {"key": key},
            {
                "$set": {
                    "locked_until": now + timedelta(seconds=SHARE_LOCKOUT_SECONDS),
                }
            },
        )
        return True
    return False


async def share_clear_password_failures(
    db: AsyncIOMotorClient, token: str, client_ip: str
) -> None:
    await db[DATABASE_NAME][COLLECTION].delete_one({"key": _lock_key(token, client_ip)})
