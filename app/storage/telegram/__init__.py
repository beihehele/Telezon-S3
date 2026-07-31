__all__ = ["TelegramAccountStorage", "TelegramBotStorage"]


def __getattr__(name: str):
    if name == "TelegramAccountStorage":
        from app.storage.telegram.telegram_account_storage import TelegramAccountStorage

        return TelegramAccountStorage
    if name == "TelegramBotStorage":
        from app.storage.telegram.telegram_bot_storage import TelegramBotStorage

        return TelegramBotStorage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
