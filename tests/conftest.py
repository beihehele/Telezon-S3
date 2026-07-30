# Ensure an event loop exists before libraries that call get_event_loop() at import.
import asyncio

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import io
import os

# Config is imported eagerly; set defaults before app modules load.
os.environ.setdefault("PROJECT_NAME", "telezon-test")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("MONGO_HOST", "localhost")
os.environ.setdefault("MONGO_PORT", "27017")
os.environ.setdefault("MONGO_USER", "")
os.environ.setdefault("MONGO_PASSWORD", "")
os.environ.setdefault("DATABASE_NAME", "telezon_test")
os.environ.setdefault("DATABASE_URL", "mongodb://localhost:27017")
os.environ.setdefault("BOT_TOKEN", "0:test")
os.environ.setdefault("CID", "123")
os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("SESSION_STRING", "session")
os.environ.setdefault("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))
os.environ.setdefault("MULTIPART_MIN_PART_BYTES", "1")
os.environ.setdefault("ENABLE_GC", "0")
os.environ.setdefault("TG_RATE_LIMIT_PER_SEC", "20")
os.environ.setdefault("TG_RATE_BURST", "20")
os.environ.setdefault("TG_RATE_WAIT_SECONDS", "30")

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.storage.storage import PutFileResult


class FakeStorage:
    def __init__(self):
        self.files = {}
        self.deleted_messages = []
        self._msg = 100
        self.last_put_kwargs = {}

    async def put_file(self, file: bytes, filename: str, **kwargs) -> PutFileResult:
        self.last_put_kwargs = kwargs
        self._msg += 1
        file_id = f"file-{self._msg}"
        self.files[file_id] = file
        return PutFileResult(file_id=file_id, message_id=self._msg)

    async def get_file(self, file_id: str):
        return io.BytesIO(self.files[file_id])

    async def delete_message(self, message_id: int, **kwargs) -> bool:
        self.deleted_messages.append(message_id)
        return True


@pytest.fixture
def mock_db():
    return AsyncMongoMockClient()


@pytest.fixture
def fake_storage():
    return FakeStorage()
