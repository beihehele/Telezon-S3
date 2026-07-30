import os

import uvicorn
from dotenv import load_dotenv

from app.core.telegram_proxy import parse_telegram_proxy

load_dotenv()

logger = uvicorn.logging.logging.getLogger("uvicorn")


# ENVIRONMENT = os.getenv("ENVIRONMENT")
PROJECT_NAME = os.getenv("PROJECT_NAME")
PORT = int(os.getenv("PORT"))

SECRET_KEY = os.getenv("SECRET_KEY")

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "TelezonS3")

DATABASE_URL = os.getenv("DATABASE_URL", "")

TOKEN = os.getenv("BOT_TOKEN")
CID = os.getenv("CID")

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

INITIAL_ADMIN_USER = os.getenv("INITIAL_ADMIN_USER")
INITIAL_ADMIN_PASSWORD = os.getenv("INITIAL_ADMIN_PASSWORD")

# Upload / Telegram reliability (0.3)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
TG_RATE_LIMIT_PER_SEC = float(os.getenv("TG_RATE_LIMIT_PER_SEC", "20"))
TG_RATE_BURST = float(os.getenv("TG_RATE_BURST", "20"))
TG_RATE_WAIT_SECONDS = float(os.getenv("TG_RATE_WAIT_SECONDS", "30"))

# 0.5 large files / cache
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "")  # e.g. http://localhost:8081
CACHE_DIR = os.getenv("CACHE_DIR", "")
CACHE_MAX_BYTES = int(os.getenv("CACHE_MAX_BYTES", str(512 * 1024 * 1024)))
MULTIPART_MAX_PARTS = int(os.getenv("MULTIPART_MAX_PARTS", "10000"))
MULTIPART_MIN_PART_BYTES = int(os.getenv("MULTIPART_MIN_PART_BYTES", str(5 * 1024 * 1024)))

# 0.6
APP_LANG = os.getenv("APP_LANG", "en")
ENABLE_MGMT_BOT = os.getenv("ENABLE_MGMT_BOT", "0") == "1"
TELEGRAM_ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# Telegram outbound proxy, e.g. socks5://user:pass@127.0.0.1:1080
TELEGRAM_PROXY = parse_telegram_proxy(os.getenv("TELEGRAM_PROXY", ""))

# Background hygiene
ENABLE_GC = os.getenv("ENABLE_GC", "1") == "1"
GC_INTERVAL_SECONDS = int(os.getenv("GC_INTERVAL_SECONDS", "3600"))
GC_MULTIPART_MAX_AGE_SECONDS = int(
    os.getenv("GC_MULTIPART_MAX_AGE_SECONDS", str(24 * 3600))
)
GC_ORPHAN_SAMPLE_SIZE = int(os.getenv("GC_ORPHAN_SAMPLE_SIZE", "20"))

# Soft delete / trash
ENABLE_TRASH = os.getenv("ENABLE_TRASH", "1") == "1"
TRASH_RETENTION_SECONDS = int(
    os.getenv("TRASH_RETENTION_SECONDS", str(7 * 24 * 3600))
)

# Share password brute-force protection
SHARE_MAX_FAILED_ATTEMPTS = int(os.getenv("SHARE_MAX_FAILED_ATTEMPTS", "5"))
SHARE_LOCKOUT_SECONDS = int(os.getenv("SHARE_LOCKOUT_SECONDS", "900"))

# When 0, /api/health omits error detail strings (safer on public endpoints).
HEALTH_EXPOSE_ERRORS = os.getenv("HEALTH_EXPOSE_ERRORS", "1") == "1"
