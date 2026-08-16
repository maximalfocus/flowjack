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
    """

    name: str
    seat_quota: bool = False
    governed_identity_supply: bool = False
    flow_state: bool = False

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

POLICIES: dict[str, Policy] = {policy.name: policy for policy in (SECURE, VULNERABLE_NONE)}
