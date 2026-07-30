from pathlib import Path

from app.storage.disk_cache import cache_delete, cache_get, cache_put


def test_disk_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.storage.disk_cache.CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("app.storage.disk_cache.CACHE_MAX_BYTES", 1024)
    assert cache_get("b", "k") is None
    cache_put("b", "k", b"hello")
    assert cache_get("b", "k") == b"hello"
    cache_delete("b", "k")
    assert cache_get("b", "k") is None
