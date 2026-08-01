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


def test_input_media_document_accepts_bytesio_with_name():
    from pyrogram.types import InputMediaDocument

    document = io.BytesIO(b"chunk")
    document.name = "part-00001.bin"
    InputMediaDocument(document)


@pytest.mark.asyncio
async def test_send_media_group_builds_input_media_from_named_bytesio(monkeypatch):
    built: list[io.BytesIO] = []

    class RecordingInputMediaDocument:
        def __init__(self, media):
            built.append(media)

    client = AsyncMock()
    message = MagicMock()
    message.document = MagicMock(file_id="fid-1")
    message.id = 7
    client.send_media_group = AsyncMock(return_value=[message])

    mgr = _FakeMgr()
    mgr.client = client
    monkeypatch.setattr(tas_mod, "account_client_manager", mgr)
    monkeypatch.setattr(
        tas_mod.telegram_rate_limiter, "acquire", AsyncMock(return_value=True)
    )

    import sys

    fake_types = MagicMock()
    fake_types.InputMediaDocument = RecordingInputMediaDocument
    monkeypatch.setitem(sys.modules, "pyrogram.types", fake_types)

    storage = TelegramAccountStorage()
    results = await storage.send_media_group(
        [(b"one", "a.bin"), (b"two", "b.bin")], chat_id="123"
    )

    assert len(built) == 2
    assert built[0].getvalue() == b"one" and built[0].name == "a.bin"
    assert built[1].getvalue() == b"two" and built[1].name == "b.bin"
    assert len(results) == 1
    assert results[0].file_id == "fid-1"
    assert results[0].message_id == 7


@pytest.mark.asyncio
async def test_send_media_group_accepts_staging_path(monkeypatch, tmp_path):
    built: list[str] = []

    class RecordingInputMediaDocument:
        def __init__(self, media):
            built.append(media)

    staging_file = tmp_path / "opaque.part1"
    staging_file.write_bytes(b"from-disk")

    client = AsyncMock()
    message = MagicMock()
    message.document = MagicMock(file_id="fid-path")
    message.id = 8
    client.send_media_group = AsyncMock(return_value=[message])

    mgr = _FakeMgr()
    mgr.client = client
    monkeypatch.setattr(tas_mod, "account_client_manager", mgr)
    monkeypatch.setattr(
        tas_mod.telegram_rate_limiter, "acquire", AsyncMock(return_value=True)
    )

    import sys

    fake_types = MagicMock()
    fake_types.InputMediaDocument = RecordingInputMediaDocument
    monkeypatch.setitem(sys.modules, "pyrogram.types", fake_types)

    storage = TelegramAccountStorage()
    label = staging_file.name
    results = await storage.send_media_group(
        [(str(staging_file), label)], chat_id="123"
    )
    assert built == [str(staging_file)]
    assert results[0].file_id == "fid-path"
