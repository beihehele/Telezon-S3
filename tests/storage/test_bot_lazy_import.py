import importlib
import sys


def test_import_account_client_without_bot_token(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    saved = {
        name: sys.modules[name]
        for name in list(sys.modules)
        if name == "app.storage.telegram.bot"
        or name.startswith("app.storage.telegram.")
        or name == "app.core.config"
    }
    try:
        for name in saved:
            sys.modules.pop(name, None)

        config = importlib.import_module("app.core.config")
        assert config.TOKEN is None

        account_client = importlib.import_module("app.storage.telegram.account_client")
        assert account_client.account_client_manager is not None

        bot_mod = importlib.import_module("app.storage.telegram.bot")
        assert bot_mod._updater is None
    finally:
        for name in saved:
            sys.modules[name] = saved[name]
