import io
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.storage.telegram import telegram_account_storage as tas_mod
from app.storage.telegram.telegram_account_storage import TelegramAccountStorage


class _FakeMgr:
    ready = True
    client = None
    last_error = None


@pytest.mark.asyncio
async def test_get_file_prefers_message_context(monkeypatch):
    client = AsyncMock()
    message = MagicMock()
    message.document = MagicMock()
    message.id = 42
    client.get_messages = AsyncMock(return_value=message)
    client.download_media = AsyncMock(return_value=io.BytesIO(b"payload"))

    mgr = _FakeMgr()
    mgr.client = client
    monkeypatch.setattr(tas_mod, "account_client_manager", mgr)
    monkeypatch.setattr(
        tas_mod.telegram_rate_limiter, "acquire", AsyncMock(return_value=True)
    )

    storage = TelegramAccountStorage()
    data = await storage.get_file("stale-id", chat_id="-1001", message_id=42)
    assert data.read() == b"payload"
    client.get_messages.assert_awaited_once()
    client.download_media.assert_awaited_once_with(message, in_memory=True)


@pytest.mark.asyncio
async def test_get_file_raises_when_reference_expired_without_message(monkeypatch):
    from pyrogram.errors import FileReferenceExpired

    client = AsyncMock()
    client.download_media = AsyncMock(side_effect=FileReferenceExpired())

    mgr = _FakeMgr()
    mgr.client = client
    monkeypatch.setattr(tas_mod, "account_client_manager", mgr)
    monkeypatch.setattr(
        tas_mod.telegram_rate_limiter, "acquire", AsyncMock(return_value=True)
    )

    from app.storage.errors import StorageUnavailableError

    storage = TelegramAccountStorage()
    with pytest.raises(StorageUnavailableError):
        await storage.get_file("stale-id")
