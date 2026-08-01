import logging
import os
import shutil
from pathlib import Path

from app.core.config import MPU_STAGING_DIR

logger = logging.getLogger(__name__)


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


def part_tg_upload_path(upload_id: str, part_number: int, label: str) -> Path:
    """Filesystem path for Pyrogram upload; basename matches ``label`` (no RAM read)."""
    src = part_staging_path(upload_id, part_number)
    if not src.is_file():
        raise FileNotFoundError(f"staged part missing: {src}")
    dest = upload_staging_dir(upload_id) / label
    if dest.exists():
        try:
            if dest.samefile(src):
                return dest
        except OSError:
            pass
        dest.unlink()
    try:
        os.link(src, dest)
    except OSError:
        try:
            dest.symlink_to(src.resolve())
        except OSError:
            logger.warning(
                "mpu staging: hardlink/symlink failed for %s; copying", dest.name
            )
            shutil.copy2(src, dest)
    return dest


def remove_upload_staging(upload_id: str) -> None:
    if not staging_enabled():
        return
    root = upload_staging_dir(upload_id)
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)
