from fastapi import APIRouter

from app.s3.handlers.bucket_ops import router as bucket_ops_router
from app.s3.handlers.delete_objects import router as delete_objects_router
from app.s3.handlers.list_buckets import router as list_buckets_router
from app.s3.handlers.list_objects import router as list_objects_router
from app.s3.handlers.object import router as object_router

router = APIRouter(tags=["S3"])
# ListBuckets on "/" must be registered before parameterized routes.
router.include_router(list_buckets_router)
router.include_router(bucket_ops_router)
router.include_router(delete_objects_router)
router.include_router(list_objects_router)
router.include_router(object_router)
