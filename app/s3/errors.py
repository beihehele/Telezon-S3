from xml.sax.saxutils import escape
from uuid import uuid4

from starlette.responses import Response

from app.s3.i18n import s3_message


def s3_error_response(
    *,
    status_code: int,
    code: str,
    message: str | None = None,
    resource: str = "/",
    request_id: str | None = None,
) -> Response:
    rid = request_id or uuid4().hex
    text = message or s3_message(code)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Error>"
        f"<Code>{escape(code)}</Code>"
        f"<Message>{escape(text)}</Message>"
        f"<Resource>{escape(resource)}</Resource>"
        f"<RequestId>{escape(rid)}</RequestId>"
        "</Error>"
    )
    return Response(
        content=body,
        status_code=status_code,
        media_type="application/xml",
    )
