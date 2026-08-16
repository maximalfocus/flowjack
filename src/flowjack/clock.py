"""Injectable clock.

Hold expiry is the one behaviour in this demo that depends on time passing. Injecting the clock
keeps the in-process tests instant and exactly reproducible, while the containerised walkthrough
runs on the real clock with a deliberately short hold window.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Seconds since the epoch."""


class SystemClock:
    """Real time. Used by the running application."""

    def now(self) -> float:
        return time.time()


class FakeClock:
    """Controllable time. Used by tests so no test ever sleeps.

    Guarded by a lock because the harness paces from several threads at once, and a lost update
    here would make time appear to stand still — which would change results rather than merely
    slow them.
    """

    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self._now = start
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._now += seconds
