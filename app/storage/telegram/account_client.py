import logging
from typing import Any

from app.core.config import (
    SESSION_STRING,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_PROXY,
)

logger = logging.getLogger(__name__)


class TelegramAccountClientManager:
    def __init__(self):
        self._client: Any | None = None
        self.ready: bool = False
        self.last_error: str | None = None

    @property
    def client(self):
        return self._client

    async def start(self) -> None:
        if self._client is not None:
            self.ready = True
            return

        from pyrogram import Client

        kwargs = {
            "name": "telegram",
            "api_id": TELEGRAM_API_ID,
            "api_hash": TELEGRAM_API_HASH,
            "session_string": SESSION_STRING,
            "in_memory": True,
        }
        if TELEGRAM_PROXY is not None:
            kwargs["proxy"] = TELEGRAM_PROXY.as_pyrogram_dict()
            logger.info(
                "Telegram account client using proxy %s://%s:%s",
                TELEGRAM_PROXY.scheme,
                TELEGRAM_PROXY.hostname,
                TELEGRAM_PROXY.port,
            )

        client = Client(**kwargs)
        try:
            await client.start()
            async for _ in client.get_dialogs():
                pass
        except Exception as exc:
            self.ready = False
            self.last_error = str(exc)
            try:
                if getattr(client, "is_connected", False):
                    await client.stop()
            except Exception:
                logger.exception("Cleanup after failed Telegram client start")
            raise

        self._client = client
        self.ready = True
        self.last_error = None
        logger.info("Telegram account client started")

    async def stop(self) -> None:
        self.ready = False
        if self._client is None:
            return
        try:
            await self._client.stop()
        except Exception:
            logger.exception("Error stopping Telegram account client")
        finally:
            self._client = None
            logger.info("Telegram account client stopped")


account_client_manager = TelegramAccountClientManager()
