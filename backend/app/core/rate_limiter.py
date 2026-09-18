import time
import threading
from typing import Dict, List
from fastapi import Request, HTTPException, status
from app.core.config import settings


class InMemoryRateLimiter:
    """
    Sliding window in-memory rate limiter.
    Tracks client request timestamps and enforces rate limits per IP/client key.
    Thread-safe with periodic eviction of stale timestamps.
    """

    def __init__(self, requests_limit: int = 60, window_seconds: int = 60):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self._records: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def is_rate_limited(self, client_key: str) -> tuple[bool, int]:
        """
        Returns (is_limited, retry_after_seconds).
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._records.get(client_key, [])
            # Filter out timestamps older than the sliding window
            timestamps = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= self.requests_limit:
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + self.window_seconds - now))
                self._records[client_key] = timestamps
                return True, retry_after

            timestamps.append(now)
            self._records[client_key] = timestamps
            return False, 0

    def check(self, request: Request):
        # Determine client identifier: X-Forwarded-For or client.host
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        elif request.client:
            client_ip = request.client.host
        else:
            client_ip = "127.0.0.1"

        is_limited, retry_after = self.is_rate_limited(client_ip)
        if is_limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )


# Default rate limiters for general API and LLM endpoints
default_api_limiter = InMemoryRateLimiter(
    requests_limit=settings.RATE_LIMIT_PER_MINUTE,
    window_seconds=60
)

llm_api_limiter = InMemoryRateLimiter(
    requests_limit=settings.LLM_RATE_LIMIT_PER_MINUTE,
    window_seconds=60
)
