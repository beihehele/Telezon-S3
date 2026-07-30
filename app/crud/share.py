import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import DATABASE_NAME
from app.models.share import Share, ShareInCreate

COLLECTION = "shares"


def _hash_share_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_share_password(password: str, stored: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except ValueError:
        return False


async def crud_create_share(
    db: AsyncIOMotorClient, payload: ShareInCreate, owner_username: str
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
    await db[DATABASE_NAME][COLLECTION].insert_one(share.model_dump())
    return share


async def crud_get_share(db: AsyncIOMotorClient, token: str) -> Share | None:
    row = await db[DATABASE_NAME][COLLECTION].find_one({"token": token})
    if not row:
        return None
    return Share(**row)


async def crud_delete_share(db: AsyncIOMotorClient, token: str) -> bool:
    result = await db[DATABASE_NAME][COLLECTION].delete_one({"token": token})
    return result.deleted_count > 0


async def crud_claim_share_download(db: AsyncIOMotorClient, token: str) -> Share | None:
    now = datetime.now(timezone.utc)
    row = await db[DATABASE_NAME][COLLECTION].find_one_and_update(
        {
            "token": token,
            "expires_at": {"$gt": now},
            "$or": [
                {"max_downloads": None},
                {"$expr": {"$lt": ["$download_count", "$max_downloads"]}},
            ],
        },
        {"$inc": {"download_count": 1}},
        return_document=True,
    )
    if not row:
        return None
    return Share(**row)


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
