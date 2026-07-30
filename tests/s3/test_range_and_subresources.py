from app.s3.http_range import InvalidRange, etag_matches, parse_bytes_range
from app.s3.subresources import unsupported_subresource
from starlette.requests import Request


def test_parse_range_suffix_and_open_end():
    assert parse_bytes_range("bytes=0-3", 10) == (0, 3)
    assert parse_bytes_range("bytes=8-", 10) == (8, 9)
    assert parse_bytes_range("bytes=-3", 10) == (7, 9)


def test_parse_range_unsatisfiable():
    try:
        parse_bytes_range("bytes=20-30", 10)
        assert False
    except InvalidRange:
        pass


def test_etag_matches():
    assert etag_matches('"abc"', '"abc"')
    assert etag_matches('W/"abc", "xyz"', "xyz")
    assert etag_matches("*", "anything")


def test_unsupported_acl_detected():
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "PUT",
        "scheme": "http",
        "path": "/b/k",
        "raw_path": b"/b/k",
        "query_string": b"acl",
        "headers": [],
        "client": ("127.0.0.1", 0),
        "server": ("test", 80),
    }
    request = Request(scope)
    assert unsupported_subresource(request) == "acl"
