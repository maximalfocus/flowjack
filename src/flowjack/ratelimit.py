"""A per-source request rate limiter.

This is **not** one of the flow limits. It is here so the demonstration can show a genuinely
enforced, correctly implemented rate limit holding perfectly — never once exceeded — while the
venue's entire allocation drains past it.

The limiter counts *requests per source*. The business cares about *outcomes per person*. Those are
different quantities, and the attacker picks the source.

It is a real sliding-window limiter, not a stub: point enough traffic at a single source and it
refuses, which the regression suite asserts. The demonstration's operator simply never does that.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Final

#: Distinct from the flow-limit refusal. A rate limit is a conventional, advertised control, and
#: this status is what a caller would expect from one.
RATE_LIMIT_STATUS: Final = 429
RATE_LIMIT_DETAIL: Final = "Too many requests from this source."


class SourceRateLimiter:
    """Sliding-window request counting, keyed on a source label."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._lock = threading.Lock()
        self._seen: defaultdict[str, deque[float]] = defaultdict(deque)

    def allow(self, source: str, *, now: float) -> bool:
        """Record a request from ``source`` and report whether it is within the limit."""
        with self._lock:
            window = self._seen[source]
            cutoff = now - self._window
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= self._limit:
                return False
            window.append(now)
            return True

    def counts(self, *, now: float) -> dict[str, int]:
        """Current in-window request count per source, for the run's output."""
        with self._lock:
            cutoff = now - self._window
            return {
                source: sum(1 for stamp in window if stamp > cutoff)
                for source, window in self._seen.items()
                if window
            }

    @property
    def limit(self) -> int:
        return self._limit
