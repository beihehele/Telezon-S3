from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.models.blob import BlobPart
from app.models.db_model import DateTimeModelMixin


class TrashItem(DateTimeModelMixin):
    trash_id: str
    bucket_name: str
    path: str
    storage_id: str | None = None
    telegram_grouped_id: int | None = None
    telegram_albums: list | None = None
    file: str = ""
    content_type: str = ""
    size: int = 0
    message_id: Optional[int] = None
    parts: Optional[List[BlobPart]] = None
    sse_nonce: Optional[str] = None
    sse_tag: Optional[str] = None
    encrypted: bool = False
    deleted_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    deleted_by: str = ""
    reason: str = ""


class TrashPublic(BaseModel):
    trash_id: str
    bucket: str
    key: str
    size: int = 0
    content_type: str = ""
    deleted_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    reason: str = ""


class TrashRestoreRequest(BaseModel):
    trash_id: str = Field(min_length=1)


class TrashEmptyRequest(BaseModel):
    bucket: str = Field(min_length=1)
