from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.db_model import DateTimeModelMixin


class ShareInCreate(BaseModel):
    bucket: str
    key: str
    password: Optional[str] = None
    expires_in: int = Field(default=3600, ge=60, le=604800)
    max_downloads: Optional[int] = Field(default=None, ge=1)


class Share(DateTimeModelMixin):
    token: str
    bucket: str
    key: str
    password_hash: Optional[str] = None
    expires_at: datetime
    max_downloads: Optional[int] = None
    download_count: int = 0
    owner_username: str = ""


class SharePublic(BaseModel):
    token: str
    bucket: str
    key: str
    expires_at: datetime
    max_downloads: Optional[int] = None
    download_count: int = 0
    has_password: bool = False
