import base64
import os

from app.s3.sse import decrypt_sse_c, encrypt_sse_c


def test_sse_roundtrip():
    key = base64.b64encode(os.urandom(32)).decode()
    plain = b"secret-bytes-123"
    aad = b"bucket/key"
    cipher, nonce, tag = encrypt_sse_c(plain, key, aad=aad)
    assert cipher != plain
    out = decrypt_sse_c(cipher, key, nonce, tag, aad=aad)
    assert out == plain


def test_sse_aad_mismatch_fails():
    key = base64.b64encode(os.urandom(32)).decode()
    plain = b"secret-bytes-123"
    cipher, nonce, tag = encrypt_sse_c(plain, key, aad=b"a/b")
    try:
        decrypt_sse_c(cipher, key, nonce, tag, aad=b"other")
        assert False, "expected decrypt failure"
    except Exception:
        pass
