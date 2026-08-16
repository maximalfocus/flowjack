"""The allocation ledger and the flow-limit verdict.

The ledger answers the only question that matters for this class of defect: **who ended up with
the thing there was not enough of?** No individual request can answer it, which is why the run ends
here rather than in a per-request assertion.

The operator's share of the allocation is the headline figure, and the count of individually
invalid requests sits directly beside it — because a run in which the operator took everything
while issuing zero invalid requests is precisely the shape this project exists to make legible.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from flowjack.harness.records import Actor, Outcome, RequestRecord, Step

VERDICT_HELD = "flow limit held"
VERDICT_ABSENT = "flow limit absent"


@dataclass(frozen=True, slots=True)
class Ledger:
    seats_allocated: int
    seats_held: int
    seats_confirmed: int
    seats_available: int

    operator_seats: int
    genuine_seats: int
    operator_ceiling: int

    operator_identities: int
    genuine_identities: int

    demand_offered: int
    demand_served: int

    requests_issued: int
    status_distribution: dict[int, int]
    invalid_requests: int

    @property
    def verdict(self) -> str:
        bounded = self.operator_seats <= self.operator_ceiling
        served = self.demand_served >= self.demand_offered
        return VERDICT_HELD if bounded and served else VERDICT_ABSENT

    @property
    def conclusion(self) -> str:
        if self.verdict == VERDICT_HELD:
            return (
                "SECURE — the flow limited the operator to its documented ceiling while every "
                "genuine patron was served in full."
            )
        return (
            "VULNERABLE — the flow placed no effective bound on the operator's share of the "
            "allocation. Note the invalid-request count: there was no bad request to find."
        )

    def render(self) -> str:
        share = (self.operator_seats / self.seats_allocated * 100) if self.seats_allocated else 0.0
        statuses = "  ".join(
            f"{status}x{count}" for status, count in sorted(self.status_distribution.items())
        )
        return "\n".join(
            [
                "allocation ledger",
                "-----------------",
                f"  seats allocated              : {self.seats_allocated}",
                f"    held (unconfirmed)         : {self.seats_held}",
                f"    confirmed                  : {self.seats_confirmed}",
                f"    still available            : {self.seats_available}",
                "",
                f"  seats to the AUTOMATED actor : {self.operator_seats}"
                f"  ({share:.1f}% of the allocation)",
                f"    its documented ceiling     : {self.operator_ceiling}",
                f"    identities it used         : {self.operator_identities}",
                "",
                f"  seats to GENUINE patrons     : {self.genuine_seats}",
                f"    identities served          : {self.genuine_identities}",
                f"    demand offered vs served   : {self.demand_offered} vs {self.demand_served}",
                "",
                f"  requests issued              : {self.requests_issued}",
                f"    status distribution        : {statuses}",
                f"    individually INVALID       : {self.invalid_requests}",
                "",
                f"  VERDICT                      : {self.verdict}",
                f"  {self.conclusion}",
            ]
        )


def build_ledger(
    *,
    records: Sequence[RequestRecord],
    allocation: dict[str, object],
    operator_ceiling: int,
    demand_offered: int,
) -> Ledger:
    """Reconcile per-request records against the venue's own report of its allocation."""
    holdings = allocation["holdings"]
    assert isinstance(holdings, list)

    operator_seats = 0
    genuine_seats = 0
    operator_identities = 0
    genuine_identities = 0
    for holding in holdings:
        seats = int(holding["seats_held"]) + int(holding["seats_confirmed"])
        if str(holding["created_via"]) == "self_service":
            operator_seats += seats
            operator_identities += 1
        else:
            genuine_seats += seats
            genuine_identities += 1

    # A genuine patron's demand is met when its confirmation is granted; registrations and holds
    # are steps toward that, not the outcome the venue promised anybody.
    demand_served = sum(
        1
        for record in records
        if record.actor is Actor.GENUINE
        and record.outcome is Outcome.GRANTED
        and record.step is Step.CONFIRM
    )

    return Ledger(
        seats_allocated=_as_int(allocation["seats_allocated"]),
        seats_held=_as_int(allocation["seats_held"]),
        seats_confirmed=_as_int(allocation["seats_confirmed"]),
        seats_available=_as_int(allocation["seats_available"]),
        operator_seats=operator_seats,
        genuine_seats=genuine_seats,
        operator_ceiling=operator_ceiling,
        operator_identities=operator_identities,
        genuine_identities=genuine_identities,
        demand_offered=demand_offered,
        demand_served=demand_served,
        requests_issued=len(records),
        status_distribution=dict(Counter(record.status for record in records)),
        invalid_requests=sum(1 for record in records if record.individually_invalid),
    )


def _as_int(value: object) -> int:
    """Coerce a value read back from the venue's own JSON, refusing anything unexpected."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"expected an integer from the allocation report, got {value!r}")
    return value
