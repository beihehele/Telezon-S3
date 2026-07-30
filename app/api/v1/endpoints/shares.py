from fastapi import APIRouter, Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.responses import Response
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from app.api.auth.utils import is_admin
from app.core.config import MAX_UPLOAD_BYTES
from app.core.token import get_current_user
from app.crud.blob import crud_get_all_blobs
from app.crud.bucket import crud_get_bucket_by_name
from app.crud.share import (
    crud_claim_share_download,
    crud_create_share,
    crud_delete_share,
    crud_get_share,
    share_is_usable,
    share_password_ok,
)
from app.crud.share_lockout import (
    share_clear_password_failures,
    share_is_locked,
    share_record_password_failure,
)
from app.db.mongodb import get_database
from app.models.blob import BlobFilterParams
from app.models.share import ShareInCreate, SharePublic
from app.models.user import User
from app.s3.blob_io import load_blob_bytes, safe_content_disposition

router = APIRouter(prefix="/shares", tags=["Shares"])


@router.post("/", response_model=SharePublic)
async def create_share(
    payload: ShareInCreate,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    bucket = await crud_get_bucket_by_name(db, payload.bucket)
    if not bucket:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Bucket not found")
    if not is_admin(current_user) and bucket.owner.username != current_user.username:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Not bucket owner")

    blobs = await crud_get_all_blobs(
        db, BlobFilterParams(path=payload.key, bucket_name=payload.bucket)
    )
    if not blobs:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Object not found")

    blob = blobs[0]
    if blob.encrypted:
        raise HTTPException(
            status_code=400,
            detail="Cannot share SSE-C encrypted objects",
        )

    blob_size = int(getattr(blob, "size", 0) or 0)
    if blob_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Objects larger than {MAX_UPLOAD_BYTES} bytes cannot use share "
                f"links (in-memory download); use a presigned GET instead"
            ),
        )

    share = await crud_create_share(db, payload, current_user.username)
    return SharePublic(
        token=share.token,
        bucket=share.bucket,
        key=share.key,
        expires_at=share.expires_at,
        max_downloads=share.max_downloads,
        download_count=share.download_count,
        has_password=bool(share.password_hash),
    )


@router.delete("/{token}")
async def revoke_share(
    token: str,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    share = await crud_get_share(db, token)
    if not share:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Share not found")
    if not is_admin(current_user) and share.owner_username != current_user.username:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Not share owner")
    await crud_delete_share(db, token)
    return {"ok": True}


share_public_router = APIRouter(tags=["ShareDownload"])


@share_public_router.get("/share/{token}")
async def download_share(
    token: str,
    request: Request,
    db: AsyncIOMotorClient = Depends(get_database),
):
    share = await crud_get_share(db, token)
    if not share or not share_is_usable(share):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Share not found")

    client_ip = request.client.host if request.client else "unknown"
    if await share_is_locked(db, token, client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many failed password attempts; try again later",
        )

    # Prefer header; query password is rejected to avoid log leakage.
    if "password" in request.query_params:
        raise HTTPException(
            status_code=400,
            detail="Pass password via X-Share-Password header only",
        )
    header_password = request.headers.get("x-share-password")
    if not share_password_ok(share, header_password):
        locked = await share_record_password_failure(db, token, client_ip)
        if locked:
            raise HTTPException(
                status_code=429,
                detail="Too many failed password attempts; try again later",
            )
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid password")

    await share_clear_password_failures(db, token, client_ip)

    blobs = await crud_get_all_blobs(
        db, BlobFilterParams(path=share.key, bucket_name=share.bucket)
    )
    if not blobs:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Object not found")

    blob = blobs[0]
    if blob.encrypted:
        raise HTTPException(
            status_code=400,
            detail="Encrypted object cannot be downloaded via share link",
        )

    blob_size = int(getattr(blob, "size", 0) or 0)
    if blob_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Share download loads the object into memory and is limited to "
                f"{MAX_UPLOAD_BYTES} bytes; use a presigned GET for larger objects"
            ),
        )

    try:
        data = await load_blob_bytes(blob)
    except Exception:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail="Object not available"
        ) from None

    claimed = await crud_claim_share_download(db, token)
    if not claimed:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Share not found")

    return Response(
        content=data,
        media_type=blob.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": safe_content_disposition(share.key),
            "Content-Length": str(len(data)),
        },
    )
