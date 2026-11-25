"""Small in-process sliding-window rate limiter.

This app is a single-operator dashboard served by one process, so an in-process
limiter is proportionate. Counters reset on restart and are not shared between
workers; that trade-off is documented in the README.
"""

from __future__ import annotations

import threading
import time


class SlidingWindow:
    """Allow at most ``limit`` hits per ``window_seconds`` for a given key."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = max(1, int(limit))
        self.window = float(window_seconds)
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> int:
        """Record a hit.

        Returns 0 when the request may proceed, otherwise the number of seconds
        the caller should wait before a slot frees up.
        """
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 2048:
                self._prune(now)
            bucket = [stamp for stamp in self._hits.get(key, []) if now - stamp < self.window]
            if len(bucket) >= self.limit:
                self._hits[key] = bucket
                return max(1, int(self.window - (now - bucket[0])) + 1)
            bucket.append(now)
            self._hits[key] = bucket
            return 0

    def _prune(self, now: float) -> None:
        fresh: dict[str, list[float]] = {}
        for key, stamps in self._hits.items():
            kept = [stamp for stamp in stamps if now - stamp < self.window]
            if kept:
                fresh[key] = kept
        self._hits = fresh

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
