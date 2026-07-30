"""Reject unsupported S3 sub-resource query params before data ops."""

from starlette.requests import Request

from app.s3.errors import s3_error_response

# Present on a request → must not fall through to Put/Get/Delete object.
UNSUPPORTED_SUBRESOURCES = frozenset(
    {
        "acl",
        "policy",
        "cors",
        "encryption",
        "notification",
        "replication",
        "website",
        "logging",
        "analytics",
        "metrics",
        "inventory",
        "accelerate",
        "requestPayment",
        "object-lock",
        "legal-hold",
        "retention",
        "torrent",
        "restore",
        "select",
        "intelligent-tiering",
        "ownershipControls",
        "publicAccessBlock",
        "versions",
        "lifecycle",
        "tagging",
    }
)

# Allowed when implementing DeleteObjects / multipart / list / presign.
_ALLOWED_ALWAYS = frozenset(
    {
        "list-type",
        "prefix",
        "continuation-token",
        "start-after",
        "max-keys",
        "encoding-type",
        "delimiter",
        "uploads",
        "uploadId",
        "partNumber",
        "delete",
        "x-id",
        "key-marker",
        "upload-id-marker",
        "max-uploads",
        "location",
        "versioning",
    }
)


def unsupported_subresource(request: Request) -> str | None:
    for name in request.query_params.keys():
        lower = name.lower()
        if lower.startswith("x-amz-"):
            continue
        if lower in _ALLOWED_ALWAYS:
            continue
        if lower in UNSUPPORTED_SUBRESOURCES or name in UNSUPPORTED_SUBRESOURCES:
            return name
    return None


def reject_unsupported_subresource(request: Request, resource: str):
    name = unsupported_subresource(request)
    if not name:
        return None
    return s3_error_response(
        status_code=501,
        code="NotImplemented",
        message=f"The {name} sub-resource is not supported.",
        resource=resource,
    )
