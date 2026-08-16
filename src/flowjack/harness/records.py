"""Per-request records.

One record per request the harness issues, classified by what the application did with it. The
classification carries the demonstration's central claim: a request that a *flow limit* refused is
not the same thing as a request that was *invalid*, and this project's whole point is that the
attack contains none of the latter.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from flowjack.errors import VERIFICATION_REQUIRED_STATUS
from flowjack.ratelimit import RATE_LIMIT_STATUS


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
    #: A per-source *request* rate limit declined it. Also not an invalid request: the limiter
    #: refused it for arriving, not for being wrong.
    REFUSED_BY_RATE_LIMIT = "refused_by_rate_limit"
    #: A verification gate declined it for want of a token. This one *does* count as invalid: a
    #: required per-request credential was absent.
    REFUSED_BY_VERIFICATION = "refused_by_verification"
    #: Authentication failed — an individually invalid request.
    UNAUTHENTICATED = "unauthenticated"
    #: The body or route was wrong — an individually invalid request.
    MALFORMED = "malformed"
    #: Anything else. Also counted as individually invalid, so a surprise cannot hide.
    UNEXPECTED = "unexpected"


#: Outcomes that mean the request was wrong on its own terms, independent of any limit.
#:
#: A rate-limited request is deliberately **not** here. A rate limit is the closest thing to a
#: per-request control this demo contains, and even it does not say the request was bad — only that
#: it arrived. A missing verification token *is* here, because a required per-request credential was
#: absent; keeping it here is what stops the project's "100% of the attack was valid" claim from
#: being achieved by definition.
INDIVIDUALLY_INVALID = frozenset(
    {
        Outcome.UNAUTHENTICATED,
        Outcome.MALFORMED,
        Outcome.UNEXPECTED,
        Outcome.REFUSED_BY_VERIFICATION,
    }
)


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
    if status == RATE_LIMIT_STATUS:
        return Outcome.REFUSED_BY_RATE_LIMIT
    if status == VERIFICATION_REQUIRED_STATUS:
        return Outcome.REFUSED_BY_VERIFICATION
    if status == 401:
        return Outcome.UNAUTHENTICATED
    if status in (400, 404, 422):
        return Outcome.MALFORMED
    return Outcome.UNEXPECTED
