def escape_like_prefix(value: str) -> str:
    """Escape % and _ for SQL LIKE prefix patterns."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
