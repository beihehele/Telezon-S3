import pytest

from app.storage.telegram.account_client import TelegramAccountClientManager


@pytest.mark.asyncio
async def test_start_cleans_up_when_warmup_fails(monkeypatch):
    manager = TelegramAccountClientManager()
    stopped = {"n": 0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.is_connected = False

        async def start(self):
            self.is_connected = True

        async def stop(self):
            stopped["n"] += 1
            self.is_connected = False

        def get_dialogs(self):
            async def _gen():
                raise RuntimeError("warmup failed")
                yield  # pragma: no cover

            return _gen()

    class FakePyrogram:
        Client = FakeClient

    monkeypatch.setitem(__import__("sys").modules, "pyrogram", FakePyrogram)

    with pytest.raises(RuntimeError, match="warmup failed"):
        await manager.start()

    assert manager.client is None
    assert manager.ready is False
    assert stopped["n"] == 1
