class StorageThrottleError(Exception):
    """Raised when Telegram rate limiter cannot acquire a token in time."""


class StorageUnavailableError(Exception):
    """Raised when the Telegram client is not ready."""


class StorageObjectGoneError(Exception):
    """Raised when a Telegram file/message is confirmed missing."""
