"""Stable object-key identity for MySQL unique indexes (TEXT paths)."""

from __future__ import annotations

import hashlib


def blob_path_digest(bucket_name: str, path: str) -> str:
    payload = f"{bucket_name}\n{path}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
