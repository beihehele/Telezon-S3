from fastapi import APIRouter
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.buckets import router as buckets_router
from app.api.v1.endpoints.presign import router as presign_router
from app.api.v1.endpoints.shares import router as shares_router
from app.api.v1.endpoints.upload import router as upload_router
from app.api.v1.endpoints.credentials import router as credentials_router
from app.api.v1.endpoints.trash import router as trash_router
from app.api.v1.endpoints.objects import router as objects_router

router = APIRouter(prefix="/v1")

router.include_router(users_router)
router.include_router(buckets_router)
router.include_router(objects_router)
router.include_router(presign_router)
router.include_router(shares_router)
router.include_router(upload_router)
router.include_router(credentials_router)
router.include_router(trash_router)
