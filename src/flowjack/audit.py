"""Generic rejection audit events.

Exactly one event is emitted per refused request, from the single exception handler in
:mod:`flowjack.app`. Centralising emission is what makes "exactly one event per refusal"
a property of the design rather than a discipline.

The event is deliberately incurious. It records that a request was refused, which step refused
it, and enough to correlate it with a client response — and nothing else. It carries no remaining
seat count, no quota headroom, no other patron's holdings, no identity-supply ceiling, and no
token, secret, or personal datum. A caller who could read the log must learn nothing from it that
the generic client response withholds.
"""

from __future__ import annotations

import json
import sys
from contextvars import ContextVar
from typing import Final, Literal, TextIO

RequestStep = Literal["register", "hold", "confirm"]

EVENT_NAME: Final = "flow_limit_refusal"

_request_id: ContextVar[str] = ContextVar("flowjack_request_id", default="unknown")

#: Fields the event is permitted to carry. Asserted by the test suite.
ALLOWED_FIELDS: Final = frozenset({"event", "request_id", "show_id", "step", "outcome", "patron"})


def set_request_id(request_id: str) -> None:
    _request_id.set(request_id)


def current_request_id() -> str:
    return _request_id.get()


def emit_refusal(
    *,
    step: RequestStep,
    show_id: str | None,
    patron_id: str | None,
    stream: TextIO | None = None,
) -> None:
    """Write one generic refusal event as a single JSON line."""
    event = {
        "event": EVENT_NAME,
        "request_id": current_request_id(),
        "show_id": show_id,
        "step": step,
        "outcome": "refused",
        "patron": patron_id,
    }
    target = stream if stream is not None else sys.stdout
    target.write(json.dumps(event, sort_keys=True) + "\n")
    target.flush()
