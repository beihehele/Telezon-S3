from typing import Optional

from pydantic import BaseModel, Field

from app.models.db_model import DateTimeModelMixin
from app.models.user import User


class BucketFilterParams(BaseModel):
    name: str = Field(default="")
    owner_username: str = Field(default="")
    limit: int = Field(default=20)
    offset: int = Field(default=0)


class BucketBase(BaseModel):
    name: str
    is_public: bool = False
    telegram_chat_id: Optional[str] = None
    telegram_topic_id: Optional[int] = None


class BucketInDb(BucketBase, DateTimeModelMixin):
    owner_username: str = ""


class Bucket(BucketBase, DateTimeModelMixin):
    owner: User
    size: int = 0


class BucketInCreate(BucketBase):
    owner_username: str = ""


class BucketInUpdate(BaseModel):
    owner_username: Optional[str] = None
    is_public: Optional[bool] = None
    telegram_chat_id: Optional[str] = None
    telegram_topic_id: Optional[int] = None
