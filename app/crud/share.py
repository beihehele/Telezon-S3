import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mappers import share_from_row
from app.db.tables import ShareRow
from app.models.share import Share, ShareInCreate


def _hash_share_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_share_password(password: str, stored: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except ValueError:
        return False


async def crud_create_share(
    db: AsyncSession, payload: ShareInCreate, owner_username: str
) -> Share:
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    share = Share(
        token=token,
        bucket=payload.bucket,
        key=payload.key,
        password_hash=_hash_share_password(payload.password)
        if payload.password
        else None,
        expires_at=now + timedelta(seconds=payload.expires_in),
        max_downloads=payload.max_downloads,
        download_count=0,
        owner_username=owner_username,
        created_at=now,
        updated_at=now,
    )
    row = ShareRow(
        token=share.token,
        bucket=share.bucket,
        key=share.key,
        password_hash=share.password_hash,
        expires_at=share.expires_at,
        max_downloads=share.max_downloads,
        download_count=0,
        owner_username=share.owner_username,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return share


async def crud_get_share(db: AsyncSession, token: str) -> Share | None:
    result = await db.execute(select(ShareRow).where(ShareRow.token == token))
    row = result.scalar_one_or_none()
    if not row:
        return None
    return share_from_row(row)


async def crud_list_shares(
    db: AsyncSession,
    *,
    owner_username: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Share]:
    stmt = select(ShareRow).order_by(ShareRow.created_at.desc()).offset(offset).limit(limit)
    if owner_username:
        stmt = stmt.where(ShareRow.owner_username == owner_username)
    result = await db.execute(stmt)
    return [share_from_row(row) for row in result.scalars().all()]


async def crud_delete_share(db: AsyncSession, token: str) -> bool:
    row = await db.get(ShareRow, token)
    if not row:
        return False
    await db.delete(row)
    await db.flush()
    return True


async def crud_delete_expired_shares(db: AsyncSession, now: datetime) -> int:
    from sqlalchemy import delete

    result = await db.execute(delete(ShareRow).where(ShareRow.expires_at < now))
    return int(result.rowcount or 0)


async def crud_release_share_download(db: AsyncSession, token: str) -> bool:
    result = await db.execute(
        update(ShareRow)
        .where(ShareRow.token == token, ShareRow.download_count > 0)
        .values(download_count=ShareRow.download_count - 1)
    )
    return (result.rowcount or 0) > 0


async def crud_claim_share_download(db: AsyncSession, token: str) -> Share | None:
    now = datetime.now(timezone.utc)
    usable = and_(
        ShareRow.token == token,
        ShareRow.expires_at > now,
        or_(
            ShareRow.max_downloads.is_(None),
            ShareRow.download_count < ShareRow.max_downloads,
        ),
    )
    result = await db.execute(
        update(ShareRow)
        .where(usable)
        .values(download_count=ShareRow.download_count + 1)
        .returning(ShareRow)
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return share_from_row(row)


def share_is_usable(share: Share) -> bool:
    expires = share.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        return False
    if share.max_downloads is not None and share.download_count >= share.max_downloads:
        return False
    return True


def share_password_ok(share: Share, password: str | None) -> bool:
    if not share.password_hash:
        return True
    if not password:
        return False
    return _verify_share_password(password, share.password_hash)
