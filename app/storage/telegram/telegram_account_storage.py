import io
import logging

from app.core.config import CID, TG_RATE_WAIT_SECONDS
from app.storage.errors import StorageObjectGoneError, StorageThrottleError, StorageUnavailableError
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

    async def send_media_group(
        self,
        documents: list[tuple[bytes, str]],
        *,
        chat_id: str | None = None,
        topic_id: int | None = None,
    ) -> list[PutFileResult]:
        if not documents:
            return []
        await self._acquire()
        from pyrogram.types import InputMediaDocument

        client = self._require_client()
        media = []
        for data, name in documents:
            document = io.BytesIO(data)
            document.name = name
            media.append(InputMediaDocument(document, file_name=name))
        kwargs = pyrogram_document_topic_kwargs(topic_id)
        messages = await client.send_media_group(
            self._resolve_chat_id(chat_id), media, **kwargs
        )
        grouped_id = getattr(messages[0], "media_group_id", None) if messages else None
        results: list[PutFileResult] = []
        for message in messages:
            doc = message.document
            if doc is None:
                continue
            results.append(
                PutFileResult(
                    file_id=str(doc.file_id),
                    message_id=message.id,
                    grouped_id=grouped_id,
                )
            )
        return results

    async def forward_messages(
        self,
        from_chat_id: str,
        message_ids: int | list[int],
        *,
        chat_id: str | None = None,
        topic_id: int | None = None,
    ) -> list[PutFileResult]:
        await self._acquire()
        client = self._require_client()
        from_peer = self._resolve_chat_id(from_chat_id)
        to_peer = self._resolve_chat_id(chat_id)
        anchor = message_ids if isinstance(message_ids, int) else message_ids[0]
        raw = await client.forward_messages(to_peer, from_peer, anchor)
        messages = raw if isinstance(raw, list) else [raw]
        grouped_id = getattr(messages[0], "media_group_id", None) if messages else None
        results: list[PutFileResult] = []
        for message in messages:
            doc = message.document
            if doc is None:
                continue
            results.append(
                PutFileResult(
                    file_id=str(doc.file_id),
                    message_id=message.id,
                    grouped_id=grouped_id,
                )
            )
        if not results:
            raise StorageUnavailableError("forward produced no documents")
        return results

    async def get_file(
        self,
        file_id: str,
        *,
        chat_id: str | None = None,
        message_id: int | None = None,
    ) -> io.BufferedReader:
        await self._acquire()
        client = self._require_client()
        from pyrogram.errors import FileReferenceExpired

        async def _download_from_message() -> io.BytesIO | None:
            if message_id is None or chat_id in (None, ""):
                return None
            message = await client.get_messages(
                self._resolve_chat_id(chat_id), message_id
            )
            if message is None or message.document is None:
                return None
            data = await client.download_media(message, in_memory=True)
            if data is None:
                return None
            if hasattr(data, "seek"):
                data.seek(0)
            return data

        if message_id is not None and chat_id not in (None, ""):
            from_message = await _download_from_message()
            if from_message is not None:
                return from_message

        try:
            file = await client.download_media(file_id, in_memory=True)
        except FileReferenceExpired:
            from_message = await _download_from_message()
            if from_message is not None:
                return from_message
            raise StorageUnavailableError(
                "Telegram file reference expired; could not refresh from message"
            ) from None
        if file is None:
            raise StorageObjectGoneError(f"Telegram media missing for file_id={file_id!r}")
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
