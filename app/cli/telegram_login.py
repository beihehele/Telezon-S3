"""
Interactive Telegram login for account-mode storage.

Run locally: poetry run python setup_account_storage.py
Docker:      docker compose --profile setup run --rm setup
"""

from __future__ import annotations

import sys

from pyrogram import Client
from pyrogram.types import Message

from app.core.config import (
    SESSION_STRING,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_PROXY,
)
from app.core.telegram_session import effective_session_string


def _require_api_credentials() -> tuple[int, str]:
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        print(
            "Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env first "
            "(https://my.telegram.org/apps).",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        api_id = int(str(TELEGRAM_API_ID).strip())
    except ValueError:
        print("TELEGRAM_API_ID must be a number.", file=sys.stderr)
        sys.exit(1)
    api_hash = str(TELEGRAM_API_HASH).strip()
    if not api_hash:
        print("TELEGRAM_API_HASH is empty.", file=sys.stderr)
        sys.exit(1)
    return api_id, api_hash


def _client_kwargs(api_id: int, api_hash: str, session_string: str | None) -> dict:
    kwargs: dict = {
        "name": "telezon_setup",
        "api_id": api_id,
        "api_hash": api_hash,
        "in_memory": True,
    }
    if session_string:
        kwargs["session_string"] = session_string
    if TELEGRAM_PROXY is not None:
        kwargs["proxy"] = TELEGRAM_PROXY.as_pyrogram_dict()
    return kwargs


def _export_session(api_id: int, api_hash: str) -> str:
    existing = effective_session_string(SESSION_STRING)
    client = Client(**_client_kwargs(api_id, api_hash, existing))

    print()
    print("=== Telegram login (interactive) ===")
    if existing:
        print("Using SESSION_STRING from .env to refresh export.")
    else:
        print(
            "You will be asked for phone number, login code, and 2FA if enabled."
        )
    print()

    with client:
        session = client.export_session_string()

    print()
    print("=== Copy into .env ===")
    print("SESSION_STRING=" + session)
    print()
    print("Then set CID (default storage chat) and run: docker compose up -d")
    print()
    return session


def _listen_for_cid(api_id: int, api_hash: str, session_string: str) -> None:
    client = Client(**_client_kwargs(api_id, api_hash, session_string))

    @client.on_message()
    def cid_handler(_: Client, message: Message):
        print(f"CID={message.chat.id}  (chat title: {message.chat.title!r})")

    print("=== Channel / chat ID ===")
    print("Post any message in your storage channel (or group).")
    print("The chat id will print below. Put it in .env as CID=...")
    print("Press Ctrl+C to stop.")
    print()
    client.run()


def main() -> None:
    api_id, api_hash = _require_api_credentials()
    session = _export_session(api_id, api_hash)

    try:
        answer = input("Listen for CID now? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if answer in ("y", "yes"):
        _listen_for_cid(api_id, api_hash, session)


if __name__ == "__main__":
    main()
