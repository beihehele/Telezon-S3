import logging

from app.core.config import CID, TG_RATE_WAIT_SECONDS
from app.storage.errors import StorageThrottleError
from app.storage.storage import PutFileResult, Storage
from app.storage.telegram.bot import bot
from app.storage.telegram_limiter import telegram_rate_limiter

logger = logging.getLogger(__name__)


class TelegramBotStorage(Storage):
    async def _acquire(self) -> None:
        ok = await telegram_rate_limiter.acquire(TG_RATE_WAIT_SECONDS)
        if not ok:
            raise StorageThrottleError("Telegram rate limit exceeded")

    def _resolve_chat_id(self, chat_id: str | None):
        return chat_id if chat_id not in (None, "") else CID

    async def put_file(
        self,
        file: bytes,
        filename: str,
        *,
        chat_id: str | None = None,
        topic_id: int | None = None,
    ) -> PutFileResult:
        await self._acquire()
        kwargs = {"filename": filename}
        if topic_id is not None:
            kwargs["message_thread_id"] = topic_id
        result = await bot.send_document(
            self._resolve_chat_id(chat_id), file, **kwargs
        )
        return PutFileResult(
            file_id=str(result.document.file_id),
            message_id=result.message_id,
        )

    async def get_file(self, file_id: str):
        await self._acquire()
        return await bot.get_file(file_id)

    async def delete_message(
        self,
        message_id: int,
        *,
        chat_id: str | None = None,
    ) -> bool:
        try:
            await self._acquire()
            await bot.delete_message(
                chat_id=self._resolve_chat_id(chat_id), message_id=message_id
            )
            return True
        except StorageThrottleError:
            logger.warning(
                "Rate limited while deleting Telegram message %s", message_id
            )
            return False
        except Exception:
            logger.exception("Failed to delete Telegram message %s", message_id)
            return False
