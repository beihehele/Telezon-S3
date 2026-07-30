from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.responses import Response

from app.crud.bucket import crud_get_all_buckets
from app.db.mongodb import get_database
from app.models.bucket import BucketFilterParams
from app.s3.auth import resolve_identity_from_request, resolve_user_from_request
from app.s3.errors import s3_error_response
from app.s3.xml import build_list_buckets_xml

router = APIRouter(tags=["S3"])


@router.api_route("/", methods=["GET"], include_in_schema=True)
async def list_buckets(
    request: Request,
    db: AsyncIOMotorClient = Depends(get_database),
):
    identity = await resolve_identity_from_request(db, request)
    user = await resolve_user_from_request(db, request)
    if not identity or not user:
        return s3_error_response(
            status_code=403,
            code="AccessDenied",
            message="Access Denied",
            resource="/",
        )

    buckets = await crud_get_all_buckets(
        db,
        BucketFilterParams(owner_username=user.username, limit=1000, offset=0),
    )
    if identity.buckets is not None:
        allowed = set(identity.buckets)
        buckets = [b for b in buckets if b.name in allowed]

    xml = build_list_buckets_xml(
        buckets,
        owner_id=identity.access_key_id,
        owner_display=user.username,
    )
    return Response(content=xml, media_type="application/xml")
