from pathlib import Path

import pytest

from app.storage.backend import media_group_source_bytes
from app.storage.mpu_staging import (
    part_staging_path,
    part_tg_upload_path,
    remove_upload_staging,
    write_part,
)


def test_part_tg_upload_path_uses_label_basename(tmp_path, monkeypatch):
    monkeypatch.setattr("app.storage.mpu_staging.MPU_STAGING_DIR", str(tmp_path))
    upload_id = "up-1"
    write_part(upload_id, 1, b"payload")
    label = "abc123.part1"
    upload_path = part_tg_upload_path(upload_id, 1, label)
    assert upload_path.name == label
    assert upload_path.read_bytes() == b"payload"
    assert part_staging_path(upload_id, 1).exists()
    again = part_tg_upload_path(upload_id, 1, label)
    assert again == upload_path
    remove_upload_staging(upload_id)
    assert not Path(tmp_path / upload_id).exists()


def test_media_group_source_bytes(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    assert media_group_source_bytes(b"raw") == b"raw"
    assert media_group_source_bytes(str(path)) == b"abc"
    assert media_group_source_bytes(path) == b"abc"
