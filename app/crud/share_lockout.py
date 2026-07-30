"""Share password failure lockout (per token + client IP)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import SHARE_LOCKOUT_SECONDS, SHARE_MAX_FAILED_ATTEMPTS
from app.db.tables import ShareLockoutRow


def _lock_key(token: str, client_ip: str) -> str:
    return f"{token}:{client_ip or 'unknown'}"


async def share_is_locked(db: AsyncSession, token: str, client_ip: str) -> bool:
    row = await db.get(ShareLockoutRow, _lock_key(token, client_ip))
    if not row or not row.locked_until:
        return False
    locked_until = row.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < locked_until


async def share_record_password_failure(
    db: AsyncSession, token: str, client_ip: str
) -> bool:
    """Increment failures; return True if now locked."""
    key = _lock_key(token, client_ip)
    now = datetime.now(timezone.utc)
    row = await db.get(ShareLockoutRow, key)
    if row is None:
        row = ShareLockoutRow(key=key, failures=1, created_at=now, updated_at=now)
        db.add(row)
    else:
        row.failures = int(row.failures or 0) + 1
        row.updated_at = now
    await db.flush()
    failures = int(row.failures or 0)
    if failures >= SHARE_MAX_FAILED_ATTEMPTS:
        row.locked_until = now + timedelta(seconds=SHARE_LOCKOUT_SECONDS)
        await db.flush()
        return True
    return False


async def share_clear_password_failures(
    db: AsyncSession, token: str, client_ip: str
) -> None:
    row = await db.get(ShareLockoutRow, key := _lock_key(token, client_ip))
    if row:
        await db.delete(row)
        await db.flush()
