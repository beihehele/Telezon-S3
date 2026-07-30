from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from app.api.auth.utils import is_admin
from app.core.token import get_current_user
from app.crud.bucket import (
    crud_create_bucket,
    crud_get_all_buckets,
    crud_get_bucket_by_name,
    crud_update_bucket,
)
from app.crud.shortcuts import check_free_bucket_name
from app.db.mongodb import get_database
from app.models.bucket import Bucket, BucketFilterParams, BucketInCreate, BucketInUpdate
from app.models.user import User

router = APIRouter(prefix="/buckets", tags=["Buckets"])


def _can_manage_bucket(user: User, bucket: Bucket) -> bool:
    return is_admin(user) or bucket.owner.username == user.username


@router.get("/", response_model=List[Bucket])
async def get_all_buckets(
    name: str = "",
    owner_username: str = "",
    limit: int = Query(20),
    offset: int = Query(0),
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    if not is_admin(current_user):
        owner_username = current_user.username

    filters = BucketFilterParams(
        name=name, owner_username=owner_username, limit=limit, offset=offset
    )

    buckets = await crud_get_all_buckets(db, filters)
    return buckets


@router.get("/{name}", response_model=Bucket)
async def get_bucket(
    name: str,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    bucket = await crud_get_bucket_by_name(db, name)

    if not bucket:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Bucket {name} not found",
        )
    if not _can_manage_bucket(current_user, bucket):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Not bucket owner",
        )

    return bucket


@router.post("/", response_model=BucketInCreate)
async def create_bucket(
    bucket: BucketInCreate,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    # Align with S3 CreateBucket: any authenticated user may create a bucket
    # they own. Only admins may assign a different owner_username.
    if not is_admin(current_user):
        bucket = bucket.model_copy(update={"owner_username": current_user.username})
    elif not bucket.owner_username:
        bucket = bucket.model_copy(update={"owner_username": current_user.username})

    await check_free_bucket_name(db, bucket.name)
    new_bucket = await crud_create_bucket(db, bucket, current_user)
    return new_bucket


@router.put("/{bucket_name}")
async def update_bucket(
    bucket_name: str,
    bucket: BucketInUpdate = Body(...),
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    existing = await crud_get_bucket_by_name(db, bucket_name)
    if not existing:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Bucket {bucket_name} not found",
        )
    if not _can_manage_bucket(current_user, existing):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Not bucket owner",
        )

    # Ownership transfer remains admin-only.
    if bucket.owner_username is not None and not is_admin(current_user):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Only admin can transfer bucket ownership",
        )

    response_bucket = await crud_update_bucket(db, bucket_name, bucket)
    return response_bucket
