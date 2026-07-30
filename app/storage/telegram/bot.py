from telegram.ext import Application

from app.core.config import TELEGRAM_API_BASE, TELEGRAM_PROXY, TOKEN, logger

builder = Application.builder().token(TOKEN)
if TELEGRAM_API_BASE:
    # Local Bot API server (aiogram/telegram-bot-api)
    base = TELEGRAM_API_BASE.rstrip("/")
    builder = builder.base_url(f"{base}/bot").base_file_url(f"{base}/file/bot")

if TELEGRAM_PROXY is not None:
    builder = builder.proxy(TELEGRAM_PROXY.url).get_updates_proxy(TELEGRAM_PROXY.url)
    logger.info(
        "Telegram bot API using proxy %s://%s:%s",
        TELEGRAM_PROXY.scheme,
        TELEGRAM_PROXY.hostname,
        TELEGRAM_PROXY.port,
    )

updater = builder.build()
bot = updater.bot
