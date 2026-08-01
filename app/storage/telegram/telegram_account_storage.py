import io
import logging

from app.core.config import CID, TG_RATE_WAIT_SECONDS
from app.storage.errors import StorageThrottleError, StorageUnavailableError
from app.storage.backend import PutFileResult, Storage
from app.storage.telegram.account_client import account_client_manager
from app.storage.telegram.topic import pyrogram_document_topic_kwargs
from app.storage.telegram_limiter import telegram_rate_limiter

logger = logging.getLogger(__name__)


class TelegramAccountStorage(Storage):
    async def _acquire(self) -> None:
        ok = await telegram_rate_limiter.acquire(TG_RATE_WAIT_SECONDS)
        if not ok:
            raise StorageThrottleError("Telegram rate limit exceeded")

    def _require_client(self):
        client = account_client_manager.client
        if client is None or not account_client_manager.ready:
            raise StorageUnavailableError(
                account_client_manager.last_error
                or "Telegram account client is not available"
            )
        return client

    def _resolve_chat_id(self, chat_id: str | None) -> int:
        value = chat_id if chat_id not in (None, "") else CID
        return int(value)

    async def put_file(
        self,
        file: bytes,
        filename: str,
        *,
        chat_id: str | None = None,
        topic_id: int | None = None,
    ) -> PutFileResult:
        await self._acquire()
        document = io.BytesIO(file)
        client = self._require_client()
        kwargs = {"file_name": filename, **pyrogram_document_topic_kwargs(topic_id)}
        response = await client.send_document(
            self._resolve_chat_id(chat_id), document, **kwargs
        )
        return PutFileResult(
            file_id=str(response.document.file_id),
            message_id=response.id,
        )

    async def get_file(self, file_id: str) -> io.BufferedReader:
        await self._acquire()
        client = self._require_client()
        file = await client.download_media(file_id, in_memory=True)
        file.seek(0)
        return file

    async def delete_message(
        self,
        message_id: int,
        *,
        chat_id: str | None = None,
    ) -> bool:
        try:
            await self._acquire()
            client = self._require_client()
            await client.delete_messages(self._resolve_chat_id(chat_id), message_id)
            return True
        except StorageThrottleError:
            logger.warning(
                "Rate limited while deleting Telegram message %s", message_id
            )
            return False
        except StorageUnavailableError:
            logger.warning(
                "Telegram unavailable while deleting message %s", message_id
            )
            return False
        except Exception:
            logger.exception("Failed to delete Telegram message %s", message_id)
            return False
