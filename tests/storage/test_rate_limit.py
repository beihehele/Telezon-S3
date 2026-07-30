import asyncio

import pytest

from app.storage.rate_limit import TokenBucket


@pytest.mark.asyncio
async def test_token_bucket_allows_burst_then_waits():
    bucket = TokenBucket(rate_per_sec=100.0, burst=2.0)
    assert await bucket.acquire(0.1) is True
    assert await bucket.acquire(0.1) is True
    # Third token should require refill; tiny timeout fails.
    assert await bucket.acquire(0.0) is False


@pytest.mark.asyncio
async def test_token_bucket_refills():
    bucket = TokenBucket(rate_per_sec=50.0, burst=1.0)
    assert await bucket.acquire(0.1) is True
    await asyncio.sleep(0.05)
    assert await bucket.acquire(0.2) is True
