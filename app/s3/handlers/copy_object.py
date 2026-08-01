from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from urllib.parse import unquote
from xml.sax.saxutils import escape

from fastapi import Request
from starlette.responses import Response

from app.core.config import MAX_UPLOAD_BYTES, TG_OPAQUE_FILENAMES
from app.crud.blob import crud_create_blob, crud_get_all_blobs
from app.crud.bucket import crud_get_bucket_by_name
from app.models.blob import BlobFilterParams, BlobInCreate
from app.s3.auth import (
    AUTH_MISSING,
    AUTH_OK,
    auth_error_response,
    authorize_request_for_bucket,
    resolve_identity_from_request,
)
from app.s3.blob_io import load_blob_bytes
from app.s3.copy_forward import try_build_cross_bucket_blob_via_forward
from app.s3.errors import s3_error_response
from app.s3.http_range import etag_matches
from app.s3.xml import object_etag
from app.storage import storage
from app.storage.disk_cache import cache_delete
from app.storage.errors import StorageThrottleError, StorageUnavailableError
from app.storage.tg_label import new_storage_id, tg_document_label


def _parse_copy_source(header: str) -> tuple[str, str] | None:
    raw = header.strip()
    if not raw:
        return None
    try:
        decoded = unquote(raw.split("?", 1)[0])
    except Exception:
        return None
    trimmed = decoded[1:] if decoded.startswith("/") else decoded
    slash = trimmed.find("/")
    if slash <= 0:
        return None
    return trimmed[:slash], trimmed[slash + 1 :]


def _fmt_iso(dt: datetime | None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


async def copy_object(
    request: Request,
    bucket_name: str,
    key: str,
    db: AsyncSession,
):
    resource = f"/{bucket_name}/{key}"
    src = _parse_copy_source(request.headers.get("x-amz-copy-source") or "")
    if not src:
        return s3_error_response(
            status_code=400,
            code="InvalidArgument",
            message="Invalid x-amz-copy-source",
            resource=resource,
        )
    src_bucket, src_key = src
    if not src_key:
        return s3_error_response(
            status_code=400,
            code="InvalidArgument",
            message="Invalid x-amz-copy-source key",
            resource=resource,
        )

    directive = (request.headers.get("x-amz-metadata-directive") or "COPY").upper()
    if directive not in {"COPY", "REPLACE"}:
        return s3_error_response(
            status_code=400,
            code="InvalidArgument",
            message=f"Unknown metadata directive '{directive}'",
            resource=resource,
        )

    if src_bucket == bucket_name and src_key == key and directive != "REPLACE":
        return s3_error_response(
            status_code=400,
            code="InvalidRequest",
            message=(
                "This copy request is illegal because it is trying to copy an "
                "object to itself without changing the object's metadata"
            ),
            resource=resource,
        )

    dest_bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not dest_bucket:
        return s3_error_response(
            status_code=404, code="NoSuchBucket", resource=resource
        )
    auth = await authorize_request_for_bucket(dest_bucket, request, db, body=b"")
    if auth != AUTH_OK:
        return auth_error_response(auth, resource)

    source_bucket = await crud_get_bucket_by_name(db, src_bucket)
    if not source_bucket:
        return s3_error_response(
            status_code=404,
            code="NoSuchBucket",
            resource=f"/{src_bucket}",
        )

    source_public = getattr(source_bucket, "is_public", False)
    cross_owner = source_bucket.owner.username != dest_bucket.owner.username
    if cross_owner and not source_public:
        return s3_error_response(
            status_code=403,
            code="AccessDenied",
            message="Access Denied to copy source",
            resource=f"/{src_bucket}/{src_key}",
        )

    if not cross_owner:
        identity = await resolve_identity_from_request(db, request, body=b"")
        if identity is None:
            return auth_error_response(AUTH_MISSING, resource)
        if not identity.can_read(source_bucket):
            return s3_error_response(
                status_code=403,
                code="AccessDenied",
                message="Access Denied to copy source",
                resource=f"/{src_bucket}/{src_key}",
            )

    sources = await crud_get_all_blobs(
        db, BlobFilterParams(path=src_key, bucket_name=src_bucket)
    )
    if not sources:
        return s3_error_response(
            status_code=404,
            code="NoSuchKey",
            resource=f"/{src_bucket}/{src_key}",
        )
    src_blob = sources[0]
    if src_blob.encrypted:
        return s3_error_response(
            status_code=400,
            code="InvalidRequest",
            message="Copying SSE-C objects is not supported",
            resource=resource,
        )

    dest_existing = await crud_get_all_blobs(
        db, BlobFilterParams(path=key, bucket_name=bucket_name)
    )
    update = len(dest_existing) > 0
    previous = dest_existing[0] if update else None

    if src_bucket == bucket_name:
        content_type = (
            request.headers.get("content-type", src_blob.content_type or "")
            if directive == "REPLACE"
            else src_blob.content_type or "application/octet-stream"
        )
        blob = BlobInCreate(
            path=key,
            storage_id=getattr(src_blob, "storage_id", None),
            telegram_grouped_id=getattr(src_blob, "telegram_grouped_id", None),
            telegram_albums=getattr(src_blob, "telegram_albums", None),
            file=src_blob.file or "",
            content_type=content_type,
            size=int(src_blob.size or 0),
            message_id=src_blob.message_id,
            parts=src_blob.parts,
            sse_nonce=src_blob.sse_nonce,
            sse_tag=src_blob.sse_tag,
            encrypted=bool(src_blob.encrypted),
        )
        await crud_create_blob(db, blob, bucket_name, update)
        cache_delete(bucket_name, key)
        if previous:
            from app.s3.object_lifecycle import (
                bypass_trash_requested,
                retire_previous_version,
            )

            await retire_previous_version(
                db,
                previous,
                bucket_name=bucket_name,
                chat_id=getattr(dest_bucket, "telegram_chat_id", None),
                bypass_trash=bypass_trash_requested(request),
            )
        etag = object_etag(blob)
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<CopyObjectResult>"
            f"<LastModified>{_fmt_iso(datetime.now(timezone.utc))}</LastModified>"
            f"<ETag>{escape(etag)}</ETag>"
            "</CopyObjectResult>"
        )
        return Response(content=body, media_type="application/xml", headers={"ETag": etag})

    if directive == "REPLACE":
        content_type = request.headers.get(
            "content-type", src_blob.content_type or "application/octet-stream"
        )
    else:
        content_type = src_blob.content_type or "application/octet-stream"

    src_etag = object_etag(src_blob)
    copy_if_match = request.headers.get("x-amz-copy-source-if-match")
    if copy_if_match and not etag_matches(copy_if_match, src_etag):
        return s3_error_response(
            status_code=412, code="PreconditionFailed", resource=resource
        )
    copy_if_none = request.headers.get("x-amz-copy-source-if-none-match")
    if copy_if_none and etag_matches(copy_if_none, src_etag):
        return s3_error_response(
            status_code=412, code="PreconditionFailed", resource=resource
        )

    existing = await crud_get_all_blobs(
        db, BlobFilterParams(path=key, bucket_name=bucket_name)
    )
    update = len(existing) > 0
    previous = existing[0] if update else None

    try:
        blob = await try_build_cross_bucket_blob_via_forward(
            src_blob=src_blob,
            dest_key=key,
            content_type=content_type,
            source_chat_id=getattr(source_bucket, "telegram_chat_id", None),
            dest_chat_id=getattr(dest_bucket, "telegram_chat_id", None),
            dest_topic_id=getattr(dest_bucket, "telegram_topic_id", None),
        )
    except StorageThrottleError:
        return s3_error_response(status_code=503, code="SlowDown", resource=resource)

    if blob is not None:
        await crud_create_blob(db, blob, bucket_name, update)
        cache_delete(bucket_name, key)
        if previous:
            from app.s3.object_lifecycle import (
                bypass_trash_requested,
                retire_previous_version,
            )

            await retire_previous_version(
                db,
                previous,
                bucket_name=bucket_name,
                chat_id=getattr(dest_bucket, "telegram_chat_id", None),
                bypass_trash=bypass_trash_requested(request),
            )
        etag = object_etag(blob)
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<CopyObjectResult>"
            f"<LastModified>{_fmt_iso(datetime.now(timezone.utc))}</LastModified>"
            f"<ETag>{escape(etag)}</ETag>"
            "</CopyObjectResult>"
        )
        return Response(content=body, media_type="application/xml", headers={"ETag": etag})

    # Slow path: download-then-upload (not server-side); cap memory like PutObject.
    src_size = int(getattr(src_blob, "size", 0) or 0)
    if src_size > MAX_UPLOAD_BYTES:
        return s3_error_response(
            status_code=400,
            code="EntityTooLarge",
            message=(
                f"CopyObject loads the source into memory and is limited to "
                f"{MAX_UPLOAD_BYTES} bytes; use GetObject + PutObject or multipart "
                f"for larger objects"
            ),
            resource=resource,
        )

    try:
        data = await load_blob_bytes(src_blob)
    except Exception:
        return s3_error_response(
            status_code=404,
            code="NoSuchKey",
            message="Source object not available",
            resource=f"/{src_bucket}/{src_key}",
        )

    try:
        sid = new_storage_id() if TG_OPAQUE_FILENAMES else None
        tg_name = tg_document_label(sid) if sid else key
        put_result = await storage.put_file(
            data,
            tg_name,
            chat_id=getattr(dest_bucket, "telegram_chat_id", None),
            topic_id=getattr(dest_bucket, "telegram_topic_id", None),
        )
    except StorageThrottleError:
        return s3_error_response(status_code=503, code="SlowDown", resource=resource)
    except StorageUnavailableError:
        return s3_error_response(
            status_code=503, code="ServiceUnavailable", resource=resource
        )

    blob = BlobInCreate(
        path=key,
        storage_id=sid,
        file=put_result.file_id,
        content_type=content_type,
        size=len(data),
        message_id=put_result.message_id,
        parts=None,
        encrypted=False,
    )
    await crud_create_blob(db, blob, bucket_name, update)
    cache_delete(bucket_name, key)

    if previous:
        from app.s3.object_lifecycle import (
            bypass_trash_requested,
            retire_previous_version,
        )

        await retire_previous_version(
            db,
            previous,
            bucket_name=bucket_name,
            chat_id=getattr(dest_bucket, "telegram_chat_id", None),
            bypass_trash=bypass_trash_requested(request),
        )

    etag = object_etag(blob)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<CopyObjectResult>"
        f"<LastModified>{_fmt_iso(datetime.now(timezone.utc))}</LastModified>"
        f"<ETag>{escape(etag)}</ETag>"
        "</CopyObjectResult>"
    )
    return Response(content=body, media_type="application/xml", headers={"ETag": etag})
