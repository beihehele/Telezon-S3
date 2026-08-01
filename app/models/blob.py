from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.bucket import BucketBase
from app.models.db_model import DateTimeModelMixin
from app.models.user import User


class BlobFilterParams(BaseModel):
    path: str = ""
    bucket_name: str = ""
    limit: int = 20
    offset: int = 0


class BlobPart(BaseModel):
    part_number: int
    file_id: str
    size: int = 0
    message_id: int | None = None
    etag: str = ""
    album_index: int | None = None


class TelegramAlbumMeta(BaseModel):
    grouped_id: int
    part_start: int
    part_end: int


class BlobBase(BaseModel):
    path: str
    storage_id: str | None = None
    telegram_grouped_id: int | None = None
    telegram_albums: list[TelegramAlbumMeta] | None = None
    file: str = ""
    content_type: str = ""
    size: int = 0
    message_id: int | None = None
    parts: Optional[list[BlobPart]] = None
    sse_nonce: Optional[str] = None
    sse_tag: Optional[str] = None
    encrypted: bool = False


class BlobInDb(BlobBase, DateTimeModelMixin):
    bucket_name: str = ""


class Blob(BlobBase, DateTimeModelMixin):
    bucket: BucketBase
    owner: User


class BlobInCreate(BlobBase):
    pass
