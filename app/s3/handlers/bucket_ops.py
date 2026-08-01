from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from app.crud.bucket import (
    crud_bucket_has_objects,
    crud_create_bucket,
    crud_delete_bucket,
    crud_get_bucket_by_name,
)
from app.crud.multipart import crud_list_multipart_uploads
from app.db.session import get_database
from app.models.bucket import BucketInCreate
from app.models.user import User
from app.s3.auth import (
    AUTH_OK,
    auth_error_response,
    authorize_request_for_bucket,
    resolve_identity_from_request,
    resolve_user_from_request,
)
from app.s3.errors import s3_error_response
from app.s3.subresources import reject_unsupported_subresource

router = APIRouter(tags=["S3"])


@router.head("/{bucket_name}")
@router.head("/{bucket_name}/")
async def head_bucket(
    request: Request,
    bucket_name: str,
    db: AsyncSession = Depends(get_database),
):
    resource = f"/{bucket_name}"
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
    return Response(status_code=200, headers={"x-amz-bucket-region": "us-east-1"})


@router.put("/{bucket_name}")
async def create_bucket(
    request: Request,
    bucket_name: str,
    db: AsyncSession = Depends(get_database),
):
    resource = f"/{bucket_name}"
    blocked = reject_unsupported_subresource(request, resource)
    if blocked:
        return blocked

    identity = await resolve_identity_from_request(db, request, body=b"")
    if not identity or not identity.can_create_bucket():
        return s3_error_response(
            status_code=403, code="AccessDenied", resource=resource
        )
    user = await resolve_user_from_request(db, request, body=b"")
    if not user:
        return s3_error_response(
            status_code=403, code="AccessDenied", resource=resource
        )

    existing = await crud_get_bucket_by_name(db, bucket_name)
    if existing:
        return s3_error_response(
            status_code=409,
            code="BucketAlreadyOwnedByYou"
            if existing.owner.username == user.username
            else "BucketAlreadyExists",
            resource=resource,
        )

    await crud_create_bucket(
        db,
        BucketInCreate(name=bucket_name, owner_username=user.username),
        User(**user.model_dump()),
    )
    return Response(status_code=200, headers={"Location": f"/{bucket_name}"})


@router.delete("/{bucket_name}")
async def delete_bucket(
    request: Request,
    bucket_name: str,
    db: AsyncSession = Depends(get_database),
):
    resource = f"/{bucket_name}"
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

    if await crud_bucket_has_objects(db, bucket_name):
        return s3_error_response(
            status_code=409,
            code="BucketNotEmpty",
            message="The bucket you tried to delete is not empty",
            resource=resource,
        )

    uploads = await crud_list_multipart_uploads(
        db, bucket=bucket_name, max_uploads=1
    )
    if uploads:
        return s3_error_response(
            status_code=409,
            code="BucketNotEmpty",
            message="The bucket has incomplete multipart uploads",
            resource=resource,
        )

    await crud_delete_bucket(db, bucket_name)

    # Permanently purge soft-deleted objects for this bucket.
    from app.crud.trash import crud_delete_trash_for_bucket
    from app.s3.object_lifecycle import purge_trash_item

    chat_id = getattr(bucket, "telegram_chat_id", None)
    for item in await crud_delete_trash_for_bucket(db, bucket_name):
        await purge_trash_item(db, item, chat_id=chat_id)

    return Response(status_code=204)
