from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.db_model import DateTimeModelMixin

ROLE_READWRITE = "readwrite"
ROLE_READONLY = "readonly"
VALID_ROLES = {ROLE_READWRITE, ROLE_READONLY}


class CredentialInCreate(BaseModel):
    role: str = Field(default=ROLE_READONLY)
    buckets: List[str] = Field(default_factory=list)
    label: str = ""


class CredentialPublic(DateTimeModelMixin):
    access_key_id: str
    owner_username: str
    role: str
    buckets: List[str] = Field(default_factory=list)
    label: str = ""


class CredentialCreated(CredentialPublic):
    """Returned once at creation — includes secret_key."""

    secret_key: str


class CredentialInDb(CredentialPublic):
    secret_key: str
