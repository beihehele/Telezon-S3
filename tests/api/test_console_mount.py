"""Regression: /console must not be handled as S3 bucket name (route registration order)."""

from pathlib import Path


def test_console_block_before_s3_router_in_main():
    """S3 include_router must come after ENABLE_CONSOLE mount block in app/main.py."""
    main_py = Path(__file__).resolve().parents[2] / "app" / "main.py"
    content = main_py.read_text(encoding="utf-8")
    s3_pos = content.index("app.include_router(s3_router)")
    console_pos = content.index("if ENABLE_CONSOLE:")
    assert console_pos < s3_pos
