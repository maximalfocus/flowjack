"""Which flow limits an application enforces.

One application, one policy. The secure variant switches every limit on; each vulnerable variant
switches some subset off. Keeping it a subset relation is the point: the ladder of controls that
*look* like fixes is then literally a diff of which limits are active, and the code says the thing
the walkthrough says.

Nothing here changes what a request looks like. Every variant exposes identical paths,
authentication, request bodies, and success payloads — they differ only in what they allow to
happen a great many times.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Policy:
    """The flow limits in force.

    ``seat_quota``
        Strategy A — an outcome quota counting seats per identity per show, charging outstanding
        holds exactly as confirmed tickets.
    ``governed_identity_supply``
        Strategy B — registration treated as a sensitive flow of its own, so the key the quota
        counts by is not free to manufacture.
    ``flow_state``
        Strategy C — server-side flow state re-checked at every step, so the flow cannot be
        entered part-way through.

    ``per_source_rate_limit`` / ``rate_limit_window_seconds``
        Not a flow limit at all — a *request* limit, included so the demonstration can show it
        holding perfectly while the allocation drains.
    ``verification_gate_steps``
        Steps that demand a human-verification token. Also not a flow limit: it prices entry, and
        prices it once.
    """

    name: str
    seat_quota: bool = False
    governed_identity_supply: bool = False
    flow_state: bool = False
    per_source_rate_limit: int | None = None
    rate_limit_window_seconds: float = 1.0
    verification_gate_steps: frozenset[str] = frozenset()

    @property
    def is_vulnerable(self) -> bool:
        return not (self.seat_quota and self.governed_identity_supply and self.flow_state)


#: Every limit on. This is the default application and the reference the contrast is drawn against.
SECURE = Policy(
    name="secure",
    seat_quota=True,
    governed_identity_supply=True,
    flow_state=True,
)

#: No anti-automation of any kind. Registration is unlimited and needs no eligibility reference,
#: no quota bounds any identity's share, and no server-side state records that a flow was entered.
#: Every individual request this application answers is still correct — which is the whole problem.
VULNERABLE_NONE = Policy(name="no-anti-automation")

#: A per-source request rate limit, genuinely enforced and never exceeded during the run — because
#: the operator distributes the identical flow across source labels it chooses. The limiter counts
#: requests per source; the business cares about outcomes per person.
#:
#: The window is deliberately short so the walkthrough fits its time budget, exactly as the hold
#: window is. The lesson is unchanged at ten per minute; it would simply take sixty times longer.
VULNERABLE_PER_SOURCE_RATE_LIMIT = Policy(
    name="per-source-rate-limit",
    per_source_rate_limit=10,
    rate_limit_window_seconds=1.0,
)

#: Strategy A present, strategy B absent — the demo's central shape. The quota is *correct*,
#: expressed in business terms, and is never violated. It is keyed on an identity that costs
#: nothing, so the operator simply brings more identities.
VULNERABLE_PER_ACCOUNT_QUOTA = Policy(name="per-account-quota", seat_quota=True)

#: A human-verification challenge at the point a new visitor arrives, with the whole
#: seat-allocation flow behind it ungated. Paid once, then out of the way.
VULNERABLE_FRONT_DOOR_GATE = Policy(
    name="front-door-gate",
    verification_gate_steps=frozenset({"register"}),
)

VULNERABLE_POLICIES: tuple[Policy, ...] = (
    VULNERABLE_NONE,
    VULNERABLE_PER_SOURCE_RATE_LIMIT,
    VULNERABLE_PER_ACCOUNT_QUOTA,
    VULNERABLE_FRONT_DOOR_GATE,
)

POLICIES: dict[str, Policy] = {policy.name: policy for policy in (SECURE, *VULNERABLE_POLICIES)}
