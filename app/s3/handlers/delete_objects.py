import base64
import hashlib
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.responses import Response

from app.crud.bucket import crud_get_bucket_by_name
from app.db.mongodb import get_database
from app.s3.auth import (
    AUTH_OK,
    auth_error_response,
    authorize_request_for_bucket,
    precheck_request_for_bucket,
)
from app.s3.body import BodyTooLarge, read_body_capped
from app.s3.errors import s3_error_response
from app.s3.object_lifecycle import bypass_trash_requested, delete_live_object
from app.s3.subresources import reject_unsupported_subresource

router = APIRouter(tags=["S3"])

_MAX_DELETE_XML_BYTES = 256 * 1024
_MAX_DELETE_KEYS = 1000


def _parse_delete_xml(raw: bytes) -> tuple[list[str], bool]:
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("unsafe xml")
    root = ET.fromstring(raw.decode("utf-8"))
    quiet_text = root.findtext("Quiet") or "false"
    quiet = quiet_text.strip().lower() in {"true", "1"}
    keys: list[str] = []
    for obj in root.findall("Object"):
        key = obj.findtext("Key")
        if key is not None and key != "":
            keys.append(key)
    return keys, quiet


def _md5_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.md5(data).digest()).decode("ascii")


def _delete_result_xml(
    deleted: list[str], errors: list[tuple[str, str, str]], *, quiet: bool
) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<DeleteResult>"]
    if not quiet:
        for key in deleted:
            parts.append(f"<Deleted><Key>{escape(key)}</Key></Deleted>")
    for key, code, message in errors:
        parts.append(
            "<Error>"
            f"<Key>{escape(key)}</Key>"
            f"<Code>{escape(code)}</Code>"
            f"<Message>{escape(message)}</Message>"
            "</Error>"
        )
    parts.append("</DeleteResult>")
    return "".join(parts)


@router.post("/{bucket_name}")
async def delete_objects(
    request: Request,
    bucket_name: str,
    db: AsyncIOMotorClient = Depends(get_database),
):
    resource = f"/{bucket_name}"
    if "delete" not in request.query_params:
        return s3_error_response(
            status_code=501,
            code="NotImplemented",
            message="Only POST ?delete (DeleteObjects) is supported on bucket",
            resource=resource,
        )

    blocked = reject_unsupported_subresource(request, resource)
    if blocked:
        return blocked

    bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not bucket:
        return s3_error_response(
            status_code=404, code="NoSuchBucket", resource=resource
        )

    pre = await precheck_request_for_bucket(bucket, request, db)
    if pre != AUTH_OK:
        return auth_error_response(pre, resource)

    try:
        raw = await read_body_capped(request, _MAX_DELETE_XML_BYTES)
    except BodyTooLarge:
        return s3_error_response(
            status_code=400, code="InvalidRequest", resource=resource
        )

    auth = await authorize_request_for_bucket(bucket, request, db, body=raw)
    if auth != AUTH_OK:
        return auth_error_response(auth, resource)

    content_md5 = request.headers.get("content-md5")
    if not content_md5:
        return s3_error_response(
            status_code=400,
            code="InvalidRequest",
            message="Content-MD5 header is required for DeleteObjects",
            resource=resource,
        )
    if content_md5 != _md5_b64(raw):
        return s3_error_response(
            status_code=400,
            code="InvalidRequest",
            message="The Content-MD5 you specified did not match what we received",
            resource=resource,
        )

    try:
        keys, quiet = _parse_delete_xml(raw)
    except (ET.ParseError, ValueError, UnicodeDecodeError):
        return s3_error_response(
            status_code=400, code="InvalidRequest", resource=resource
        )

    if not keys or len(keys) > _MAX_DELETE_KEYS:
        return s3_error_response(
            status_code=400,
            code="InvalidRequest",
            message="DeleteObjects requires 1..1000 keys",
            resource=resource,
        )

    deleted: list[str] = []
    errors: list[tuple[str, str, str]] = []
    chat_id = getattr(bucket, "telegram_chat_id", None)
    bypass = bypass_trash_requested(request)

    for key in keys:
        try:
            await delete_live_object(
                db,
                bucket_name=bucket_name,
                key=key,
                chat_id=chat_id,
                reason="delete_objects",
                bypass_trash=bypass,
            )
            deleted.append(key)
        except Exception as exc:
            errors.append((key, "InternalError", str(exc) or "delete failed"))

    xml = _delete_result_xml(deleted, errors, quiet=quiet)
    return Response(content=xml, media_type="application/xml")
