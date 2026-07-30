# Ensure an event loop exists before libraries that call get_event_loop() at import.
import asyncio

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import io
import os

os.environ.setdefault("PROJECT_NAME", "telezon-test")
os.environ.setdefault("PORT", "8000")
# Always override: developer .env may set a short or placeholder SECRET_KEY.
os.environ["SECRET_KEY"] = "pytest-secret-key-min-16b"
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_USER", "root")
os.environ.setdefault("MYSQL_PASSWORD", "")
os.environ.setdefault("MYSQL_DATABASE", "telezon_test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.tables import Base, BlobRow
from app.storage.backend import PutFileResult


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
async def mock_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def find_blob_row(session: AsyncSession, bucket_name: str, path: str):
    result = await session.execute(
        select(BlobRow).where(
            BlobRow.bucket_name == bucket_name,
            BlobRow.path == path,
        )
    )
    return result.scalar_one_or_none()


@pytest.fixture
def fake_storage():
    return FakeStorage()


def override_get_database(session):
    """FastAPI dependency override matching get_database (async generator)."""

    async def _override():
        yield session

    return _override
