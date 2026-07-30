import hashlib
import json
import os
import threading
from pathlib import Path

from app.core.config import CACHE_DIR, CACHE_MAX_BYTES

_lock = threading.Lock()


def _enabled() -> bool:
    return bool(CACHE_DIR)


def _root() -> Path:
    return Path(CACHE_DIR)


def _path_for(bucket: str, key: str) -> Path:
    digest = hashlib.sha256(f"{bucket}/{key}".encode("utf-8")).hexdigest()
    return _root() / digest[:2] / digest


def _meta_path() -> Path:
    return _root() / "cache-meta.json"


def _load_meta() -> dict:
    path = _meta_path()
    if not path.is_file():
        return {"total": 0, "entries": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"total": 0, "entries": {}}


def _save_meta(meta: dict) -> None:
    _root().mkdir(parents=True, exist_ok=True)
    path = _meta_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta), encoding="utf-8")
    os.replace(tmp, path)


def cache_get(bucket: str, key: str) -> bytes | None:
    if not _enabled():
        return None
    path = _path_for(bucket, key)
    if not path.is_file():
        return None
    return path.read_bytes()


def cache_put(bucket: str, key: str, data: bytes) -> None:
    if not _enabled():
        return
    if len(data) > CACHE_MAX_BYTES:
        return

    with _lock:
        meta = _load_meta()
        entry_key = f"{bucket}/{key}"
        old_size = int(meta["entries"].get(entry_key, 0))
        while meta["total"] - old_size + len(data) > CACHE_MAX_BYTES and meta["entries"]:
            victim, victim_size = next(iter(meta["entries"].items()))
            vb, _, vk = victim.partition("/")
            _cache_delete_unlocked(vb, vk)
            meta = _load_meta()
            old_size = int(meta["entries"].get(entry_key, 0))

        if meta["total"] - old_size + len(data) > CACHE_MAX_BYTES:
            return

        path = _path_for(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

        meta["total"] = meta["total"] - old_size + len(data)
        meta["entries"][entry_key] = len(data)
        _save_meta(meta)


def _cache_delete_unlocked(bucket: str, key: str) -> None:
    path = _path_for(bucket, key)
    meta = _load_meta()
    entry_key = f"{bucket}/{key}"
    size = int(meta["entries"].pop(entry_key, 0))
    meta["total"] = max(0, meta["total"] - size)
    _save_meta(meta)
    if path.is_file():
        path.unlink(missing_ok=True)


def cache_delete(bucket: str, key: str) -> None:
    if not _enabled():
        return
    with _lock:
        _cache_delete_unlocked(bucket, key)
