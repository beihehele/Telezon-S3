from datetime import timedelta

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

from app.api.v1.object_list import list_objects_page
import jwt
from jwt import PyJWTError

from app.core.config import MEDIA_TICKET_MAX_SECONDS, SECRET_KEY, CONTENT_PROXY_MAX_FULL_BYTES
from app.core.media_ticket import create_media_ticket, decode_media_ticket
from app.core.token import ALGORITHM, get_current_user
from app.crud.user import crud_get_user_by_username
from app.models.token import TokenPayload
from app.crud.blob import crud_get_blob_in_bucket, crud_rename_blob
from app.crud.bucket import crud_get_bucket_by_name
from app.db.session import get_database
from app.models.user import User
from app.s3.blob_io import (
    inline_content_disposition,
    load_blob_byte_range,
    safe_content_disposition,
)
from app.s3.http_range import InvalidRange, parse_bytes_range
from app.s3.object_lifecycle import delete_live_object
from app.s3.xml import object_etag
from app.storage.disk_cache import cache_delete

router = APIRouter(prefix="/buckets", tags=["Objects"])
_optional_bearer = HTTPBearer(auto_error=False)


async def _optional_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    db: AsyncSession = Depends(get_database),
) -> User | None:
    if not cred:
        return None
    try:
        payload = jwt.decode(cred.credentials, str(SECRET_KEY), algorithms=[ALGORITHM])
        token_data = TokenPayload(**payload)
    except PyJWTError:
        return None
    db_user = await crud_get_user_by_username(db, token_data.username)
    if not db_user:
        return None
    return User(**db_user.model_dump())


def _require_bucket_owner(bucket, current_user: User):
    if not bucket:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Bucket not found")
    if bucket.owner.username != current_user.username:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Not bucket owner")


async def _authorize_content(
    *,
    bucket_name: str,
    key: str,
    db: AsyncSession,
    bearer_user: User | None,
    media_token: str | None,
) -> None:
    if media_token:
        try:
            claims = decode_media_ticket(media_token)
        except ValueError as exc:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN, detail="Invalid or expired media token"
            ) from exc
        if claims.bucket != bucket_name or claims.key != key:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN, detail="Media token does not match object"
            )
        return
    if not bearer_user:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Not authenticated")
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    _require_bucket_owner(bucket, bearer_user)


class ContentTicketResponse(BaseModel):
    media_token: str
    expires_in: int


@router.post(
    "/{bucket_name}/objects/{key:path}/content-ticket",
    response_model=ContentTicketResponse,
)
async def create_content_ticket(
    bucket_name: str,
    key: str,
    expires_in: int = Query(600, ge=60, le=MEDIA_TICKET_MAX_SECONDS),
    db: AsyncSession = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    _require_bucket_owner(bucket, current_user)
    blob = await crud_get_blob_in_bucket(db, bucket_name, key)
    if not blob:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Object not found")
    if blob.encrypted:
        raise HTTPException(
            status_code=400,
            detail="SSE-C objects cannot use content tickets",
        )
    expires_in = min(expires_in, MEDIA_TICKET_MAX_SECONDS)
    token = create_media_ticket(
        username=current_user.username,
        bucket=bucket_name,
        key=key,
        expires_delta=timedelta(seconds=expires_in),
    )
    return ContentTicketResponse(media_token=token, expires_in=expires_in)


async def _serve_object_content(
    *,
    bucket_name: str,
    key: str,
    request: Request,
    disposition: str,
    db: AsyncSession,
) -> Response:
    blob = await crud_get_blob_in_bucket(db, bucket_name, key)
    if not blob:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Object not found")
    if blob.encrypted:
        raise HTTPException(
            status_code=400,
            detail="SSE-C objects are not available via content proxy",
        )

    total = int(blob.size or 0)
    range_header = request.headers.get("range")
    byte_range: tuple[int, int] | None = None
    if range_header:
        try:
            byte_range = parse_bytes_range(range_header, max(total, 1))
        except InvalidRange:
            return Response(
                status_code=416,
                headers={
                    "Content-Range": f"bytes */{total}",
                    "Accept-Ranges": "bytes",
                },
            )

    if byte_range is not None:
        start, end = byte_range
        data = await load_blob_byte_range(blob, start, end)
        cd = (
            inline_content_disposition(key)
            if disposition == "inline"
            else safe_content_disposition(key)
        )
        return Response(
            content=data,
            status_code=206,
            media_type=blob.content_type or "application/octet-stream",
            headers={
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Content-Length": str(len(data)),
                "Accept-Ranges": "bytes",
                "Content-Disposition": cd,
            },
        )

    if total > CONTENT_PROXY_MAX_FULL_BYTES:
        return Response(
            status_code=413,
            content=(
                "Object too large for full download via content proxy; "
                "use Range requests or presigned GET."
            ),
            media_type="text/plain",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes */{total}",
            },
        )

    if total <= 0:
        data = b""
    else:
        from app.s3.mp4_index import ensure_mp4_moov_offset

        await ensure_mp4_moov_offset(blob, bucket_name, key)
        data = await load_blob_byte_range(blob, 0, total - 1)
    cd = (
        inline_content_disposition(key)
        if disposition == "inline"
        else safe_content_disposition(key)
    )
    return Response(
        content=data,
        media_type=blob.content_type or "application/octet-stream",
        headers={
            "Content-Length": str(len(data)),
            "Accept-Ranges": "bytes",
            "Content-Disposition": cd,
        },
    )


@router.get("/{bucket_name}/objects/{key:path}/content")
async def get_object_content(
    bucket_name: str,
    key: str,
    request: Request,
    disposition: str = Query("inline", pattern="^(inline|attachment)$"),
    media_token: str | None = Query(
        None, description="Short-lived content ticket for <video src> (no Bearer header)"
    ),
    db: AsyncSession = Depends(get_database),
    bearer_user: User | None = Depends(_optional_current_user),
):
    """Byte delivery for console preview (Range-aware). Auth: Bearer JWT or media_token."""
    await _authorize_content(
        bucket_name=bucket_name,
        key=key,
        db=db,
        bearer_user=bearer_user,
        media_token=media_token,
    )
    return await _serve_object_content(
        bucket_name=bucket_name,
        key=key,
        request=request,
        disposition=disposition,
        db=db,
    )


class ObjectListItem(BaseModel):
    key: str
    size: int
    last_modified: str
    etag: str
    content_type: str


class ObjectListResponse(BaseModel):
    prefix: str
    contents: list[ObjectListItem]
    common_prefixes: list[str]
    is_truncated: bool
    next_continuation_token: str | None = None


class ObjectMetadataResponse(BaseModel):
    key: str
    size: int
    last_modified: str
    etag: str
    content_type: str
    encrypted: bool = False


class RenameBody(BaseModel):
    from_key: str = Field(alias="from", min_length=1)
    to_key: str = Field(alias="to", min_length=1)

    model_config = {"populate_by_name": True}


class BatchDeleteBody(BaseModel):
    keys: list[str] = Field(..., min_length=1, max_length=1000)


class BatchDeleteResult(BaseModel):
    deleted: list[str]
    errors: list[dict[str, str]]


@router.get("/{bucket_name}/objects", response_model=ObjectListResponse)
async def list_objects_rest(
    bucket_name: str,
    prefix: str = Query("", alias="prefix"),
    delimiter: str = Query("", alias="delimiter"),
    continuation_token: str | None = Query(None, alias="continuation-token"),
    start_after: str = Query("", alias="start-after"),
    max_keys: int = Query(1000, alias="max-keys", ge=1, le=1000),
    db: AsyncSession = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    _require_bucket_owner(bucket, current_user)
    contents, common_prefixes, is_truncated, next_token = await list_objects_page(
        db,
        bucket_name,
        prefix=prefix,
        delimiter=delimiter,
        continuation_token=continuation_token,
        start_after=start_after,
        max_keys=max_keys,
    )
    return ObjectListResponse(
        prefix=prefix,
        contents=[ObjectListItem(**item) for item in contents],
        common_prefixes=common_prefixes,
        is_truncated=is_truncated,
        next_continuation_token=next_token,
    )


@router.get(
    "/{bucket_name}/objects/{key:path}/metadata",
    response_model=ObjectMetadataResponse,
)
async def get_object_metadata(
    bucket_name: str,
    key: str,
    db: AsyncSession = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    _require_bucket_owner(bucket, current_user)
    blob = await crud_get_blob_in_bucket(db, bucket_name, key)
    if not blob:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Object not found")
    updated = getattr(blob, "updated_at", None) or getattr(blob, "created_at", None)
    last_modified = ""
    if updated is not None:
        try:
            last_modified = updated.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except Exception:
            last_modified = str(updated)
    return ObjectMetadataResponse(
        key=blob.path,
        size=int(blob.size or 0),
        last_modified=last_modified,
        etag=object_etag(blob),
        content_type=blob.content_type or "application/octet-stream",
        encrypted=bool(blob.encrypted),
    )


@router.delete("/{bucket_name}/objects/{key:path}", status_code=204)
async def delete_object_rest(
    bucket_name: str,
    key: str,
    db: AsyncSession = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    _require_bucket_owner(bucket, current_user)
    deleted = await delete_live_object(
        db,
        bucket_name=bucket_name,
        key=key,
        chat_id=getattr(bucket, "telegram_chat_id", None),
        deleted_by=current_user.username,
        reason="rest_delete",
    )
    if deleted is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Object not found")
    cache_delete(bucket_name, key)


@router.post("/{bucket_name}/objects/batch-delete", response_model=BatchDeleteResult)
async def batch_delete_objects_rest(
    bucket_name: str,
    body: BatchDeleteBody,
    db: AsyncSession = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    _require_bucket_owner(bucket, current_user)
    deleted: list[str] = []
    errors: list[dict[str, str]] = []
    chat_id = getattr(bucket, "telegram_chat_id", None)
    for key in body.keys:
        try:
            result = await delete_live_object(
                db,
                bucket_name=bucket_name,
                key=key,
                chat_id=chat_id,
                deleted_by=current_user.username,
                reason="rest_batch_delete",
            )
            if result is None:
                errors.append({"key": key, "message": "Object not found"})
            else:
                cache_delete(bucket_name, key)
                deleted.append(key)
        except Exception as exc:
            errors.append({"key": key, "message": str(exc) or "delete failed"})
    return BatchDeleteResult(deleted=deleted, errors=errors)


@router.post("/{bucket_name}/objects/rename")
async def rename_object(
    bucket_name: str,
    body: RenameBody,
    db: AsyncSession = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    _require_bucket_owner(bucket, current_user)

    try:
        blob = await crud_rename_blob(
            db, bucket_name, body.from_key, body.to_key
        )
    except LookupError:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Source not found") from None
    except FileExistsError:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail="Destination key already exists",
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    cache_delete(bucket_name, body.from_key)
    cache_delete(bucket_name, body.to_key)
    return {
        "bucket": bucket_name,
        "from": body.from_key,
        "to": body.to_key,
        "etag": object_etag(blob),
        "path": blob.path,
    }
