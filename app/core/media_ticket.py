"""Short-lived JWT for object content delivery only (console <video>, Range)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from jwt import PyJWTError

from app.core.config import SECRET_KEY
from app.core.token import ALGORITHM

MEDIA_TICKET_JWT_SUBJECT = "media_content"


@dataclass(frozen=True)
class MediaTicketClaims:
    username: str
    bucket: str
    key: str


def create_media_ticket(
    *,
    username: str,
    bucket: str,
    key: str,
    expires_delta: timedelta,
) -> str:
    expire = datetime.now(UTC) + expires_delta
    payload = {
        "sub": MEDIA_TICKET_JWT_SUBJECT,
        "username": username,
        "bucket": bucket,
        "key": key,
        "exp": expire,
    }
    return jwt.encode(payload, str(SECRET_KEY), algorithm=ALGORITHM)


def decode_media_ticket(token: str) -> MediaTicketClaims:
    try:
        payload = jwt.decode(token, str(SECRET_KEY), algorithms=[ALGORITHM])
    except PyJWTError as exc:
        raise ValueError("invalid media token") from exc
    if payload.get("sub") != MEDIA_TICKET_JWT_SUBJECT:
        raise ValueError("invalid media token")
    username = payload.get("username") or ""
    bucket = payload.get("bucket") or ""
    key = payload.get("key") or ""
    if not username or not bucket or not key:
        raise ValueError("invalid media token")
    return MediaTicketClaims(username=username, bucket=bucket, key=key)
