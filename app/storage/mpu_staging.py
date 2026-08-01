import shutil
from pathlib import Path

from app.core.config import MPU_STAGING_DIR


def staging_enabled() -> bool:
    return bool(MPU_STAGING_DIR)


def upload_staging_dir(upload_id: str) -> Path:
    return Path(MPU_STAGING_DIR) / upload_id


def part_staging_path(upload_id: str, part_number: int) -> Path:
    return upload_staging_dir(upload_id) / f"part-{part_number}"


def write_part(upload_id: str, part_number: int, data: bytes) -> Path:
    if not staging_enabled():
        raise RuntimeError("MPU_STAGING_DIR is not configured")
    path = part_staging_path(upload_id, part_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def read_part(upload_id: str, part_number: int) -> bytes:
    return part_staging_path(upload_id, part_number).read_bytes()


def remove_upload_staging(upload_id: str) -> None:
    if not staging_enabled():
        return
    root = upload_staging_dir(upload_id)
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)
