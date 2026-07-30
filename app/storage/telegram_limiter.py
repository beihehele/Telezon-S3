from app.core.config import TG_RATE_BURST, TG_RATE_LIMIT_PER_SEC
from app.storage.rate_limit import TokenBucket

# Shared across Account + Bot storage instances in-process.
telegram_rate_limiter = TokenBucket(TG_RATE_LIMIT_PER_SEC, TG_RATE_BURST)
