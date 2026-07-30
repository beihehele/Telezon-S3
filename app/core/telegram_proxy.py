"""Telegram outbound proxy helpers (SOCKS5 / SOCKS4 / HTTP)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class TelegramProxyConfig:
    """Parsed proxy settings for Bot API (URL) and Pyrogram (dict)."""

    url: str
    scheme: str
    hostname: str
    port: int
    username: str | None = None
    password: str | None = None

    def as_pyrogram_dict(self) -> dict:
        # Pyrogram expects socks5/socks4/http; socks5h → socks5 (DNS via proxy
        # is handled by the socks stack when hostname is used).
        scheme = self.scheme
        if scheme == "socks5h":
            scheme = "socks5"
        if scheme == "https":
            scheme = "http"
        result = {
            "scheme": scheme,
            "hostname": self.hostname,
            "port": self.port,
        }
        if self.username is not None:
            result["username"] = self.username
        if self.password is not None:
            result["password"] = self.password
        return result


_ALLOWED_SCHEMES = {"socks5", "socks5h", "socks4", "http", "https"}


def parse_telegram_proxy(raw: str | None) -> TelegramProxyConfig | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None

    parsed = urlparse(value)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Unsupported TELEGRAM_PROXY scheme '{parsed.scheme}'. "
            f"Use one of: {', '.join(sorted(_ALLOWED_SCHEMES))}"
        )
    if not parsed.hostname:
        raise ValueError("TELEGRAM_PROXY must include a hostname")
    if parsed.port is None:
        raise ValueError("TELEGRAM_PROXY must include a port")

    username = unquote(parsed.username) if parsed.username is not None else None
    password = unquote(parsed.password) if parsed.password is not None else None
    return TelegramProxyConfig(
        url=value,
        scheme=scheme,
        hostname=parsed.hostname,
        port=int(parsed.port),
        username=username,
        password=password,
    )
