"""Resolve SigV4 callers: primary user key or scoped credentials."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from starlette.requests import Request

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.credential import crud_get_credential_by_access_key
from app.crud.user import crud_get_user_by_access_key_id
from app.models.bucket import Bucket
from app.models.credential import ROLE_READONLY, ROLE_READWRITE
from app.models.user import UserInDb
from app.s3.awssig import AWSSigV4Verifier, InvalidSignatureError

logger = logging.getLogger(__name__)

DEFAULT_TIMESTAMP_MISMATCH_SECONDS = 900

_WRITE_METHODS = {"PUT", "POST", "DELETE", "PATCH"}

AUTH_OK = "ok"
AUTH_SIGNATURE = "signature"
AUTH_DENIED = "access_denied"
AUTH_MISSING = "missing"


@dataclass
class AccessIdentity:
    access_key_id: str
    secret_key: str
    owner_username: str
    role: str  # owner | readwrite | readonly
    buckets: list[str] | None  # None = all buckets of owner
    is_primary: bool

    def allows_bucket(self, bucket_name: str) -> bool:
        if self.buckets is None:
            return True
        return bucket_name in self.buckets

    def can_read(self, bucket: Bucket) -> bool:
        if bucket.owner.username != self.owner_username:
            return False
        return self.allows_bucket(bucket.name)

    def can_write(self, bucket: Bucket) -> bool:
        if not self.can_read(bucket):
            return False
        return self.role in {"owner", ROLE_READWRITE}

    def can_create_bucket(self) -> bool:
        # Primary key, or unrestricted readwrite credential.
        if self.is_primary:
            return True
        return self.role == ROLE_READWRITE and self.buckets is None


def _request_path(request: Request) -> str:
    return request.url.path


def _query_string(request: Request) -> str:
    raw = request.url.query
    if raw:
        return raw
    return str(request.query_params)


def extract_access_key(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth and auth.startswith("AWS4-HMAC-SHA256 "):
        for part in auth[len("AWS4-HMAC-SHA256 ") :].split(","):
            part = part.strip()
            if part.startswith("Credential="):
                cred = part.split("=", 1)[1]
                return cred.split("/", 1)[0]

    cred = request.query_params.get("X-Amz-Credential")
    if cred:
        return cred.split("/", 1)[0]
    return None


def is_presigned_request(request: Request) -> bool:
    return (
        request.query_params.get("X-Amz-Algorithm") == "AWS4-HMAC-SHA256"
        and "X-Amz-Signature" in request.query_params
    )


def _parse_amz_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _presign_still_valid(request: Request) -> bool:
    try:
        expires = int(request.query_params.get("X-Amz-Expires", "0"))
    except ValueError:
        return False
    if expires <= 0 or expires > 604800:
        return False

    amz_date = request.query_params.get("X-Amz-Date")
    started = _parse_amz_date(amz_date) if amz_date else None
    if started is None:
        return False

    deadline = started + timedelta(seconds=expires)
    now = datetime.now(timezone.utc)
    if started - now > timedelta(seconds=DEFAULT_TIMESTAMP_MISMATCH_SECONDS):
        return False
    return now <= deadline


async def verify_sigv4(
    request: Request,
    key_mapping: dict[str, str],
    *,
    body: bytes | None = None,
    timestamp_mismatch: int | None = DEFAULT_TIMESTAMP_MISMATCH_SECONDS,
) -> bool:
    if body is None:
        if request.method.upper() in {"GET", "HEAD", "DELETE"}:
            body = b""
        else:
            body = await request.body()

    headers = {k: v for k, v in request.headers.items()}
    if "x-amz-date" in headers and "X-Amz-Date" not in headers:
        headers["X-Amz-Date"] = headers["x-amz-date"]

    if is_presigned_request(request):
        if not _presign_still_valid(request):
            return False
        if "x-amz-content-sha256" not in {k.lower() for k in headers}:
            headers["x-amz-content-sha256"] = "UNSIGNED-PAYLOAD"
        timestamp_mismatch = None

    verifier = AWSSigV4Verifier(
        request_method=request.method,
        uri_path=_request_path(request),
        query_string=_query_string(request),
        headers=headers,
        body=body,
        region="us-east-1",
        service="s3",
        key_mapping=key_mapping,
        timestamp_mismatch=timestamp_mismatch,
    )
    try:
        verifier.verify()
        return True
    except InvalidSignatureError as exc:
        logger.info("Invalid SigV4 signature: %s", exc)
        return False
    except Exception:
        logger.exception("Unable to verify SigV4 request")
        return False


async def resolve_identity(
    db: AsyncSession, access_key_id: str
) -> AccessIdentity | None:
    user = await crud_get_user_by_access_key_id(db, access_key_id)
    if user:
        return AccessIdentity(
            access_key_id=user.access_key_id,
            secret_key=user.secret_key,
            owner_username=user.username,
            role="owner",
            buckets=None,
            is_primary=True,
        )

    cred = await crud_get_credential_by_access_key(db, access_key_id)
    if not cred:
        return None
    buckets = cred.buckets if cred.buckets else None
    return AccessIdentity(
        access_key_id=cred.access_key_id,
        secret_key=cred.secret_key,
        owner_username=cred.owner_username,
        role=cred.role,
        buckets=buckets,
        is_primary=False,
    )


async def resolve_verified_identity(
    db: AsyncSession,
    request: Request,
    *,
    body: bytes | None = None,
) -> AccessIdentity | None:
    access_key = extract_access_key(request)
    if not access_key:
        return None
    identity = await resolve_identity(db, access_key)
    if not identity:
        return None
    ok = await verify_sigv4(
        request,
        {identity.access_key_id: identity.secret_key},
        body=body,
    )
    if not ok:
        return None
    return identity


def _method_allowed(identity: AccessIdentity, request: Request, bucket: Bucket) -> bool:
    method = request.method.upper()
    if method in _WRITE_METHODS:
        return identity.can_write(bucket)
    return identity.can_read(bucket)


async def authorize_request_for_bucket(
    bucket: Bucket,
    request: Request,
    db: AsyncSession | None = None,
    *,
    body: bytes | None = None,
) -> str:
    """Return AUTH_OK / AUTH_SIGNATURE / AUTH_DENIED / AUTH_MISSING."""
    owner = bucket.owner
    if db is None:
        ok = await verify_sigv4(
            request,
            {owner.access_key_id: owner.secret_key},
            body=body,
        )
        return AUTH_OK if ok else AUTH_SIGNATURE

    access_key = extract_access_key(request)
    if not access_key:
        return AUTH_MISSING

    identity = await resolve_identity(db, access_key)
    if identity is None and access_key == owner.access_key_id:
        identity = AccessIdentity(
            access_key_id=owner.access_key_id,
            secret_key=owner.secret_key,
            owner_username=owner.username,
            role="owner",
            buckets=None,
            is_primary=True,
        )
    if identity is None:
        return AUTH_MISSING

    if not await verify_sigv4(
        request,
        {identity.access_key_id: identity.secret_key},
        body=body,
    ):
        return AUTH_SIGNATURE

    if not _method_allowed(identity, request, bucket):
        return AUTH_DENIED
    return AUTH_OK


async def precheck_request_for_bucket(
    bucket: Bucket,
    request: Request,
    db: AsyncSession | None = None,
) -> str:
    """Identity + RBAC only (no payload signature).

    Call before buffering large bodies so unknown keys and denied roles fail
    cheaply. Full ``authorize_request_for_bucket`` must still run after the body
    is available.
    """
    owner = bucket.owner
    if db is None:
        access_key = extract_access_key(request)
        if not access_key:
            return AUTH_MISSING
        if access_key != owner.access_key_id:
            return AUTH_MISSING
        return AUTH_OK

    access_key = extract_access_key(request)
    if not access_key:
        return AUTH_MISSING

    identity = await resolve_identity(db, access_key)
    if identity is None and access_key == owner.access_key_id:
        identity = AccessIdentity(
            access_key_id=owner.access_key_id,
            secret_key=owner.secret_key,
            owner_username=owner.username,
            role="owner",
            buckets=None,
            is_primary=True,
        )
    if identity is None:
        return AUTH_MISSING
    if not _method_allowed(identity, request, bucket):
        return AUTH_DENIED
    return AUTH_OK


async def verify_request_for_bucket(
    bucket: Bucket,
    request: Request,
    db: AsyncSession | None = None,
    *,
    body: bytes | None = None,
) -> bool:
    """Verify SigV4 and RBAC for a bucket.

    When ``db`` is omitted, falls back to the bucket owner primary key only
    (legacy test helpers). Production handlers must pass ``db``.
    """
    return (
        await authorize_request_for_bucket(bucket, request, db, body=body) == AUTH_OK
    )


def auth_error_response(auth_code: str, resource: str):
    from app.s3.errors import s3_error_response

    if auth_code == AUTH_DENIED:
        return s3_error_response(
            status_code=403,
            code="AccessDenied",
            message="Access Denied",
            resource=resource,
        )
    if auth_code == AUTH_MISSING:
        return s3_error_response(
            status_code=403,
            code="InvalidAccessKeyId",
            message="The AWS Access Key Id you provided does not exist",
            resource=resource,
        )
    return s3_error_response(
        status_code=403,
        code="SignatureDoesNotMatch",
        message="The request signature we calculated does not match",
        resource=resource,
    )


async def resolve_user_from_request(
    db: AsyncSession, request: Request, *, body: bytes | None = None
) -> UserInDb | None:
    identity = await resolve_verified_identity(db, request, body=body)
    if not identity:
        return None
    user = await crud_get_user_by_access_key_id(db, identity.access_key_id)
    if user:
        return user
    from app.crud.user import crud_get_user_by_username

    return await crud_get_user_by_username(db, identity.owner_username)


async def resolve_identity_from_request(
    db: AsyncSession, request: Request, *, body: bytes | None = None
) -> AccessIdentity | None:
    return await resolve_verified_identity(db, request, body=body)


async def aws_sig_verify(bucket: Bucket, request: Request) -> bool:
    return await verify_request_for_bucket(bucket, request)
