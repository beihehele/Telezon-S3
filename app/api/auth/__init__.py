from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN

from app.core.config import ALLOW_SIGNUP, logger
from app.core.token import create_access_token, get_current_user
from app.crud.bucket import crud_create_bucket
from app.crud.shortcuts import check_free_bucket_name, check_free_username_and_email
from app.crud.user import (
    crud_create_user,
    crud_delete_user,
    crud_get_user_by_username,
)
from app.db.session import get_database
from app.models.bucket import BucketInCreate
from pydantic import BaseModel

from app.models.token import Token
from app.models.user import User, UserInCreate, UserPublic

router = APIRouter(prefix="/auth", tags=["Auth"])

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # One week


class AuthPublicConfig(BaseModel):
    allow_signup: bool


@router.get("/config", response_model=AuthPublicConfig)
def auth_public_config():
    """Console reads this before showing the register link."""
    return AuthPublicConfig(allow_signup=ALLOW_SIGNUP)


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_database),
):
    user = await crud_get_user_by_username(db, form_data.username)
    if not user or not user.check_password(form_data.password):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST, detail="Incorrect username or password"
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    token = create_access_token(
        data={"username": user.username}, expires_delta=access_token_expires
    )

    return {"access_token": token, "token_type": "bearer"}


@router.post("/signup", response_model=UserPublic)
async def signup(
    user: UserInCreate = Body(...),
    db: AsyncSession = Depends(get_database),
):
    if not ALLOW_SIGNUP:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Public signup is disabled",
        )
    await check_free_username_and_email(db, user.username, user.email)
    new_user = await crud_create_user(db, user)

    # Default bucket matches username; roll back the user if bucket setup fails
    # so clients never see an account without a usable home bucket.
    try:
        await check_free_bucket_name(db, user.username)
        bucket = BucketInCreate(
            name=user.username,
            owner_username=user.username,
        )
        await crud_create_bucket(db, bucket, User(**new_user.model_dump()))
    except Exception as e:
        logger.error("Error creating default bucket for %s: %s", user.username, e)
        try:
            await crud_delete_user(db, user.username)
        except Exception as cleanup_err:
            logger.error(
                "Failed to roll back user %s after bucket error: %s",
                user.username,
                cleanup_err,
            )
        if isinstance(e, HTTPException):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Signup failed while creating default bucket",
            ) from e
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Signup failed while creating default bucket",
        ) from e

    return UserPublic.from_user(User(**new_user.model_dump()))


@router.get("/current_user", response_model=UserPublic)
def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    return UserPublic.from_user(current_user)
