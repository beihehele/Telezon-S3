import tempfile
import uuid
from pathlib import Path

from app.core.config import CACHE_DIR


def new_put_staging_file() -> Path:
    if CACHE_DIR:
        root = Path(CACHE_DIR) / "put-staging"
    else:
        root = Path(tempfile.gettempdir()) / "telezon-put-staging"
    root.mkdir(parents=True, exist_ok=True)
    return root / uuid.uuid4().hex
