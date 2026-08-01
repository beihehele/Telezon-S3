"""Map ORM rows to Pydantic models."""

from __future__ import annotations

from typing import Any

from app.models.blob import Blob, BlobInDb, BlobPart
from app.models.bucket import Bucket, BucketInDb
from app.models.credential import CredentialInDb
from app.models.share import Share
from app.models.trash import TrashItem
from app.models.user import User, UserInDb
from app.db.tables import (
    BlobRow,
    BucketRow,
    CredentialRow,
    ShareRow,
    TrashRow,
    UserRow,
)


def _parts_from_json(raw: list | None) -> list[BlobPart] | None:
    if not raw:
        return None
    return [BlobPart(**p) if isinstance(p, dict) else p for p in raw]


def user_from_row(row: UserRow) -> UserInDb:
    return UserInDb(
        username=row.username,
        email=row.email,
        description=row.description or "",
        role=row.role,
        access_key_id=row.access_key_id or "",
        secret_key=row.secret_key or "",
        salt=row.salt or "",
        hashed_password=row.hashed_password or "",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def user_public_from_row(row: UserRow) -> User:
    u = user_from_row(row)
    return User(**u.model_dump(exclude={"salt", "hashed_password"}))


def bucket_in_db_from_row(row: BucketRow) -> BucketInDb:
    return BucketInDb(
        name=row.name,
        owner_username=row.owner_username,
        is_public=bool(row.is_public),
        telegram_chat_id=row.telegram_chat_id,
        telegram_topic_id=row.telegram_topic_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def bucket_from_rows(bucket: BucketRow, owner: UserRow, size: int = 0) -> Bucket:
    return Bucket(
        name=bucket.name,
        is_public=bool(bucket.is_public),
        telegram_chat_id=bucket.telegram_chat_id,
        telegram_topic_id=bucket.telegram_topic_id,
        owner=user_public_from_row(owner),
        size=size,
        created_at=bucket.created_at,
        updated_at=bucket.updated_at,
    )


def _albums_from_json(raw: list | None) -> list | None:
    if not raw:
        return None
    from app.models.blob import TelegramAlbumMeta

    return [TelegramAlbumMeta(**a) if isinstance(a, dict) else a for a in raw]


def _albums_to_json(albums: Any) -> list | None:
    if not albums:
        return None
    out = []
    for a in albums:
        if hasattr(a, "model_dump"):
            out.append(a.model_dump())
        elif isinstance(a, dict):
            out.append(a)
    return out or None


def blob_in_db_from_row(row: BlobRow) -> BlobInDb:
    return BlobInDb(
        path=row.path,
        storage_id=row.storage_id,
        telegram_grouped_id=row.telegram_grouped_id,
        telegram_albums=_albums_from_json(row.telegram_albums),
        file=row.file or "",
        content_type=row.content_type or "",
        size=int(row.size or 0),
        message_id=row.message_id,
        parts=_parts_from_json(row.parts),
        sse_nonce=row.sse_nonce,
        sse_tag=row.sse_tag,
        encrypted=bool(row.encrypted),
        bucket_name=row.bucket_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def blob_from_row(row: BlobRow, bucket: BucketRow, owner: UserRow) -> Blob:
    b = blob_in_db_from_row(row)
    return Blob(
        **b.model_dump(exclude={"bucket_name"}),
        bucket=bucket_in_db_from_row(bucket),
        owner=user_public_from_row(owner),
    )


def credential_from_row(row: CredentialRow) -> CredentialInDb:
    buckets = row.buckets if isinstance(row.buckets, list) else []
    return CredentialInDb(
        access_key_id=row.access_key_id,
        secret_key=row.secret_key,
        owner_username=row.owner_username,
        role=row.role,
        buckets=[str(b) for b in buckets],
        label=row.label or "",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def share_from_row(row: ShareRow) -> Share:
    return Share(
        token=row.token,
        bucket=row.bucket,
        key=row.key,
        password_hash=row.password_hash,
        expires_at=row.expires_at,
        max_downloads=row.max_downloads,
        download_count=int(row.download_count or 0),
        owner_username=row.owner_username,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def trash_from_row(row: TrashRow) -> TrashItem:
    return TrashItem(
        trash_id=row.trash_id,
        bucket_name=row.bucket_name,
        path=row.path,
        storage_id=row.storage_id,
        telegram_grouped_id=row.telegram_grouped_id,
        telegram_albums=row.telegram_albums,
        file=row.file or "",
        content_type=row.content_type or "",
        size=int(row.size or 0),
        message_id=row.message_id,
        parts=_parts_from_json(row.parts),
        sse_nonce=row.sse_nonce,
        sse_tag=row.sse_tag,
        encrypted=bool(row.encrypted),
        deleted_at=row.deleted_at,
        expires_at=row.expires_at,
        deleted_by=row.deleted_by or "",
        reason=row.reason or "",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def parts_to_json(parts: Any) -> list | None:
    if not parts:
        return None
    out = []
    for p in parts:
        if hasattr(p, "model_dump"):
            out.append(p.model_dump())
        elif isinstance(p, dict):
            out.append(p)
        else:
            out.append(dict(p))
    return out
