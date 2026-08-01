from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.storage.errors import StorageUnavailableError


class PutFileResult(BaseModel):
    file_id: str
    message_id: int | None = None
    grouped_id: int | None = None


class Storage(ABC):
    @abstractmethod
    async def put_file(
        self,
        file: bytes,
        filename: str,
        *,
        chat_id: str | None = None,
        topic_id: int | None = None,
    ) -> PutFileResult:
        raise NotImplementedError

    @abstractmethod
    async def get_file(self, file_id: str):
        raise NotImplementedError

    @abstractmethod
    async def delete_message(
        self,
        message_id: int,
        *,
        chat_id: str | None = None,
    ) -> bool:
        raise NotImplementedError

    async def send_media_group(
        self,
        documents: list[tuple[bytes, str]],
        *,
        chat_id: str | None = None,
        topic_id: int | None = None,
    ) -> list[PutFileResult]:
        results: list[PutFileResult] = []
        for data, name in documents:
            results.append(
                await self.put_file(
                    data, name, chat_id=chat_id, topic_id=topic_id
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
        raise StorageUnavailableError("forward_messages not implemented")
