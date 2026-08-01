from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

from app.api.auth.utils import is_admin
from app.core.token import get_current_user
from app.crud.blob import crud_rename_blob
from app.crud.bucket import crud_get_bucket_by_name
from app.db.session import get_database
from app.models.user import User
from app.s3.xml import object_etag
from app.storage.disk_cache import cache_delete

router = APIRouter(prefix="/buckets", tags=["Objects"])


class RenameBody(BaseModel):
    from_key: str = Field(alias="from", min_length=1)
    to_key: str = Field(alias="to", min_length=1)

    model_config = {"populate_by_name": True}


@router.post("/{bucket_name}/objects/rename")
async def rename_object(
    bucket_name: str,
    body: RenameBody,
    db: AsyncSession = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    bucket = await crud_get_bucket_by_name(db, bucket_name)
    if not bucket:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Bucket not found")
    if not is_admin(current_user) and bucket.owner.username != current_user.username:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Not bucket owner")

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
