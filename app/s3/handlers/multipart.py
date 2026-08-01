from sqlalchemy.ext.asyncio import AsyncSession
import hashlib
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from fastapi import Request
from starlette.responses import Response

from app.core.config import (
    MAX_UPLOAD_BYTES,
    MULTIPART_MAX_PARTS,
    MULTIPART_MIN_PART_BYTES,
    TG_ALBUM_MAX_ITEMS,
)
from app.crud.blob import crud_create_blob, crud_get_all_blobs
from app.crud.bucket import crud_get_bucket_by_name
from app.crud.multipart import (
    crud_create_multipart_upload,
    crud_delete_multipart_upload,
    crud_get_multipart_upload,
    crud_get_parts_for_complete,
    crud_list_parts,
    crud_upsert_part,
)
from app.models.blob import BlobFilterParams, BlobInCreate, BlobPart, TelegramAlbumMeta
from app.s3.auth import (
    AUTH_OK,
    auth_error_response,
    authorize_request_for_bucket,
    extract_access_key,
    precheck_request_for_bucket,
    resolve_identity,
)
from app.s3 import stream_upload
from app.s3.body import (
    BodyTooLarge,
    read_body_capped,
    reject_oversized_content_length,
    stream_body_to_file,
)
from app.s3.stream_upload import SHA_MISMATCH
from app.s3.errors import s3_error_response
from app.storage import storage
from app.storage.disk_cache import cache_delete
from app.storage.errors import StorageThrottleError, StorageUnavailableError
from app.storage.mpu_staging import (
    part_staging_path,
    part_tg_upload_path,
    remove_upload_staging,
    staging_enabled,
)
from app.storage.tg_label import tg_document_label

# Complete XML is small; still cap to avoid abuse.
_MAX_COMPLETE_XML_BYTES = 256 * 1024


def _etag_for_bytes(data: bytes) -> str:
    return f'"{hashlib.md5(data).hexdigest()}"'


def _norm_etag(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().strip('"')


async def _upload_owner_ok(upload: dict, bucket, request: Request, db) -> bool:
    access_key = extract_access_key(request)
    if not access_key:
        return False
    identity = await resolve_identity(db, access_key)
    if not identity:
        return False
    return identity.can_write(bucket)


def _parse_complete_xml(raw: bytes):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("unsafe xml")
    if len(raw) > _MAX_COMPLETE_XML_BYTES:
        raise ValueError("xml too large")
    return ET.fromstring(raw.decode("utf-8"))


async def _cleanup_existing_blob(
    db, bucket, bucket_name: str, key: str, *, bypass_trash: bool = False
) -> None:
    """Park the previous live object in trash (or hard-delete) before Complete."""
    existing = await crud_get_all_blobs(
        db, BlobFilterParams(path=key, bucket_name=bucket_name)
    )
    if not existing:
        return
    from app.s3.object_lifecycle import retire_previous_version

    await retire_previous_version(
        db,
        existing[0],
        bucket_name=bucket_name,
        chat_id=getattr(bucket, "telegram_chat_id", None),
        bypass_trash=bypass_trash,
        deleted_by="",
    )


async def create_multipart_upload(
    request: Request,
    bucket_name: str,
    key: str,
    db: AsyncSession,
):
    resource = f"/{bucket_name}/{key}"
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not bucket:
        return s3_error_response(status_code=404, code="NoSuchBucket", resource=resource)
    auth = await authorize_request_for_bucket(bucket, request, db)
    if auth != AUTH_OK:
        return auth_error_response(auth, resource)
    content_type = request.headers.get("content-type", "application/octet-stream")
    upload_id = await crud_create_multipart_upload(
        db,
        bucket=bucket_name,
        key=key,
        content_type=content_type,
        owner_access_key=bucket.owner.access_key_id,
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<InitiateMultipartUploadResult>"
        f"<Bucket>{escape(bucket_name)}</Bucket>"
        f"<Key>{escape(key)}</Key>"
        f"<UploadId>{escape(upload_id)}</UploadId>"
        "</InitiateMultipartUploadResult>"
    )
    return Response(content=body, media_type="application/xml")


async def upload_part(
    request: Request,
    bucket_name: str,
    key: str,
    db: AsyncSession,
    upload_id: str,
    part_number: int,
):
    resource = f"/{bucket_name}/{key}"
    if part_number < 1 or part_number > MULTIPART_MAX_PARTS:
        return s3_error_response(status_code=400, code="InvalidRequest", resource=resource)

    upload = await crud_get_multipart_upload(db, upload_id)
    if not upload or upload["bucket"] != bucket_name or upload["key"] != key:
        return s3_error_response(status_code=404, code="NoSuchUpload", resource=resource)

    bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not bucket:
        return s3_error_response(status_code=404, code="NoSuchBucket", resource=resource)

    early = reject_oversized_content_length(request, resource)
    if early:
        return early

    pre = await precheck_request_for_bucket(bucket, request, db)
    if pre != AUTH_OK:
        return auth_error_response(pre, resource)

    if not staging_enabled():
        return s3_error_response(
            status_code=503,
            code="ServiceUnavailable",
            message="MPU_STAGING_DIR is not configured",
            resource=resource,
        )

    pre_auth = await stream_upload.authorize_before_stream(bucket, request, db)
    if pre_auth not in (AUTH_OK, stream_upload.DEFER_STREAM_AUTH):
        return auth_error_response(pre_auth, resource)

    path = part_staging_path(upload_id, part_number)
    try:
        size, md5_hex, sha256_hex = await stream_body_to_file(
            request, path, MAX_UPLOAD_BYTES
        )
    except BodyTooLarge as exc:
        return s3_error_response(
            status_code=400,
            code="EntityTooLarge",
            message=(
                f"Object size {exc.size} exceeds maximum allowed size "
                f"{MAX_UPLOAD_BYTES} bytes"
            ),
            resource=resource,
        )
    except OSError:
        return s3_error_response(
            status_code=503,
            code="ServiceUnavailable",
            message="Failed to stage multipart part",
            resource=resource,
        )

    auth = await stream_upload.finalize_streamed_payload(
        bucket,
        request,
        db,
        sha256_hex=sha256_hex,
        staging_path=path,
        pre_authenticated=pre_auth == AUTH_OK,
    )
    if auth == SHA_MISMATCH:
        return s3_error_response(
            status_code=400,
            code="InvalidRequest",
            message="x-amz-content-sha256 does not match request payload",
            resource=resource,
        )
    if auth != AUTH_OK:
        return auth_error_response(auth, resource)
    if not await _upload_owner_ok(upload, bucket, request, db):
        path.unlink(missing_ok=True)
        return s3_error_response(status_code=403, code="AccessDenied", resource=resource)

    etag = f'"{md5_hex}"'
    previous = await crud_upsert_part(
        db,
        upload_id=upload_id,
        part_number=part_number,
        etag=etag,
        size=size,
        file_id="",
        message_id=None,
        staging_path=f"{upload_id}/part-{part_number}",
    )
    if (
        previous
        and previous.get("message_id") is not None
    ):
        from app.ops.tg_delete import safe_delete_tg_message

        await safe_delete_tg_message(
            db,
            previous["message_id"],
            chat_id=getattr(bucket, "telegram_chat_id", None),
            reason="multipart_part_replaced",
        )
    return Response(status_code=200, headers={"ETag": etag})


async def complete_multipart_upload(
    request: Request,
    bucket_name: str,
    key: str,
    db: AsyncSession,
    upload_id: str,
):
    resource = f"/{bucket_name}/{key}"
    upload = await crud_get_multipart_upload(db, upload_id)
    if not upload or upload["bucket"] != bucket_name or upload["key"] != key:
        return s3_error_response(status_code=404, code="NoSuchUpload", resource=resource)

    bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not bucket:
        return s3_error_response(status_code=404, code="NoSuchBucket", resource=resource)

    pre = await precheck_request_for_bucket(bucket, request, db)
    if pre != AUTH_OK:
        return auth_error_response(pre, resource)

    # Complete body is XML only; require Content-Length when present to be sane,
    # but always hard-cap the read to avoid DoS.
    content_length = request.headers.get("content-length")
    if content_length is not None:
        if not content_length.isdigit() or int(content_length) > _MAX_COMPLETE_XML_BYTES:
            return s3_error_response(
                status_code=400, code="InvalidRequest", resource=resource
            )
    try:
        raw = await read_body_capped(request, _MAX_COMPLETE_XML_BYTES)
    except BodyTooLarge:
        return s3_error_response(status_code=400, code="InvalidRequest", resource=resource)

    auth = await authorize_request_for_bucket(bucket, request, db, body=raw)
    if auth != AUTH_OK:
        return auth_error_response(auth, resource)
    if not await _upload_owner_ok(upload, bucket, request, db):
        return s3_error_response(status_code=403, code="AccessDenied", resource=resource)

    try:
        root = _parse_complete_xml(raw)
    except (ET.ParseError, ValueError, UnicodeDecodeError):
        return s3_error_response(status_code=400, code="InvalidRequest", resource=resource)

    requested = []
    for part in root.findall("Part"):
        num = part.findtext("PartNumber")
        etag = part.findtext("ETag")
        if num is None:
            continue
        requested.append((int(num), _norm_etag(etag)))

    if not requested:
        return s3_error_response(status_code=400, code="InvalidRequest", resource=resource)

    rows = await crud_get_parts_for_complete(
        db, upload_id, [n for n, _ in requested]
    )
    by_num = {row["part_number"]: row for row in rows}
    if len(by_num) != len(requested):
        return s3_error_response(status_code=400, code="InvalidPart", resource=resource)
    for num, etag in requested:
        stored = _norm_etag(by_num[num].get("etag"))
        if etag and stored != etag:
            return s3_error_response(status_code=400, code="InvalidPart", resource=resource)

    # AWS rule: every part except the last must be >= min size.
    for idx, (num, _) in enumerate(requested):
        size = int(by_num[num].get("size", 0))
        if idx < len(requested) - 1 and size < MULTIPART_MIN_PART_BYTES:
            return s3_error_response(
                status_code=400,
                code="EntityTooSmall",
                message=(
                    f"Part {num} size {size} is below minimum "
                    f"{MULTIPART_MIN_PART_BYTES} bytes"
                ),
                resource=resource,
            )

    sorted_nums = sorted(n for n, _ in requested)
    storage_id = upload.get("storage_id") or ""
    telegram_albums: list[TelegramAlbumMeta] | None = None
    telegram_grouped_id = None

    legacy_tg_parts = any(by_num[n].get("file_id") for n in sorted_nums) and not any(
        by_num[n].get("staging_path") for n in sorted_nums
    )

    if legacy_tg_parts:
        parts = [
            BlobPart(
                part_number=by_num[num]["part_number"],
                file_id=by_num[num]["file_id"],
                size=by_num[num].get("size", 0),
                message_id=by_num[num].get("message_id"),
                etag=by_num[num].get("etag", ""),
            )
            for num in sorted_nums
        ]
    else:
        built: list[BlobPart] = []
        albums_meta: list[TelegramAlbumMeta] = []
        chat_id = getattr(bucket, "telegram_chat_id", None)
        topic_id = getattr(bucket, "telegram_topic_id", None)
        album_index = 0
        # Complete is not fully idempotent: if TG fails after some albums were sent,
        # staging is kept so the client may Abort and restart; retrying Complete without
        # Abort may create duplicate TG messages. Partial TG messages are best-effort deleted.
        from app.ops.tg_delete import safe_delete_tg_message

        async def _rollback_sent_parts(parts_sent: list[BlobPart]) -> None:
            seen: set[int] = set()
            for part in parts_sent:
                mid = part.message_id
                if mid is None or mid in seen:
                    continue
                seen.add(mid)
                await safe_delete_tg_message(
                    db,
                    mid,
                    chat_id=chat_id,
                    reason="multipart_complete_rollback",
                )

        try:
            for offset in range(0, len(sorted_nums), TG_ALBUM_MAX_ITEMS):
                chunk_nums = sorted_nums[offset : offset + TG_ALBUM_MAX_ITEMS]
                chunk_docs = []
                for num in chunk_nums:
                    label = tg_document_label(storage_id, part_number=num)
                    chunk_docs.append(
                        (part_tg_upload_path(upload_id, num, label), label)
                    )
                results = await storage.send_media_group(
                    chunk_docs, chat_id=chat_id, topic_id=topic_id
                )
                if len(results) != len(chunk_docs):
                    raise StorageUnavailableError("incomplete media group response")
                gid = results[0].grouped_id
                if telegram_grouped_id is None and gid is not None:
                    telegram_grouped_id = gid
                albums_meta.append(
                    TelegramAlbumMeta(
                        grouped_id=int(gid or 0),
                        part_start=chunk_nums[0],
                        part_end=chunk_nums[-1],
                    )
                )
                for idx, res in enumerate(results):
                    pn = chunk_nums[idx]
                    built.append(
                        BlobPart(
                            part_number=pn,
                            file_id=res.file_id,
                            message_id=res.message_id,
                            size=int(by_num[pn].get("size", 0)),
                            etag=by_num[pn].get("etag", ""),
                            album_index=album_index,
                        )
                    )
                album_index += 1
        except StorageThrottleError:
            await _rollback_sent_parts(built)
            return s3_error_response(status_code=503, code="SlowDown", resource=resource)
        except StorageUnavailableError:
            await _rollback_sent_parts(built)
            return s3_error_response(
                status_code=503, code="ServiceUnavailable", resource=resource
            )
        except (OSError, ValueError):
            await _rollback_sent_parts(built)
            return s3_error_response(
                status_code=503,
                code="ServiceUnavailable",
                message="Failed to prepare staged multipart part",
                resource=resource,
            )
        parts = built
        telegram_albums = albums_meta
        remove_upload_staging(upload_id)

    total_size = sum(p.size for p in parts)

    # Best-effort cleanup of uploaded parts not included in Complete.
    kept = {num for num, _ in requested}
    all_parts = await crud_list_parts(db, upload_id)
    from app.ops.tg_delete import safe_delete_tg_message

    for part in all_parts:
        if part["part_number"] in kept:
            continue
        if part.get("message_id") is not None:
            await safe_delete_tg_message(
                db,
                part["message_id"],
                chat_id=getattr(bucket, "telegram_chat_id", None),
                reason="multipart_unused_part",
            )

    from app.s3.object_lifecycle import bypass_trash_requested

    await _cleanup_existing_blob(
        db,
        bucket,
        bucket_name,
        key,
        bypass_trash=bypass_trash_requested(request),
    )
    filters = BlobFilterParams(path=key, bucket_name=bucket_name)
    existing = await crud_get_all_blobs(db, filters)
    update = len(existing) > 0
    blob = BlobInCreate(
        path=key,
        storage_id=storage_id,
        telegram_grouped_id=telegram_grouped_id,
        telegram_albums=telegram_albums,
        file=f"multipart:{upload_id}",
        content_type=upload.get("content_type", "application/octet-stream"),
        size=total_size,
        parts=parts,
        message_id=None,
    )
    await crud_create_blob(db, blob, bucket_name, update)
    # Drop upload metadata only; keep TG messages referenced by completed parts.
    await crud_delete_multipart_upload(db, upload_id)
    cache_delete(bucket_name, key)

    etag = f'"{hashlib.md5(upload_id.encode()).hexdigest()}-{len(parts)}"'
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<CompleteMultipartUploadResult>"
        f"<Bucket>{escape(bucket_name)}</Bucket>"
        f"<Key>{escape(key)}</Key>"
        f"<ETag>{escape(etag)}</ETag>"
        "</CompleteMultipartUploadResult>"
    )
    return Response(content=body, media_type="application/xml")


async def abort_multipart_upload(
    request: Request,
    bucket_name: str,
    key: str,
    db: AsyncSession,
    upload_id: str,
):
    resource = f"/{bucket_name}/{key}"
    upload = await crud_get_multipart_upload(db, upload_id)
    if not upload or upload["bucket"] != bucket_name or upload["key"] != key:
        return s3_error_response(status_code=404, code="NoSuchUpload", resource=resource)

    bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not bucket:
        return s3_error_response(status_code=404, code="NoSuchBucket", resource=resource)
    auth = await authorize_request_for_bucket(bucket, request, db)
    if auth != AUTH_OK:
        return auth_error_response(auth, resource)
    if not await _upload_owner_ok(upload, bucket, request, db):
        return s3_error_response(status_code=403, code="AccessDenied", resource=resource)

    parts = await crud_list_parts(db, upload_id)
    from app.ops.tg_delete import safe_delete_tg_message

    for part in parts:
        if part.get("message_id") is not None:
            await safe_delete_tg_message(
                db,
                part["message_id"],
                chat_id=getattr(bucket, "telegram_chat_id", None),
                reason="multipart_abort",
            )
    remove_upload_staging(upload_id)
    await crud_delete_multipart_upload(db, upload_id)
    return Response(status_code=204)


async def list_parts(
    request: Request,
    bucket_name: str,
    key: str,
    db: AsyncSession,
    upload_id: str,
):
    resource = f"/{bucket_name}/{key}"
    upload = await crud_get_multipart_upload(db, upload_id)
    if not upload or upload["bucket"] != bucket_name or upload["key"] != key:
        return s3_error_response(status_code=404, code="NoSuchUpload", resource=resource)

    bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not bucket:
        return s3_error_response(status_code=404, code="NoSuchBucket", resource=resource)
    auth = await authorize_request_for_bucket(bucket, request, db)
    if auth != AUTH_OK:
        return auth_error_response(auth, resource)
    if not await _upload_owner_ok(upload, bucket, request, db):
        return s3_error_response(status_code=403, code="AccessDenied", resource=resource)

    parts = await crud_list_parts(db, upload_id)
    parts_xml = "".join(
        "<Part>"
        f"<PartNumber>{p['part_number']}</PartNumber>"
        f"<ETag>{escape(p.get('etag', ''))}</ETag>"
        f"<Size>{int(p.get('size', 0))}</Size>"
        "</Part>"
        for p in parts
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ListPartsResult>"
        f"<Bucket>{escape(bucket_name)}</Bucket>"
        f"<Key>{escape(key)}</Key>"
        f"<UploadId>{escape(upload_id)}</UploadId>"
        f"{parts_xml}"
        "</ListPartsResult>"
    )
    return Response(content=body, media_type="application/xml")
