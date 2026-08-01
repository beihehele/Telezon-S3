"""Detect S3 ListObjects-style bucket GET requests (e.g. S3 Browser trailing slash)."""

from starlette.requests import Request


def looks_like_list_objects(request: Request) -> bool:
    q = request.query_params
    return (
        "delimiter" in q
        or "prefix" in q
        or "max-keys" in q
        or "list-type" in q
        or "continuation-token" in q
        or "start-after" in q
        or "encoding-type" in q
    )
