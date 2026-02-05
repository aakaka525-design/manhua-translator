from __future__ import annotations

import asyncio
import time


class RequestRateLimiter:
    """Simple async pace limiter based on requests-per-second."""

    def __init__(self, rate_limit_rps: float) -> None:
        self._rate_limit_rps = max(float(rate_limit_rps), 0.001)
        self._interval_sec = 1.0 / self._rate_limit_rps
        self._next_allowed_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait_sec = self._next_allowed_at - now
            if wait_sec > 0:
                await asyncio.sleep(wait_sec)
                now = time.monotonic()
            self._next_allowed_at = max(self._next_allowed_at, now) + self._interval_sec
