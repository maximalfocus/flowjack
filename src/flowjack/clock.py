"""Injectable clock.

Hold expiry is the one behaviour in this demo that depends on time passing. Injecting the clock
keeps the in-process tests instant and exactly reproducible, while the containerised walkthrough
runs on the real clock with a deliberately short hold window.
"""

from __future__ import annotations

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
    """Controllable time. Used by tests so no test ever sleeps."""

    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds
