import asyncio
import time


class TokenBucket:
    def __init__(self, rate_per_sec: float, burst: float):
        self.rate_per_sec = max(rate_per_sec, 0.1)
        self.burst = max(burst, 1.0)
        self.tokens = self.burst
        self.updated_at = time.monotonic()
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.updated_at
        self.updated_at = now
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate_per_sec)

    async def acquire(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(timeout_seconds, 0.0)
        async with self._condition:
            while True:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    self._condition.notify()
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                wait = min((1.0 - self.tokens) / self.rate_per_sec, remaining)
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=wait)
                except TimeoutError:
                    continue
