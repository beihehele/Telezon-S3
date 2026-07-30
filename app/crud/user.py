import random
import string
from datetime import datetime, timezone
from typing import List

from fastapi.exceptions import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_404_NOT_FOUND

from app.db.mappers import user_from_row
from app.db.tables import UserRow
from app.models.user import (
    ADMIN_ROLE,
    USER_ROLE,
    UserFilterParams,
    UserInCreate,
    UserInDb,
    UserInUpdate,
)


async def crud_get_all_users(
    db: AsyncSession, filters: UserFilterParams
) -> List[UserInDb]:
    stmt = select(UserRow)
    if filters.username:
        names = filters.username.replace(", ", ",").split(",")
        stmt = stmt.where(UserRow.username.in_(names))
    if filters.email:
        emails = filters.email.replace(", ", ",").split(",")
        stmt = stmt.where(UserRow.email.in_(emails))
    stmt = stmt.offset(filters.offset).limit(filters.limit)
    result = await db.execute(stmt)
    return [user_from_row(row) for row in result.scalars().all()]


async def crud_get_user_by_username(db: AsyncSession, username: str) -> UserInDb | None:
    row = await db.get(UserRow, username)
    if row:
        return user_from_row(row)
    return None


async def crud_get_user_by_email(db: AsyncSession, email: str) -> UserInDb | None:
    result = await db.execute(select(UserRow).where(UserRow.email == email))
    row = result.scalar_one_or_none()
    if row:
        return user_from_row(row)
    return None


async def crud_get_user_by_access_key_id(
    db: AsyncSession, access_key_id: str
) -> UserInDb | None:
    result = await db.execute(
        select(UserRow).where(UserRow.access_key_id == access_key_id)
    )
    row = result.scalar_one_or_none()
    if row:
        return user_from_row(row)
    return None


async def crud_create_user(
    db: AsyncSession, user: UserInCreate, admin=False
) -> UserInDb:
    data_user = UserInDb(**user.model_dump())
    if admin:
        data_user.role = ADMIN_ROLE
    else:
        data_user.role = USER_ROLE

    data_user.change_password(user.password)

    if not data_user.access_key_id:
        data_user.access_key_id = "".join(
            random.choice(string.ascii_letters + string.digits) for _ in range(16)
        )

    if not data_user.secret_key:
        data_user.secret_key = "".join(
            random.choice(string.ascii_letters + string.digits) for _ in range(16)
        )

    now = datetime.now(timezone.utc)
    data_user.created_at = now
    data_user.updated_at = now

    row = UserRow(
        username=data_user.username,
        email=str(data_user.email),
        description=data_user.description or "",
        role=data_user.role,
        access_key_id=data_user.access_key_id,
        secret_key=data_user.secret_key,
        salt=data_user.salt,
        hashed_password=data_user.hashed_password,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return user_from_row(row)


async def crud_update_user(
    db: AsyncSession, username: str, user: UserInUpdate
) -> UserInDb:
    row = await db.get(UserRow, username)
    if not row:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Username {username} not found",
        )

    data_user = user_from_row(row)
    data_user.email = user.email or data_user.email
    data_user.description = user.description or data_user.description
    data_user.role = user.role or data_user.role

    if user.password:
        data_user.change_password(user.password)

    row.email = str(data_user.email)
    row.description = data_user.description or ""
    row.role = data_user.role
    row.salt = data_user.salt
    row.hashed_password = data_user.hashed_password
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return user_from_row(row)


async def crud_delete_user(db: AsyncSession, username: str) -> None:
    row = await db.get(UserRow, username)
    if row:
        await db.delete(row)
        await db.flush()
