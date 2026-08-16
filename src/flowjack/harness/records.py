"""Per-request records.

One record per request the harness issues, classified by what the application did with it. The
classification carries the demonstration's central claim: a request that a *flow limit* refused is
not the same thing as a request that was *invalid*, and this project's whole point is that the
attack contains none of the latter.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Actor(StrEnum):
    OPERATOR = "operator"
    GENUINE = "genuine"


class Step(StrEnum):
    REGISTER = "register"
    HOLD = "hold"
    CONFIRM = "confirm"


class Outcome(StrEnum):
    #: The application did the thing that was asked.
    GRANTED = "granted"
    #: A flow limit declined it. The request itself was perfectly well formed.
    REFUSED_BY_FLOW_LIMIT = "refused_by_flow_limit"
    #: Authentication failed — an individually invalid request.
    UNAUTHENTICATED = "unauthenticated"
    #: The body or route was wrong — an individually invalid request.
    MALFORMED = "malformed"
    #: Anything else. Also counted as individually invalid, so a surprise cannot hide.
    UNEXPECTED = "unexpected"


#: Outcomes that mean the request was wrong on its own terms, independent of any limit.
INDIVIDUALLY_INVALID = frozenset({Outcome.UNAUTHENTICATED, Outcome.MALFORMED, Outcome.UNEXPECTED})


@dataclass(frozen=True, slots=True)
class RequestRecord:
    actor: Actor
    identity: str
    source_label: str
    step: Step
    status: int
    outcome: Outcome

    @property
    def individually_invalid(self) -> bool:
        return self.outcome in INDIVIDUALLY_INVALID


def classify(status: int, *, refusal_status: int) -> Outcome:
    if status in (200, 201):
        return Outcome.GRANTED
    if status == refusal_status:
        return Outcome.REFUSED_BY_FLOW_LIMIT
    if status == 401:
        return Outcome.UNAUTHENTICATED
    if status in (400, 404, 422):
        return Outcome.MALFORMED
    return Outcome.UNEXPECTED
