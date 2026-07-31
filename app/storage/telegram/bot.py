from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import TELEGRAM_API_BASE, TELEGRAM_PROXY, TOKEN, logger

if TYPE_CHECKING:
    from telegram import Bot
    from telegram.ext import Application

_updater: Application | None = None
_bot: Bot | None = None


def _token_for_bot() -> str | None:
    if TOKEN is None:
        return None
    stripped = str(TOKEN).strip()
    return stripped or None


def build_application() -> Application:
    """Build PTB Application (legacy bot storage / setup scripts). Requires BOT_TOKEN."""
    from telegram.ext import Application

    token = _token_for_bot()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is missing. Set it in .env for legacy bot storage or "
            "setup_bot_storage.py. Account-mode deploys (SESSION_STRING) do not need BOT_TOKEN."
        )

    builder = Application.builder().token(token)
    if TELEGRAM_API_BASE:
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

    return builder.build()


def get_updater() -> Application:
    global _updater, _bot
    if _updater is None:
        _updater = build_application()
        _bot = _updater.bot
    return _updater


def get_bot() -> Bot:
    get_updater()
    assert _bot is not None
    return _bot


# Legacy module attributes (lazy; do not build at import).


def __getattr__(name: str):
    if name == "updater":
        return get_updater()
    if name == "bot":
        return get_bot()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
