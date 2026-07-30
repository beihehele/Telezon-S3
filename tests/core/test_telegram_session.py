from app.core.telegram_session import (
    effective_session_string,
    is_configured_session_string,
)


def test_placeholder_session_not_configured():
    assert not is_configured_session_string("")
    assert not is_configured_session_string("lakkdladkladkal")
    assert not is_configured_session_string(None)
    assert effective_session_string("lakkdladkladkal") is None


def test_real_session_configured():
    value = "1BQANOTEz..." + "x" * 20
    assert is_configured_session_string(value)
    assert effective_session_string(value) == value
