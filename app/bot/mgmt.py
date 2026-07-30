"""Optional lightweight management bot commands."""

from app.core.config import (
    DATABASE_NAME,
    ENABLE_MGMT_BOT,
    TELEGRAM_ADMIN_IDS,
    TELEGRAM_PROXY,
    TOKEN,
    logger,
)
from app.db.mongodb import db


_app = None


def _is_admin(update) -> bool:
    if not TELEGRAM_ADMIN_IDS:
        return False
    user = update.effective_user
    if user is None:
        return False
    return int(user.id) in TELEGRAM_ADMIN_IDS


async def start_mgmt_bot_if_enabled() -> None:
    global _app
    if not ENABLE_MGMT_BOT or not TOKEN:
        return
    if not TELEGRAM_ADMIN_IDS:
        logger.warning(
            "ENABLE_MGMT_BOT=1 but TELEGRAM_ADMIN_IDS is empty; bot will reject all users"
        )
    try:
        from telegram.ext import Application, CommandHandler

        builder = Application.builder().token(TOKEN)
        if TELEGRAM_PROXY is not None:
            builder = builder.proxy(TELEGRAM_PROXY.url).get_updates_proxy(
                TELEGRAM_PROXY.url
            )
            logger.info(
                "Management bot using proxy %s://%s:%s",
                TELEGRAM_PROXY.scheme,
                TELEGRAM_PROXY.hostname,
                TELEGRAM_PROXY.port,
            )
        _app = builder.build()

        async def start(update, context):
            if not _is_admin(update):
                await update.message.reply_text("Unauthorized")
                return
            await update.message.reply_text(
                "Telezon-S3 management bot\nCommands: /start /help /stats /buckets"
            )

        async def help_cmd(update, context):
            if not _is_admin(update):
                await update.message.reply_text("Unauthorized")
                return
            await update.message.reply_text(
                "/start - hello\n/help - this help\n"
                "/stats - object counts\n/buckets - list bucket names\n"
                "Use the S3 API and /api for full management."
            )

        async def stats(update, context):
            if not _is_admin(update):
                await update.message.reply_text("Unauthorized")
                return
            if db.client is None:
                await update.message.reply_text("Database not ready")
                return
            users = await db.client[DATABASE_NAME]["users"].count_documents({})
            buckets = await db.client[DATABASE_NAME]["buckets"].count_documents({})
            blobs = await db.client[DATABASE_NAME]["blobs"].count_documents({})
            await update.message.reply_text(
                f"users={users}\nbuckets={buckets}\nobjects={blobs}"
            )

        async def buckets_cmd(update, context):
            if not _is_admin(update):
                await update.message.reply_text("Unauthorized")
                return
            if db.client is None:
                await update.message.reply_text("Database not ready")
                return
            names = []
            cursor = db.client[DATABASE_NAME]["buckets"].find({}, {"name": 1}).limit(50)
            async for row in cursor:
                names.append(row.get("name", "?"))
            await update.message.reply_text(
                "buckets:\n" + ("\n".join(names) if names else "(none)")
            )

        _app.add_handler(CommandHandler("start", start))
        _app.add_handler(CommandHandler("help", help_cmd))
        _app.add_handler(CommandHandler("stats", stats))
        _app.add_handler(CommandHandler("buckets", buckets_cmd))
        await _app.initialize()
        await _app.start()
        if _app.updater is not None:
            await _app.updater.start_polling(drop_pending_updates=True)
        logger.info("Management bot started with polling")
    except Exception:
        logger.exception("Failed to start management bot")


async def stop_mgmt_bot() -> None:
    global _app
    if _app is None:
        return
    try:
        if _app.updater is not None:
            await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()
    except Exception:
        logger.exception("Failed to stop management bot")
    finally:
        _app = None
