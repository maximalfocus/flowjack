"""The request-level validity replay.

This is the demonstration's sharpest negative control, and it needs saying carefully.

A request-level control — a WAF rule, a schema validator, an authorization check, a signature
verifier, an anomaly rule keyed on a single request — can only ever refuse a request for something
*about that request*. So the question worth asking about an attack is: how many of its requests
were wrong on their own terms?

This replays every record the harness captured and answers it. For an attack that drains a venue's
entire public allocation, the answer is **none**. Not a low number: none. Every request
authenticated, carried a well-formed body, addressed a real route, and was authorised to do exactly
what it did. There was nothing for a request-level control to key on, which is why one would not
have helped.

The check is deliberately conservative. A request refused for want of a verification token counts
as *invalid* here — a required per-request credential was absent — so the "100%" figure is never
reached by defining the problem away.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from flowjack.harness.records import INDIVIDUALLY_INVALID, Outcome, RequestRecord


@dataclass(frozen=True, slots=True)
class ValidityReport:
    total: int
    valid: int
    invalid: int
    invalid_by_outcome: dict[str, int]

    @property
    def valid_percentage(self) -> float:
        return 100.0 if self.total == 0 else (self.valid / self.total) * 100.0

    @property
    def all_valid(self) -> bool:
        return self.invalid == 0

    def render(self) -> str:
        verdict = (
            "every request in this run was individually valid — a request-level control had "
            "nothing to key on"
            if self.all_valid
            else "some requests were individually invalid"
        )
        lines = [
            "request-level validity replay",
            "-----------------------------",
            f"  requests replayed            : {self.total}",
            f"  individually VALID           : {self.valid}  ({self.valid_percentage:.1f}%)",
            f"  individually INVALID         : {self.invalid}",
        ]
        for outcome, count in sorted(self.invalid_by_outcome.items()):
            lines.append(f"    {outcome:<26} {count}")
        lines.append(f"  {verdict}")
        return "\n".join(lines)


def replay(records: Sequence[RequestRecord]) -> ValidityReport:
    """Check every captured request against the per-request rules that were in force."""
    invalid = [record for record in records if record.outcome in INDIVIDUALLY_INVALID]
    by_outcome: dict[str, int] = {}
    for record in invalid:
        by_outcome[record.outcome.value] = by_outcome.get(record.outcome.value, 0) + 1

    # A sanity assertion on the classification itself: nothing outside the known outcome set can
    # slip through as "valid" merely because it was unrecognised.
    assert all(record.outcome in set(Outcome) for record in records)

    return ValidityReport(
        total=len(records),
        valid=len(records) - len(invalid),
        invalid=len(invalid),
        invalid_by_outcome=by_outcome,
    )
