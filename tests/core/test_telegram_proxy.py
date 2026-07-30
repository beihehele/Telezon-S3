import pytest

from app.core.telegram_proxy import parse_telegram_proxy


def test_parse_socks5_with_auth():
    cfg = parse_telegram_proxy("socks5://alice:s3cret@127.0.0.1:1080")
    assert cfg is not None
    assert cfg.scheme == "socks5"
    assert cfg.hostname == "127.0.0.1"
    assert cfg.port == 1080
    assert cfg.username == "alice"
    assert cfg.password == "s3cret"
    assert cfg.as_pyrogram_dict() == {
        "scheme": "socks5",
        "hostname": "127.0.0.1",
        "port": 1080,
        "username": "alice",
        "password": "s3cret",
    }


def test_parse_socks5h_maps_for_pyrogram():
    cfg = parse_telegram_proxy("socks5h://proxy.local:9050")
    assert cfg is not None
    assert cfg.scheme == "socks5h"
    pyro = cfg.as_pyrogram_dict()
    assert pyro["scheme"] == "socks5"
    assert "username" not in pyro


def test_parse_empty_returns_none():
    assert parse_telegram_proxy("") is None
    assert parse_telegram_proxy("   ") is None
    assert parse_telegram_proxy(None) is None


def test_parse_rejects_bad_scheme():
    with pytest.raises(ValueError, match="Unsupported"):
        parse_telegram_proxy("ftp://127.0.0.1:21")


def test_parse_rejects_missing_port():
    with pytest.raises(ValueError, match="port"):
        parse_telegram_proxy("socks5://127.0.0.1")
