"""Upgrade Agent - Rate Limiter for Gemini API"""

import time
from datetime import datetime
from threading import Lock
from typing import Optional

from .constants import MAX_LLM_CALLS_PER_DAY, RPM_LIMIT


class RateLimiter:
    """Token bucket rate limiter for Gemini API."""

    def __init__(self, rpm: int = RPM_LIMIT, max_daily: int = MAX_LLM_CALLS_PER_DAY):
        self.rpm = rpm
        self.max_daily = max_daily
        self.requests: list[float] = []
        self.daily_count = 0
        self.last_reset = datetime.now()
        self.lock = Lock()
        self.backoff_until: Optional[float] = None

    def acquire(self) -> bool:
        """Acquire permission to make a request."""
        with self.lock:
            now = time.time()

            # Check if in backoff period
            if self.backoff_until and now < self.backoff_until:
                return False

            # Reset daily counter if needed
            if (now - self.last_reset.timestamp()) > 86400:  # 24 hours
                self.daily_count = 0
                self.last_reset = datetime.now()
                self.requests.clear()

            # Check daily limit
            if self.daily_count >= self.max_daily:
                return False

            # Clean old requests (older than 1 minute)
            self.requests = [ts for ts in self.requests if now - ts < 60]

            # Check RPM limit
            if len(self.requests) >= self.rpm:
                return False

            # Allow request
            self.requests.append(now)
            self.daily_count += 1
            return True

    def wait_and_acquire(self, timeout: int = 60) -> bool:
        """Wait for permission to make a request."""
        start = time.time()
        while time.time() - start < timeout:
            if self.acquire():
                return True
            # Exponential backoff
            time.sleep(min(2 ** (len(self.requests) + 1), 30))
        return False

    def report_rate_limit_error(self):
        """Called when a 429 error is received."""
        with self.lock:
            self.backoff_until = time.time() + 60  # 1 minute backoff

    def report_success(self):
        """Called when a request succeeds."""
        with self.lock:
            self.backoff_until = None

    def get_status(self) -> dict:
        """Get current rate limit status."""
        with self.lock:
            now = time.time()
            recent_requests = len([ts for ts in self.requests if now - ts < 60])
            return {
                "rpm_used": recent_requests,
                "rpm_limit": self.rpm,
                "daily_used": self.daily_count,
                "daily_limit": self.max_daily,
                "in_backoff": self.backoff_until is not None
                and now < self.backoff_until,
            }


# Global rate limiter instance
rate_limiter = RateLimiter()
