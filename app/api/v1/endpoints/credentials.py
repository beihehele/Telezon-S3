from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from app.core.token import get_current_user
from app.crud.credential import (
    crud_create_credential,
    crud_delete_credential,
    crud_list_credentials_for_owner,
)
from app.db.session import get_database
from app.models.credential import CredentialCreated, CredentialInCreate, CredentialPublic
from app.models.user import User

router = APIRouter(prefix="/credentials", tags=["Credentials"])


@router.get("/", response_model=List[CredentialPublic])
async def list_credentials(
    db: AsyncSession = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    rows = await crud_list_credentials_for_owner(db, current_user.username)
    return [
        CredentialPublic(
            access_key_id=row.access_key_id,
            owner_username=row.owner_username,
            role=row.role,
            buckets=row.buckets,
            label=row.label,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("/", response_model=CredentialCreated)
async def create_credential(
    payload: CredentialInCreate,
    db: AsyncSession = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    try:
        created = await crud_create_credential(db, current_user.username, payload)
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CredentialCreated(**created.model_dump())


@router.delete("/{access_key_id}")
async def delete_credential(
    access_key_id: str,
    db: AsyncSession = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    deleted = await crud_delete_credential(db, current_user.username, access_key_id)
    if not deleted:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail="Credential not found"
        )
    return {"ok": True}
