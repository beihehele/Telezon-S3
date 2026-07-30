import random
import string
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import DATABASE_NAME
from app.models.credential import (
    VALID_ROLES,
    CredentialInCreate,
    CredentialInDb,
)

COLLECTION = "credentials"


def _random_key(length: int = 20) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


async def crud_get_credential_by_access_key(
    db: AsyncIOMotorClient, access_key_id: str
) -> Optional[CredentialInDb]:
    row = await db[DATABASE_NAME][COLLECTION].find_one(
        {"access_key_id": access_key_id}
    )
    if not row:
        return None
    return CredentialInDb(**row)


async def crud_list_credentials_for_owner(
    db: AsyncIOMotorClient, owner_username: str
) -> List[CredentialInDb]:
    cursor = db[DATABASE_NAME][COLLECTION].find({"owner_username": owner_username})
    rows: List[CredentialInDb] = []
    async for row in cursor:
        rows.append(CredentialInDb(**row))
    return rows


async def crud_create_credential(
    db: AsyncIOMotorClient,
    owner_username: str,
    payload: CredentialInCreate,
) -> CredentialInDb:
    role = (payload.role or "").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")

    buckets = [b.strip() for b in payload.buckets if b and b.strip()]
    data = CredentialInDb(
        access_key_id="TZ" + _random_key(18),
        secret_key=_random_key(40),
        owner_username=owner_username,
        role=role,
        buckets=buckets,
        label=(payload.label or "").strip()[:64],
    )
    row = await db[DATABASE_NAME][COLLECTION].insert_one(data.model_dump())
    data.created_at = ObjectId(row.inserted_id).generation_time
    data.updated_at = data.created_at
    await db[DATABASE_NAME][COLLECTION].update_one(
        {"access_key_id": data.access_key_id},
        {"$set": {"created_at": data.created_at, "updated_at": data.updated_at}},
    )
    return data


async def crud_delete_credential(
    db: AsyncIOMotorClient, owner_username: str, access_key_id: str
) -> bool:
    result = await db[DATABASE_NAME][COLLECTION].delete_one(
        {"owner_username": owner_username, "access_key_id": access_key_id}
    )
    return result.deleted_count > 0
