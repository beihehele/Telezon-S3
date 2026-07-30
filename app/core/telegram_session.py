"""Helpers for Telegram Pyrogram session strings from environment."""

from __future__ import annotations

# Placeholders shipped in .env.example — treat as "not configured".
_PLACEHOLDER_SESSION_VALUES = frozenset(
    {
        "",
        "lakkdladkladkal",
        "changeme",
        "your_session_string",
    }
)


def is_configured_session_string(value: str | None) -> bool:
    if value is None:
        return False
    stripped = value.strip()
    if not stripped:
        return False
    return stripped.lower() not in _PLACEHOLDER_SESSION_VALUES


def effective_session_string(value: str | None) -> str | None:
    if is_configured_session_string(value):
        return value.strip()
    return None
