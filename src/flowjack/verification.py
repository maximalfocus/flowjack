"""A human-verification challenge, modelled at the front door.

**What this is not.** It is not a CAPTCHA, a proof of work, or a bot-detection system, and nothing
in this project attempts to defeat, solve, weaken, replay, or machine-answer one. Challenge strength
is deliberately out of scope, because it is irrelevant to the shape being demonstrated.

**What this is.** A stand-in for the cost a challenge imposes *once*, at the point a user interface
shows a new visitor something to prove they are human. The demo issues a single-use token on
request. In a real system, obtaining that token would cost a person a few seconds of attention.

The finding does not depend on how much it costs. Even a challenge nobody can beat, paid once,
buys every unchallenged request behind it — and in this venue that is the entire 120-seat
allocation. A gate prices *entry*. It says nothing about how much flow one entry may go on to
consume, and that is what a flow limit is for.
"""

from __future__ import annotations

import itertools
import threading
from typing import Final

VERIFICATION_HEADER: Final = "X-Human-Verification"


class VerificationChallenge:
    """Issues single-use verification tokens and spends them.

    Tokens are single-use so the demonstration can state without qualification that nothing was
    replayed: one challenge passed means one challenge passed.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        self._unspent: set[str] = set()
        self.issued = 0
        self.spent = 0

    def issue(self) -> str:
        with self._lock:
            token = f"verify-{next(self._counter):06d}"
            self._unspent.add(token)
            self.issued += 1
            return token

    def spend(self, token: str | None) -> bool:
        """Consume a token. Returns False for a missing, unknown, or already-spent token."""
        if token is None:
            return False
        with self._lock:
            if token not in self._unspent:
                return False
            self._unspent.discard(token)
            self.spent += 1
            return True
