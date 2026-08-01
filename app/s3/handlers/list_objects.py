from sqlalchemy.ext.asyncio import AsyncSession
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from app.crud.blob import crud_list_blobs_for_s3
from app.crud.bucket import crud_get_bucket_by_name
from app.crud.multipart import crud_list_multipart_uploads
from app.db.session import get_database
from app.s3.auth import (
    AUTH_OK,
    auth_error_response,
    authorize_request_for_bucket,
)
from app.s3.errors import s3_error_response
from app.s3.subresources import reject_unsupported_subresource
from app.s3.xml import build_list_objects_v2_xml, rollup_with_delimiter

router = APIRouter(tags=["S3"])


def _fmt_iso(value) -> str:
    if value is None:
        return ""
    try:
        return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        return str(value)


async def _list_multipart_uploads(request, bucket_name, db, resource):
    blocked = reject_unsupported_subresource(request, resource)
    if blocked:
        return blocked
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not bucket:
        return s3_error_response(
            status_code=404, code="NoSuchBucket", resource=resource
        )
    auth = await authorize_request_for_bucket(bucket, request, db)
    if auth != AUTH_OK:
        return auth_error_response(auth, resource)

    prefix = request.query_params.get("prefix", "")
    key_marker = request.query_params.get("key-marker", "")
    upload_id_marker = request.query_params.get("upload-id-marker", "")
    try:
        max_uploads = int(request.query_params.get("max-uploads", "1000"))
    except ValueError:
        max_uploads = 1000
    max_uploads = max(1, min(max_uploads, 1000))

    rows = await crud_list_multipart_uploads(
        db,
        bucket=bucket_name,
        prefix=prefix,
        key_marker=key_marker,
        upload_id_marker=upload_id_marker,
        max_uploads=max_uploads,
    )
    truncated = len(rows) > max_uploads
    page = rows[:max_uploads]
    uploads_xml = "".join(
        "<Upload>"
        f"<Key>{escape(u.get('key', ''))}</Key>"
        f"<UploadId>{escape(u.get('upload_id', ''))}</UploadId>"
        f"<Initiated>{escape(_fmt_iso(u.get('initiated_at')))}</Initiated>"
        "</Upload>"
        for u in page
    )
    next_key = page[-1].get("key", "") if truncated and page else ""
    next_upload = page[-1].get("upload_id", "") if truncated and page else ""
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ListMultipartUploadsResult>"
        f"<Bucket>{escape(bucket_name)}</Bucket>"
        f"<Prefix>{escape(prefix)}</Prefix>"
        f"<KeyMarker>{escape(key_marker)}</KeyMarker>"
        f"<UploadIdMarker>{escape(upload_id_marker)}</UploadIdMarker>"
        f"<NextKeyMarker>{escape(next_key)}</NextKeyMarker>"
        f"<NextUploadIdMarker>{escape(next_upload)}</NextUploadIdMarker>"
        f"<MaxUploads>{max_uploads}</MaxUploads>"
        f"<IsTruncated>{str(truncated).lower()}</IsTruncated>"
        f"{uploads_xml}"
        "</ListMultipartUploadsResult>"
    )
    return Response(content=body, media_type="application/xml")


@router.get("/{bucket_name}")
async def list_objects(
    request: Request,
    bucket_name: str,
    db: AsyncSession = Depends(get_database),
):
    resource = f"/{bucket_name}"

    if "uploads" in request.query_params:
        return await _list_multipart_uploads(request, bucket_name, db, resource)

    if "location" in request.query_params:
        bucket = await crud_get_bucket_by_name(db, bucket_name)
        if not bucket:
            return s3_error_response(
                status_code=404, code="NoSuchBucket", resource=resource
            )
        auth = await authorize_request_for_bucket(bucket, request, db)
        if auth != AUTH_OK:
            return auth_error_response(auth, resource)
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<LocationConstraint xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            "us-east-1"
            "</LocationConstraint>"
        )
        return Response(content=body, media_type="application/xml")

    if "versioning" in request.query_params:
        bucket = await crud_get_bucket_by_name(db, bucket_name)
        if not bucket:
            return s3_error_response(
                status_code=404, code="NoSuchBucket", resource=resource
            )
        auth = await authorize_request_for_bucket(bucket, request, db)
        if auth != AUTH_OK:
            return auth_error_response(auth, resource)
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<VersioningConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/"/>'
        )
        return Response(content=body, media_type="application/xml")

    if "object-lock" in request.query_params:
        bucket = await crud_get_bucket_by_name(db, bucket_name)
        if not bucket:
            return s3_error_response(
                status_code=404, code="NoSuchBucket", resource=resource
            )
        auth = await authorize_request_for_bucket(bucket, request, db)
        if auth != AUTH_OK:
            return auth_error_response(auth, resource)
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ObjectLockConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01"/>'
        )
        return Response(content=body, media_type="application/xml")

    blocked = reject_unsupported_subresource(request, resource)
    if blocked:
        return blocked
    list_type = request.query_params.get("list-type")
    if list_type is None:
        # S3 Browser and some clients omit list-type; Telezon only implements V2.
        list_type = "2"
    if list_type != "2":
        return s3_error_response(
            status_code=501,
            code="NotImplemented",
            message="Only ListObjectsV2 (list-type=2) is supported",
            resource=resource,
        )

    bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not bucket:
        return s3_error_response(
            status_code=404,
            code="NoSuchBucket",
            message="The specified bucket does not exist",
            resource=resource,
        )

    auth = await authorize_request_for_bucket(bucket, request, db)
    if auth != AUTH_OK:
        return auth_error_response(auth, resource)

    prefix = request.query_params.get("prefix", "")
    delimiter = request.query_params.get("delimiter") or ""
    continuation_token = request.query_params.get("continuation-token")
    start_after = request.query_params.get("start-after", "")
    try:
        max_keys = int(request.query_params.get("max-keys", "1000"))
    except ValueError:
        max_keys = 1000
    max_keys = max(1, min(max_keys, 1000))

    effective_start = continuation_token or start_after or ""

    if delimiter:
        # Oversample raw keys so CommonPrefixes can fill MaxKeys.
        fetch_limit = min(5000, max(max_keys * 20, max_keys + 1))
        rows = await crud_list_blobs_for_s3(
            db,
            bucket_name,
            prefix=prefix,
            start_after=effective_start,
            max_keys=fetch_limit,
        )
        page, common_prefixes, rolled_truncated, last_key = rollup_with_delimiter(
            rows, prefix=prefix, delimiter=delimiter, max_keys=max_keys
        )
        # Truncated if rollup filled max_keys and more raw keys remain.
        is_truncated = rolled_truncated or (
            len(rows) >= fetch_limit and last_key is not None
        )
        next_token = last_key if is_truncated else None
        xml = build_list_objects_v2_xml(
            bucket_name=bucket_name,
            prefix=prefix,
            max_keys=max_keys,
            blobs=page,
            is_truncated=is_truncated,
            next_continuation_token=next_token,
            continuation_token=continuation_token,
            start_after=start_after or None,
            delimiter=delimiter,
            common_prefixes=common_prefixes,
        )
        return Response(content=xml, media_type="application/xml")

    rows = await crud_list_blobs_for_s3(
        db,
        bucket_name,
        prefix=prefix,
        start_after=effective_start,
        max_keys=max_keys + 1,
    )
    is_truncated = len(rows) > max_keys
    page = rows[:max_keys]
    next_token = page[-1].path if is_truncated and page else None

    xml = build_list_objects_v2_xml(
        bucket_name=bucket_name,
        prefix=prefix,
        max_keys=max_keys,
        blobs=page,
        is_truncated=is_truncated,
        next_continuation_token=next_token,
        continuation_token=continuation_token,
        start_after=start_after or None,
    )
    return Response(content=xml, media_type="application/xml")
