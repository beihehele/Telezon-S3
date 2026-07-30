"""HTTP Range and conditional request helpers for GetObject/HeadObject."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


class InvalidRange(Exception):
    pass


def parse_bytes_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Return inclusive (start, end) or None if no Range. Raises InvalidRange."""
    if not header:
        return None
    value = header.strip()
    if not value.lower().startswith("bytes="):
        raise InvalidRange("Only bytes ranges are supported")
    spec = value[6:].strip()
    if "," in spec:
        raise InvalidRange("Multiple ranges are not supported")
    if "-" not in spec:
        raise InvalidRange("Malformed Range")
    start_s, end_s = spec.split("-", 1)
    if size == 0:
        raise InvalidRange("Empty object")
    if start_s == "":
        # suffix: bytes=-N
        if not end_s.isdigit():
            raise InvalidRange("Malformed Range")
        length = int(end_s)
        if length <= 0:
            raise InvalidRange("Malformed Range")
        start = max(0, size - length)
        end = size - 1
    elif end_s == "":
        if not start_s.isdigit():
            raise InvalidRange("Malformed Range")
        start = int(start_s)
        end = size - 1
    else:
        if not start_s.isdigit() or not end_s.isdigit():
            raise InvalidRange("Malformed Range")
        start = int(start_s)
        end = int(end_s)
    if start < 0 or end < start or start >= size:
        raise InvalidRange("Requested range not satisfiable")
    end = min(end, size - 1)
    return start, end


def etag_matches(header_value: str | None, etag: str) -> bool:
    if not header_value:
        return False
    etag_norm = etag.strip().strip('"')
    for part in header_value.split(","):
        token = part.strip()
        if token == "*":
            return True
        if token.strip('"') == etag_norm:
            return True
    return False


def _parse_http_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def evaluate_conditionals(
    *,
    etag: str,
    last_modified: datetime | None,
    if_match: str | None,
    if_none_match: str | None,
    if_modified_since: str | None,
    if_unmodified_since: str | None,
) -> str | None:
    """
    Return None to proceed, 'not_modified' for 304, 'precondition_failed' for 412.
    Precedence roughly follows RFC 9110 / S3 practice for If-Match / If-None-Match.
    """
    if if_match is not None and not etag_matches(if_match, etag):
        return "precondition_failed"

    if if_none_match is not None and etag_matches(if_none_match, etag):
        return "not_modified"

    lm = last_modified
    if lm is not None and lm.tzinfo is None:
        lm = lm.replace(tzinfo=timezone.utc)

    if if_unmodified_since is not None and lm is not None:
        since = _parse_http_date(if_unmodified_since)
        if since is not None and lm > since:
            return "precondition_failed"

    if if_modified_since is not None and lm is not None:
        since = _parse_http_date(if_modified_since)
        if since is not None and lm <= since:
            return "not_modified"

    return None
