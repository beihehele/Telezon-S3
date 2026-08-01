from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from email.utils import format_datetime

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from app.core.config import MAX_UPLOAD_BYTES, TG_OPAQUE_FILENAMES
from app.crud.blob import crud_create_blob, crud_get_all_blobs
from app.crud.bucket import crud_get_bucket_by_name
from app.db.session import get_database
from app.models.blob import BlobFilterParams, BlobInCreate
from app.s3.auth import (
    AUTH_OK,
    auth_error_response,
    authorize_request_for_bucket,
    precheck_request_for_bucket,
)
from app.s3.body import BodyTooLarge, read_body_capped, reject_oversized_content_length
from app.s3.errors import s3_error_response
from app.s3.list_query import looks_like_list_objects
from app.s3.handlers.list_objects import list_objects
from app.s3.handlers import multipart as multipart_handlers
from app.s3.handlers import copy_object as copy_handlers
from app.s3.http_range import (
    InvalidRange,
    evaluate_conditionals,
    parse_bytes_range,
)
from app.s3.sse import SseError, decrypt_sse_c, encrypt_sse_c, sse_key_md5_b64
from app.s3.subresources import reject_unsupported_subresource
from app.s3.xml import object_etag
from app.storage import storage
from app.storage.disk_cache import cache_delete, cache_get, cache_put
from app.storage.tg_label import new_storage_id, tg_document_label
from app.storage.errors import StorageThrottleError, StorageUnavailableError

router = APIRouter(tags=["S3"])


def _empty_key_error(bucket_name: str):
    return s3_error_response(
        status_code=400,
        code="InvalidRequest",
        resource=f"/{bucket_name}/",
    )


def _entity_too_large(resource: str, size: int):
    return s3_error_response(
        status_code=400,
        code="EntityTooLarge",
        message=(
            f"Object size {size} exceeds maximum allowed size "
            f"{MAX_UPLOAD_BYTES} bytes"
        ),
        resource=resource,
    )


def _slow_down(resource: str):
    return s3_error_response(status_code=503, code="SlowDown", resource=resource)


def _service_unavailable(resource: str):
    return s3_error_response(
        status_code=503, code="ServiceUnavailable", resource=resource
    )


async def _load_bucket_or_404(db, bucket_name: str, resource: str):
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not bucket:
        return None, s3_error_response(
            status_code=404, code="NoSuchBucket", resource=resource
        )
    return bucket, None


def _sse_aad(bucket_name: str, key: str) -> bytes:
    return f"{bucket_name}/{key}".encode("utf-8")


def _blob_last_modified(blob) -> datetime | None:
    last_modified = getattr(blob, "updated_at", None) or getattr(
        blob, "created_at", None
    )
    if isinstance(last_modified, datetime):
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)
        return last_modified
    return None


async def _load_object_bytes(blob, *, bucket_name: str, key: str, sse_key: str | None):
    cached = None if blob.encrypted or blob.parts else cache_get(bucket_name, key)
    if cached is not None:
        return cached, False

    if blob.parts:
        chunks: list[bytes] = []
        for part in blob.parts:
            file_obj = await storage.get_file(part.file_id)
            data = file_obj.read() if hasattr(file_obj, "read") else file_obj
            if isinstance(data, memoryview):
                data = data.tobytes()
            if isinstance(data, str):
                data = data.encode()
            chunks.append(data)
        return b"".join(chunks), False

    result_file = await storage.get_file(blob.file)
    data = result_file.read() if hasattr(result_file, "read") else result_file
    if isinstance(data, memoryview):
        data = data.tobytes()
    if isinstance(data, str):
        data = data.encode()

    if blob.encrypted:
        data = decrypt_sse_c(
            data,
            sse_key,
            blob.sse_nonce or "",
            blob.sse_tag or "",
            aad=_sse_aad(bucket_name, key),
        )
        return data, True

    cache_put(bucket_name, key, data)
    return data, False


@router.put("/{bucket_name}/{key:path}")
async def put_object(
    request: Request,
    bucket_name: str,
    key: str,
    db: AsyncSession = Depends(get_database),
):
    if not key:
        return _empty_key_error(bucket_name)

    resource = f"/{bucket_name}/{key}"
    blocked = reject_unsupported_subresource(request, resource)
    if blocked:
        return blocked

    if request.headers.get("x-amz-copy-source"):
        return await copy_handlers.copy_object(request, bucket_name, key, db)

    upload_id = request.query_params.get("uploadId")
    part_number = request.query_params.get("partNumber")
    if upload_id and part_number:
        return await multipart_handlers.upload_part(
            request,
            bucket_name,
            key,
            db,
            upload_id=upload_id,
            part_number=int(part_number),
        )

    bucket, err = await _load_bucket_or_404(db, bucket_name, resource)
    if err:
        return err

    early = reject_oversized_content_length(request, resource)
    if early:
        return early

    pre = await precheck_request_for_bucket(bucket, request, db)
    if pre != AUTH_OK:
        return auth_error_response(pre, resource)

    try:
        body = await read_body_capped(request, MAX_UPLOAD_BYTES)
    except BodyTooLarge as exc:
        return _entity_too_large(resource, exc.size)

    auth = await authorize_request_for_bucket(bucket, request, db, body=body)
    if auth != AUTH_OK:
        return auth_error_response(auth, resource)

    size = len(body)
    sse_key = request.headers.get("x-amz-server-side-encryption-customer-key")
    sse_md5 = request.headers.get("x-amz-server-side-encryption-customer-key-md5")
    sse_nonce = None
    sse_tag = None
    encrypted = False
    store_body = body
    response_headers = {}
    if sse_key:
        try:
            if sse_md5 and sse_md5 != sse_key_md5_b64(sse_key):
                return s3_error_response(
                    status_code=400,
                    code="InvalidRequest",
                    message="SSE customer key MD5 mismatch",
                    resource=resource,
                )
            store_body, sse_nonce, sse_tag = encrypt_sse_c(
                body, sse_key, aad=_sse_aad(bucket_name, key)
            )
            encrypted = True
            response_headers["x-amz-server-side-encryption-customer-algorithm"] = (
                "AES256"
            )
            response_headers["x-amz-server-side-encryption-customer-key-md5"] = (
                sse_key_md5_b64(sse_key)
            )
        except SseError as exc:
            return s3_error_response(
                status_code=400,
                code="InvalidRequest",
                message=str(exc),
                resource=resource,
            )

    filters = BlobFilterParams(path=key, bucket_name=bucket_name)
    blobs = await crud_get_all_blobs(db, filters)
    update = len(blobs) > 0
    previous_message_id = blobs[0].message_id if update else None
    previous_parts = blobs[0].parts if update else None
    blob = BlobInCreate(**blobs[0].model_dump()) if update else BlobInCreate(path=key)

    blob.content_type = request.headers.get("content-type", "application/octet-stream")
    blob.size = size
    blob.encrypted = encrypted
    blob.sse_nonce = sse_nonce
    blob.sse_tag = sse_tag
    blob.parts = None

    tg_label = key
    if TG_OPAQUE_FILENAMES:
        blob.storage_id = new_storage_id()
        tg_label = tg_document_label(blob.storage_id)

    try:
        put_result = await storage.put_file(
            store_body,
            tg_label,
            chat_id=getattr(bucket, "telegram_chat_id", None),
            topic_id=getattr(bucket, "telegram_topic_id", None),
        )
    except StorageThrottleError:
        return _slow_down(resource)
    except StorageUnavailableError:
        return _service_unavailable(resource)

    blob.file = put_result.file_id
    blob.message_id = put_result.message_id
    await crud_create_blob(db, blob, bucket_name, update)
    cache_delete(bucket_name, key)

    if update and (previous_message_id is not None or previous_parts):
        from app.s3.object_lifecycle import (
            bypass_trash_requested,
            retire_previous_version,
        )

        previous_snapshot = blobs[0]
        await retire_previous_version(
            db,
            previous_snapshot,
            bucket_name=bucket_name,
            chat_id=getattr(bucket, "telegram_chat_id", None),
            bypass_trash=bypass_trash_requested(request),
        )

    response_headers["ETag"] = object_etag(blob)
    return Response(status_code=200, headers=response_headers)


@router.post("/{bucket_name}/{key:path}")
async def post_object(
    request: Request,
    bucket_name: str,
    key: str,
    db: AsyncSession = Depends(get_database),
):
    if not key:
        return _empty_key_error(bucket_name)
    resource = f"/{bucket_name}/{key}"
    blocked = reject_unsupported_subresource(request, resource)
    if blocked:
        return blocked
    if "uploads" in request.query_params:
        return await multipart_handlers.create_multipart_upload(
            request, bucket_name, key, db
        )
    upload_id = request.query_params.get("uploadId")
    if upload_id:
        return await multipart_handlers.complete_multipart_upload(
            request, bucket_name, key, db, upload_id=upload_id
        )
    return s3_error_response(
        status_code=501,
        code="NotImplemented",
        resource=resource,
    )


@router.get("/{bucket_name}/{key:path}")
async def get_object(
    request: Request,
    bucket_name: str,
    key: str,
    db: AsyncSession = Depends(get_database),
):
    if not key:
        if looks_like_list_objects(request):
            return await list_objects(request, bucket_name, db)
        return _empty_key_error(bucket_name)

    resource = f"/{bucket_name}/{key}"
    blocked = reject_unsupported_subresource(request, resource)
    if blocked:
        return blocked

    upload_id = request.query_params.get("uploadId")
    if upload_id:
        return await multipart_handlers.list_parts(
            request, bucket_name, key, db, upload_id=upload_id
        )

    bucket, err = await _load_bucket_or_404(db, bucket_name, resource)
    if err:
        return err

    auth = await authorize_request_for_bucket(bucket, request, db)
    if auth != AUTH_OK and not getattr(bucket, "is_public", False):
        return auth_error_response(auth, resource)

    filters = BlobFilterParams(path=key, bucket_name=bucket_name)
    blobs = await crud_get_all_blobs(db, filters)
    if not blobs:
        return s3_error_response(status_code=404, code="NoSuchKey", resource=resource)

    blob = blobs[0]
    etag = object_etag(blob)
    last_modified = _blob_last_modified(blob)
    cond = evaluate_conditionals(
        etag=etag,
        last_modified=last_modified,
        if_match=request.headers.get("if-match"),
        if_none_match=request.headers.get("if-none-match"),
        if_modified_since=request.headers.get("if-modified-since"),
        if_unmodified_since=request.headers.get("if-unmodified-since"),
    )
    if cond == "not_modified":
        return Response(status_code=304, headers={"ETag": etag})
    if cond == "precondition_failed":
        return s3_error_response(
            status_code=412,
            code="PreconditionFailed",
            message="At least one of the preconditions you specified did not hold",
            resource=resource,
        )

    headers = {
        "Content-Length": str(blob.size),
        "ETag": etag,
        "Accept-Ranges": "bytes",
    }
    if last_modified is not None:
        headers["Last-Modified"] = format_datetime(last_modified, usegmt=True)

    sse_key = request.headers.get("x-amz-server-side-encryption-customer-key")
    if blob.encrypted and not sse_key:
        return s3_error_response(
            status_code=400,
            code="InvalidRequest",
            message="Missing SSE customer key",
            resource=resource,
        )

    try:
        data, was_encrypted = await _load_object_bytes(
            blob, bucket_name=bucket_name, key=key, sse_key=sse_key
        )
    except StorageThrottleError:
        return _slow_down(resource)
    except StorageUnavailableError:
        return _service_unavailable(resource)
    except Exception:
        if blob.encrypted:
            return s3_error_response(
                status_code=403,
                code="AccessDenied",
                message="SSE decryption failed",
                resource=resource,
            )
        raise

    if was_encrypted:
        headers["Content-Length"] = str(len(data))
        headers["x-amz-server-side-encryption-customer-algorithm"] = "AES256"
        try:
            headers["x-amz-server-side-encryption-customer-key-md5"] = sse_key_md5_b64(
                sse_key
            )
        except SseError:
            pass

    range_header = request.headers.get("range")
    if range_header:
        try:
            bounds = parse_bytes_range(range_header, len(data))
        except InvalidRange:
            return Response(
                status_code=416,
                headers={
                    "Content-Range": f"bytes */{len(data)}",
                    "Accept-Ranges": "bytes",
                },
            )
        if bounds is not None:
            start, end = bounds
            chunk = data[start : end + 1]
            headers["Content-Length"] = str(len(chunk))
            headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
            return Response(
                content=chunk,
                status_code=206,
                media_type=blob.content_type or "application/octet-stream",
                headers=headers,
            )

    return Response(
        content=data,
        media_type=blob.content_type or "application/octet-stream",
        headers=headers,
    )


@router.head("/{bucket_name}/{key:path}")
async def head_object(
    request: Request,
    bucket_name: str,
    key: str,
    db: AsyncSession = Depends(get_database),
):
    if not key:
        return _empty_key_error(bucket_name)

    resource = f"/{bucket_name}/{key}"
    blocked = reject_unsupported_subresource(request, resource)
    if blocked:
        return blocked

    bucket, err = await _load_bucket_or_404(db, bucket_name, resource)
    if err:
        return err

    auth = await authorize_request_for_bucket(bucket, request, db)
    if auth != AUTH_OK and not getattr(bucket, "is_public", False):
        return auth_error_response(auth, resource)

    filters = BlobFilterParams(path=key, bucket_name=bucket_name)
    blobs = await crud_get_all_blobs(db, filters)
    if not blobs:
        return s3_error_response(status_code=404, code="NoSuchKey", resource=resource)

    blob = blobs[0]
    etag = object_etag(blob)
    last_modified = _blob_last_modified(blob) or datetime.now(timezone.utc)
    cond = evaluate_conditionals(
        etag=etag,
        last_modified=last_modified,
        if_match=request.headers.get("if-match"),
        if_none_match=request.headers.get("if-none-match"),
        if_modified_since=request.headers.get("if-modified-since"),
        if_unmodified_since=request.headers.get("if-unmodified-since"),
    )
    if cond == "not_modified":
        return Response(status_code=304, headers={"ETag": etag})
    if cond == "precondition_failed":
        return s3_error_response(
            status_code=412,
            code="PreconditionFailed",
            message="At least one of the preconditions you specified did not hold",
            resource=resource,
        )

    return Response(
        status_code=200,
        headers={
            "Content-Length": str(blob.size),
            "Content-Type": blob.content_type or "application/octet-stream",
            "ETag": etag,
            "Last-Modified": format_datetime(last_modified, usegmt=True),
            "Accept-Ranges": "bytes",
        },
    )


@router.delete("/{bucket_name}/{key:path}")
async def delete_object(
    request: Request,
    bucket_name: str,
    key: str,
    db: AsyncSession = Depends(get_database),
):
    if not key:
        return _empty_key_error(bucket_name)

    resource = f"/{bucket_name}/{key}"
    blocked = reject_unsupported_subresource(request, resource)
    if blocked:
        return blocked

    upload_id = request.query_params.get("uploadId")
    if upload_id:
        return await multipart_handlers.abort_multipart_upload(
            request, bucket_name, key, db, upload_id=upload_id
        )

    bucket, err = await _load_bucket_or_404(db, bucket_name, resource)
    if err:
        return err

    auth = await authorize_request_for_bucket(bucket, request, db)
    if auth != AUTH_OK:
        return auth_error_response(auth, resource)

    from app.s3.object_lifecycle import bypass_trash_requested, delete_live_object

    await delete_live_object(
        db,
        bucket_name=bucket_name,
        key=key,
        chat_id=getattr(bucket, "telegram_chat_id", None),
        reason="delete_object",
        bypass_trash=bypass_trash_requested(request),
    )

    return Response(status_code=204)
