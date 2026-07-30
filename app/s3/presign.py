import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import quote, urlencode


def _aws_uri_encode(value: str, *, encode_slash: bool = True) -> str:
    return quote(value, safe="" if encode_slash else "/")


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def create_presigned_url(
    *,
    method: str,
    bucket: str,
    key: str,
    access_key: str,
    secret_key: str,
    host: str,
    expires_in: int = 3600,
    region: str = "us-east-1",
    scheme: str = "http",
) -> str:
    method = method.upper()
    if method not in {"GET", "PUT"}:
        raise ValueError("Only GET and PUT presigned URLs are supported")

    expires_in = max(1, min(int(expires_in), 604800))
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"
    credential = f"{access_key}/{credential_scope}"

    encoded_key = "/".join(_aws_uri_encode(part, encode_slash=True) for part in key.split("/"))
    canonical_uri = f"/{bucket}/{encoded_key}"

    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": credential,
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires_in),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_querystring = urlencode(sorted(query.items()), quote_via=quote)

    canonical_headers = f"host:{host}\n"
    signed_headers = "host"
    payload_hash = "UNSIGNED-PAYLOAD"
    canonical_request = (
        f"{method}\n"
        f"{canonical_uri}\n"
        f"{canonical_querystring}\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{payload_hash}"
    )
    string_to_sign = (
        "AWS4-HMAC-SHA256\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )
    signing_key = _signature_key(secret_key, date_stamp, region, "s3")
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    query["X-Amz-Signature"] = signature
    final_qs = urlencode(sorted(query.items()), quote_via=quote)
    return f"{scheme}://{host}{canonical_uri}?{final_qs}"
