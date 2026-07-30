"""HTTP middleware adding S3-style request tracing headers."""

from __future__ import annotations

import uuid
from email.utils import formatdate

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class AmzRequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = uuid.uuid4().hex
        request.state.amz_request_id = request_id
        response = await call_next(request)
        response.headers.setdefault("x-amz-request-id", request_id)
        response.headers.setdefault("x-amz-id-2", request_id)
        if "date" not in {k.lower() for k in response.headers.keys()}:
            response.headers["Date"] = formatdate(usegmt=True)
        return response
