import pytest

from app.core.config import validate_secret_key


def test_validate_secret_key_accepts_strong_key():
    assert validate_secret_key("pytest-secret-key-min-16b") == "pytest-secret-key-min-16b"


def test_validate_secret_key_rejects_placeholder():
    with pytest.raises(RuntimeError, match="placeholder"):
        validate_secret_key("change-me-to-a-long-random-string")


def test_validate_secret_key_rejects_short():
    with pytest.raises(RuntimeError, match="16"):
        validate_secret_key("short")
