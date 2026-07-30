"""Telegram storage backends.

Production path always uses account mode (`TelegramAccountStorage` / Pyrogram).
`TelegramBotStorage` remains for historical scripts and is not selected at runtime.
"""

from app.storage.backend import PutFileResult, Storage

__all__ = [
    "PutFileResult",
    "Storage",
    "TelegramAccountStorage",
    "TelegramBotStorage",
    "storage",
]

_storage: Storage | None = None


def __getattr__(name: str):
    global _storage
    if name in {"TelegramAccountStorage", "TelegramBotStorage"}:
        from app.storage.telegram import TelegramAccountStorage, TelegramBotStorage

        globals()["TelegramAccountStorage"] = TelegramAccountStorage
        globals()["TelegramBotStorage"] = TelegramBotStorage
        return globals()[name]
    if name == "storage":
        if _storage is None:
            from app.storage.telegram import TelegramAccountStorage

            _storage = TelegramAccountStorage()
            globals()["_storage"] = _storage
        return _storage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
