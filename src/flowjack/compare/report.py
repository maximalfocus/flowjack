"""Render the comparison.

The table is the demonstration. Read two columns together — *seats to the operator* and
*individually invalid requests* — and the whole risk class is on one line: an actor took everything
there was, and did not send a single bad request to do it.
"""

from __future__ import annotations

from collections.abc import Sequence

from flowjack.compare.engine import ComparisonRow
from flowjack.config import SHOW_ID, VENUE_NAME
from flowjack.harness.records import Actor, Step

#: Stated once, at the end of every comparison. Held as a constant so the test suite can strip it
#: before checking that no performance claim appears anywhere else.
PERFORMANCE_DISCLAIMER = (
    "This comparison measures correctness of an outcome. It measures no throughput, no\n"
    "latency, and no capacity, and makes no performance claim of any kind."
)

_HEADERS = (
    "scenario",
    "control in force",
    "conc",
    "pace",
    "ids",
    "srcs",
    "statuses",
    "operator",
    "genuine",
    "demand",
    "invalid",
    "verdict",
)


def render(rows: Sequence[ComparisonRow], *, verbose: bool = False) -> str:
    lines = [
        f"flowjack — scenario comparison ({VENUE_NAME}, {SHOW_ID})",
        "=" * 78,
        "",
        *_narrative(rows),
        "",
        *_table(rows),
        "",
        *_closing(rows),
    ]
    if verbose:
        for row in rows:
            lines += ["", *_detail(row)]
    lines += ["", PERFORMANCE_DISCLAIMER, ""]
    return "\n".join(lines)


def _narrative(rows: Sequence[ComparisonRow]) -> list[str]:
    allocation = rows[0].ledger.seats_allocated if rows else 0
    drained = [row for row in rows if not row.secure]
    return [
        f"A fictional venue puts {allocation} seats on public sale. Forty patrons want two each.",
        "One automated operator runs the same booking flow the patrons do.",
        "",
        f"{len(rows)} scenarios below. In {len(drained)} of them the operator takes the entire",
        "allocation and the patrons get nothing. In every one of those, the count of requests",
        "that were individually invalid is zero: there was no bad request to find, so no",
        "request-level control could have found one.",
    ]


def _table(rows: Sequence[ComparisonRow]) -> list[str]:
    body = [
        (
            row.target.scenario,
            row.target.control,
            str(row.target.config.concurrency),
            f"{row.target.config.pace_seconds:g}s",
            str(row.ledger.operator_identities),
            str(len(row.ledger.requests_by_source)),
            _statuses(row),
            f"{row.ledger.operator_seats}/{row.ledger.seats_allocated}",
            str(row.ledger.genuine_seats),
            f"{row.ledger.demand_served}/{row.ledger.demand_offered}",
            str(row.ledger.invalid_requests),
            "SECURE" if row.secure else "VULNERABLE",
        )
        for row in rows
    ]
    widths = [
        max(len(_HEADERS[column]), *(len(record[column]) for record in body))
        for column in range(len(_HEADERS))
    ]
    rule = "-+-".join("-" * width for width in widths)
    out = [" | ".join(head.ljust(width) for head, width in zip(_HEADERS, widths, strict=True))]
    out.append(rule)
    for record in body:
        out.append(
            " | ".join(cell.ljust(width) for cell, width in zip(record, widths, strict=True))
        )
    return out


def _statuses(row: ComparisonRow) -> str:
    return " ".join(
        f"{status}x{count}" for status, count in sorted(row.ledger.status_distribution.items())
    )


def _closing(rows: Sequence[ComparisonRow]) -> list[str]:
    lines = ["reading the table", "-" * 17]
    for row in rows:
        ledger = row.ledger
        if row.secure:
            note = (
                f"held the operator to {ledger.operator_seats} of {ledger.seats_allocated} "
                f"and served all {ledger.demand_offered} seats of genuine demand"
            )
        elif row.target.negative_control:
            note = (
                f"one identity, one source, {row.target.config.concurrency} request at a time, "
                f"paced under the enforced limit which refused {ledger.rate_limited_requests} "
                f"— and still {ledger.operator_seats} of {ledger.seats_allocated} seats. "
                "Not a race; throttling only changed how long it took"
            )
        elif ledger.seats_confirmed == 0:
            note = "denied every seat without selling a single ticket"
        elif ledger.challenges_passed:
            note = (
                f"{ledger.challenges_passed} verification challenge passed, legitimately, "
                f"then {ledger.operator_seats} seats taken unchallenged"
            )
        elif ledger.rate_limited_requests == 0 and ledger.max_seats_per_identity <= 2:
            note = (
                f"no identity exceeded its {ledger.max_seats_per_identity}-seat quota; "
                f"{ledger.operator_identities} identities were brought instead"
            )
        elif ledger.rate_limited_requests == 0 and row.target.config.pace_seconds:
            note = "stayed under the enforced rate limit throughout — the limiter refused nothing"
        else:
            note = f"took {ledger.operator_seats} of {ledger.seats_allocated} seats"
        prefix = "  NEGATIVE CONTROL " if row.target.negative_control else "  "
        lines.append(f"{prefix}{row.target.scenario}: {note}.")

    lines += [
        "",
        "  Every row above reports 0 individually invalid requests. That is the finding, not",
        "  a coincidence: this risk class is made entirely of requests the API is designed",
        "  to accept. The negative control settles the other common misreading — concurrency",
        "  1, one identity, one source, deliberately under the limit, and the allocation",
        "  still goes. Nothing here is simultaneous, so this is not a race; see `racejack`",
        "  (CWE-367) for that one.",
    ]
    return lines


def _detail(row: ComparisonRow) -> list[str]:
    lines = [
        f"per-request detail — {row.target.scenario}",
        "-" * (21 + len(row.target.scenario)),
        f"  {'actor':<9}{'identity':<20}{'source':<20}{'step':<9}{'status':<7}outcome",
    ]
    lines += [
        f"  {r.actor.value:<9}{r.identity:<20}{r.source_label:<20}"
        f"{r.step.value:<9}{r.status:<7}{r.outcome.value}"
        for r in row.records
    ]
    lines += ["", f"flow timeline by identity — {row.target.scenario}", "-" * 40]
    for identity in _identities(row):
        steps = [r for r in row.records if r.identity == identity]
        rendered = " -> ".join(
            f"{r.step.value}:{'ok' if r.status in (200, 201) else r.status}" for r in steps[:12]
        )
        more = "" if len(steps) <= 12 else f" ... (+{len(steps) - 12} more)"
        lines.append(f"  {identity:<20} {rendered}{more}")
    return lines


def _identities(row: ComparisonRow) -> list[str]:
    seen: list[str] = []
    for record in row.records:
        if record.actor is Actor.OPERATOR and record.identity not in seen:
            seen.append(record.identity)
    for record in row.records:
        if record.actor is Actor.GENUINE and record.step is Step.HOLD:
            if record.identity not in seen:
                seen.append(record.identity)
            if len(seen) > 12:
                break
    return seen[:12]
