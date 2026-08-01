from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

from pydantic import BaseModel

from app.storage.errors import StorageUnavailableError

MediaGroupSource = Union[bytes, str, Path]
PutFileSource = MediaGroupSource


def media_group_source_bytes(source: MediaGroupSource) -> bytes:
    if isinstance(source, bytes):
        return source
    return Path(source).read_bytes()


class PutFileResult(BaseModel):
    file_id: str
    message_id: int | None = None
    grouped_id: int | None = None


class Storage(ABC):
    @abstractmethod
    async def put_file(
        self,
        file: PutFileSource,
        filename: str,
        *,
        chat_id: str | None = None,
        topic_id: int | None = None,
    ) -> PutFileResult:
        raise NotImplementedError

    @abstractmethod
    async def get_file(
        self,
        file_id: str,
        *,
        chat_id: str | None = None,
        message_id: int | None = None,
    ):
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
        documents: list[tuple[MediaGroupSource, str]],
        *,
        chat_id: str | None = None,
        topic_id: int | None = None,
    ) -> list[PutFileResult]:
        results: list[PutFileResult] = []
        for source, name in documents:
            results.append(
                await self.put_file(
                    media_group_source_bytes(source),
                    name,
                    chat_id=chat_id,
                    topic_id=topic_id,
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
