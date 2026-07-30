from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.api.auth.utils import is_admin
from app.core.config import PUBLIC_BASE_URL
from app.core.token import get_current_user
from app.crud.bucket import crud_get_bucket_by_name
from app.db.mongodb import get_database
from app.models.user import User
from app.s3.presign import create_presigned_url

from fastapi import APIRouter, Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

router = APIRouter(prefix="/presign", tags=["Presign"])


class PresignRequest(BaseModel):
    bucket: str
    key: str
    method: str = "GET"
    expires_in: int = Field(default=3600, ge=1, le=604800)


class PresignResponse(BaseModel):
    url: str
    expires_in: int
    method: str


@router.post("/", response_model=PresignResponse)
async def create_presign(
    payload: PresignRequest,
    request: Request,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    method = payload.method.upper()
    if method not in {"GET", "PUT"}:
        raise HTTPException(status_code=400, detail="method must be GET or PUT")

    bucket = await crud_get_bucket_by_name(db, payload.bucket)
    if not bucket:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Bucket {payload.bucket} not found",
        )

    if not is_admin(current_user) and bucket.owner.username != current_user.username:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="You do not own this bucket",
        )

    if PUBLIC_BASE_URL:
        parsed = urlparse(PUBLIC_BASE_URL)
        host = parsed.netloc or request.headers.get("host") or request.url.netloc
        scheme = parsed.scheme or request.url.scheme or "http"
    else:
        host = request.headers.get("host") or request.url.netloc
        scheme = request.url.scheme or "http"
    url = create_presigned_url(
        method=method,
        bucket=payload.bucket,
        key=payload.key,
        access_key=bucket.owner.access_key_id,
        secret_key=bucket.owner.secret_key,
        host=host,
        expires_in=payload.expires_in,
        scheme=scheme,
    )
    return PresignResponse(url=url, expires_in=payload.expires_in, method=method)
