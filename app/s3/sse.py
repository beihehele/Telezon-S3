import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SseError(Exception):
    pass


def _key_from_header(b64_key: str) -> bytes:
    try:
        key = base64.b64decode(b64_key)
    except Exception as exc:
        raise SseError("Invalid SSE customer key") from exc
    if len(key) != 32:
        raise SseError("SSE customer key must decode to 32 bytes")
    return key


def sse_key_md5_b64(b64_key: str) -> str:
    key = _key_from_header(b64_key)
    return base64.b64encode(hashlib.md5(key).digest()).decode()


def encrypt_sse_c(
    plaintext: bytes, b64_key: str, *, aad: bytes = b""
) -> tuple[bytes, str, str]:
    key = _key_from_header(b64_key)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad or None)
    body, tag = ciphertext[:-16], ciphertext[-16:]
    return body, base64.b64encode(nonce).decode(), base64.b64encode(tag).decode()


def decrypt_sse_c(
    ciphertext: bytes,
    b64_key: str,
    b64_nonce: str,
    b64_tag: str,
    *,
    aad: bytes = b"",
) -> bytes:
    key = _key_from_header(b64_key)
    nonce = base64.b64decode(b64_nonce)
    tag = base64.b64decode(b64_tag)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext + tag, aad or None)
