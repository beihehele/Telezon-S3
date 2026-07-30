from abc import ABC, abstractmethod

from pydantic import BaseModel


class PutFileResult(BaseModel):
    file_id: str
    message_id: int | None = None


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
