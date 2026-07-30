from starlette.requests import Request

from app.core.config import MAX_UPLOAD_BYTES
from app.s3.errors import s3_error_response


class BodyTooLarge(Exception):
    def __init__(self, size: int):
        self.size = size


async def read_body_capped(request: Request, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise BodyTooLarge(total)
        chunks.append(chunk)
    return b"".join(chunks)


def reject_oversized_content_length(request: Request, resource: str):
    content_length = request.headers.get("content-length")
    if content_length is None:
        return s3_error_response(
            status_code=411,
            code="MissingContentLength",
            message="Content-Length header is required",
            resource=resource,
        )
    if not content_length.isdigit():
        return s3_error_response(
            status_code=400,
            code="InvalidRequest",
            message="Invalid Content-Length header",
            resource=resource,
        )
    declared = int(content_length)
    if declared > MAX_UPLOAD_BYTES:
        return s3_error_response(
            status_code=400,
            code="EntityTooLarge",
            message=(
                f"Object size {declared} exceeds maximum allowed size "
                f"{MAX_UPLOAD_BYTES} bytes"
            ),
            resource=resource,
        )
    return None
