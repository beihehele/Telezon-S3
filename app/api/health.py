from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from app.core.config import HEALTH_EXPOSE_ERRORS
from app.db import session as db_session
from app.storage.telegram.account_client import account_client_manager

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    db_ok = False
    db_error: str | None = None
    if db_session.async_session_factory is not None:
        try:
            await db_session.ping_database()
            db_ok = True
        except Exception as exc:
            db_error = str(exc)

    tg_ok = account_client_manager.ready
    tg_error = account_client_manager.last_error

    body = {
        "status": "ok" if db_ok and tg_ok else "degraded",
        "database": {"ok": db_ok},
        "telegram": {"ok": tg_ok},
    }
    if HEALTH_EXPOSE_ERRORS:
        body["database"]["error"] = db_error
        body["telegram"]["error"] = tg_error
    code = HTTP_200_OK if db_ok and tg_ok else HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=body, status_code=code)
