"""Telegram storage backends.

Production path always uses account mode (`TelegramAccountStorage` / Pyrogram).
`TelegramBotStorage` remains for historical scripts and is not selected at runtime.
"""

from app.storage.storage import PutFileResult, Storage

__all__ = [
    "PutFileResult",
    "Storage",
    "TelegramAccountStorage",
    "TelegramBotStorage",
    "storage",
]


def __getattr__(name: str):
    if name in {"TelegramAccountStorage", "TelegramBotStorage", "storage"}:
        from app.storage.telegram import TelegramAccountStorage, TelegramBotStorage

        globals()["TelegramAccountStorage"] = TelegramAccountStorage
        globals()["TelegramBotStorage"] = TelegramBotStorage
        if "storage" not in globals() or globals().get("storage") is None:
            # Account mode only — do not auto-select BotStorage.
            globals()["storage"] = TelegramAccountStorage()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
