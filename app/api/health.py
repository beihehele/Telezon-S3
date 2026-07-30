from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from app.core.config import HEALTH_EXPOSE_ERRORS
from app.db.mongodb import db
from app.storage.telegram.account_client import account_client_manager

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    mongo_ok = False
    mongo_error: str | None = None
    if db.client is not None:
        try:
            await db.client.admin.command("ping")
            mongo_ok = True
        except Exception as exc:
            mongo_error = str(exc)

    tg_ok = account_client_manager.ready
    tg_error = account_client_manager.last_error

    body = {
        "status": "ok" if mongo_ok and tg_ok else "degraded",
        "mongodb": {"ok": mongo_ok},
        "telegram": {"ok": tg_ok},
    }
    if HEALTH_EXPOSE_ERRORS:
        body["mongodb"]["error"] = mongo_error
        body["telegram"]["error"] = tg_error
    code = HTTP_200_OK if mongo_ok and tg_ok else HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=body, status_code=code)
