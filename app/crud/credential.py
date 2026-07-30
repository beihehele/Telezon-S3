import random
import string
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mappers import credential_from_row
from app.db.tables import CredentialRow
from app.models.credential import (
    VALID_ROLES,
    CredentialInCreate,
    CredentialInDb,
)


def _random_key(length: int = 20) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


async def crud_get_credential_by_access_key(
    db: AsyncSession, access_key_id: str
) -> Optional[CredentialInDb]:
    row = await db.get(CredentialRow, access_key_id)
    if not row:
        return None
    return credential_from_row(row)


async def crud_list_credentials_for_owner(
    db: AsyncSession, owner_username: str
) -> List[CredentialInDb]:
    result = await db.execute(
        select(CredentialRow).where(CredentialRow.owner_username == owner_username)
    )
    return [credential_from_row(row) for row in result.scalars().all()]


async def crud_create_credential(
    db: AsyncSession,
    owner_username: str,
    payload: CredentialInCreate,
) -> CredentialInDb:
    role = (payload.role or "").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")

    buckets = [b.strip() for b in payload.buckets if b and b.strip()]
    now = datetime.now(timezone.utc)
    data = CredentialInDb(
        access_key_id="TZ" + _random_key(18),
        secret_key=_random_key(40),
        owner_username=owner_username,
        role=role,
        buckets=buckets,
        label=(payload.label or "").strip()[:64],
        created_at=now,
        updated_at=now,
    )
    row = CredentialRow(
        access_key_id=data.access_key_id,
        secret_key=data.secret_key,
        owner_username=data.owner_username,
        role=data.role,
        buckets=buckets,
        label=data.label,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return credential_from_row(row)


async def crud_delete_credential(
    db: AsyncSession, owner_username: str, access_key_id: str
) -> bool:
    result = await db.execute(
        delete(CredentialRow).where(
            CredentialRow.owner_username == owner_username,
            CredentialRow.access_key_id == access_key_id,
        )
    )
    return (result.rowcount or 0) > 0
