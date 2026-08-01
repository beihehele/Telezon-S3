# pylint: disable=redefined-outer-name,unused-argument
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from app.bot.mgmt import start_mgmt_bot_if_enabled, stop_mgmt_bot
from app.api import router as api_router
from app.api.v1.endpoints.shares import share_public_router
from app.core.config import CID, ENABLE_CONSOLE, PROJECT_NAME, logger
from app.core.errors import http_422_error_handler, http_error_handler
from app.db.session import close_database_connection, connect_to_database
from app.ops.gc import start_gc_if_enabled, stop_gc
from app.s3 import router as s3_router
from app.s3.middleware import AmzRequestIdMiddleware
from app.storage.telegram.account_client import account_client_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_database()
    cid_raw = (CID or "").strip()
    cid_ok = False
    if cid_raw:
        try:
            int(cid_raw)
            cid_ok = True
        except ValueError:
            pass
    if not cid_ok:
        logger.warning(
            "CID is missing or invalid in .env; default Telegram storage chat is not "
            "configured. Run setup (optional CID listener) or set CID before uploading."
        )
    try:
        await account_client_manager.start()
    except Exception:
        logger.exception("Failed to start Telegram account client")
        if account_client_manager.last_error:
            logger.warning(
                "S3 storage needs a working Pyrogram session (SESSION_STRING); "
                "/api/health will return 503 until fixed. Detail: %s",
                account_client_manager.last_error,
            )
    if account_client_manager.ready:
        logger.info("Telegram account client is ready (S3 storage)")
    else:
        logger.warning(
            "Telegram account client not ready; /api/health will return 503. "
            "Set HEALTH_EXPOSE_ERRORS=1 to see telegram.error in JSON. Detail: %s",
            account_client_manager.last_error or "unknown",
        )
    await start_mgmt_bot_if_enabled()
    await start_gc_if_enabled()
    yield
    await stop_gc()
    await stop_mgmt_bot()
    await account_client_manager.stop()
    await close_database_connection()


app = FastAPI(title=PROJECT_NAME, lifespan=lifespan)

app.add_middleware(AmzRequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(HTTPException, http_error_handler)
app.add_exception_handler(HTTP_422_UNPROCESSABLE_ENTITY, http_422_error_handler)

# Fixed-path routers before S3 catch-alls (/{bucket}/{key}).
app.include_router(api_router)
app.include_router(share_public_router)
app.include_router(s3_router)

if ENABLE_CONSOLE:
    _console_dir = Path(__file__).resolve().parent / "static" / "console"
    if _console_dir.is_dir():
        app.mount(
            "/console",
            StaticFiles(directory=str(_console_dir), html=True),
            name="console",
        )
    else:
        logger.warning(
            "ENABLE_CONSOLE=1 but %s is missing; build the SPA into app/static/console/",
            _console_dir,
        )
