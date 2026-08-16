"""The run transcript.

A human-readable record of what the harness did and what the venue had left afterwards. It carries
identities, source labels, steps, statuses, and outcomes — and no token, secret, or personal datum,
because bearer tokens never leave the engine and every name in the fixtures is conspicuously
fictional.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from flowjack.config import SHOW_ID, VENUE_NAME
from flowjack.harness.engine import HarnessConfig, HarnessResult
from flowjack.harness.records import Actor, RequestRecord
from flowjack.harness.validity import replay

#: Stated once, at the end of every transcript. Held as a constant so the test suite can strip it
#: before checking that no performance claim appears anywhere else.
PERFORMANCE_DISCLAIMER = (
    "This harness generates volume to expose a design defect. It measures no throughput,\n"
    "no latency, and no capacity, and makes no performance claim of any kind."
)


def render(result: HarnessResult, config: HarnessConfig, *, verbose: bool = False) -> str:
    ledger = result.require_ledger()
    lines = [
        f"flowjack — business-flow automation harness ({VENUE_NAME}, {SHOW_ID})",
        "=" * 72,
        "",
        "run parameters (volume, pace, and concurrency are parameters — not the mechanism)",
        f"  operator identities attempted : {config.operator_identities}",
        f"  seats attempted per identity  : {config.operator_seats_per_identity}",
        f"  source labels distributed over: {len(config.source_labels)}",
        f"  genuine patrons               : {config.genuine_patrons}"
        f" x {config.genuine_seats_each} seats",
        f"  concurrency                   : {config.concurrency}",
        f"  pace between requests         : {config.pace_seconds}s",
        "",
        "requests by actor and step",
    ]
    lines.extend(_by_actor(result.records))
    lines.extend(["", ledger.render()])
    lines.extend(["", replay(result.records).render()])
    lines.extend(["", *_notes(result, config)])

    if verbose:
        lines.extend(["", "per-request records", "-" * 19])
        lines.extend(
            f"  {r.actor.value:<8} {r.identity:<20} {r.source_label:<12} "
            f"{r.step.value:<8} {r.status:<4} {r.outcome.value}"
            for r in result.records
        )

    lines.extend(["", PERFORMANCE_DISCLAIMER, ""])
    return "\n".join(lines)


def _notes(result: HarnessResult, config: HarnessConfig) -> list[str]:
    """What this particular run does and does not establish."""
    ledger = result.require_ledger()
    lines = ["what this run does and does not show", "-" * 36]

    if config.concurrency == 1:
        lines += [
            "  Concurrency 1. Every request was issued one at a time, in order, with",
            f"  {config.pace_seconds}s between each. Nothing here is simultaneous, so this is",
            "  NOT a race condition, and no interleaving is involved anywhere. The series'",
            "  demonstration of the concurrency defect this class is mistaken for is",
            "  `racejack` (CWE-367).",
        ]
    else:
        lines += [
            f"  Concurrency {config.concurrency} shortened this run and did nothing else. The same",
            "  counts arrive at concurrency 1 — the slow-and-sequential scenario proves it.",
        ]

    if ledger.rate_limited_requests == 0 and config.pace_seconds:
        lines += [
            "  The operator stayed deliberately UNDER the enforced request rate limit throughout:",
            "  the limiter refused nothing at all. Throttling changed how long the harm took, and",
            "  nothing else. Reducing the rate of a flow is not a limit on its outcome.",
        ]

    if ledger.challenges_passed:
        lines += [
            f"  {ledger.challenges_passed} verification challenge(s) passed, legitimately, against"
            f" {ledger.operator_seats} seats obtained.",
            "  Nothing was defeated, solved, replayed, or machine-answered. A gate prices",
            "  entry; it says nothing about how much flow one entry may go on to consume.",
        ]

    if ledger.max_seats_per_identity <= 2 and ledger.operator_identities > 1:
        lines += [
            f"  No identity exceeded its {ledger.max_seats_per_identity}-seat quota. The quota was",
            "  correct and was never violated. It was keyed on an identity that cost nothing,",
            f"  so {ledger.operator_identities} of them were brought.",
        ]

    return lines


def _by_actor(records: Sequence[RequestRecord]) -> list[str]:
    lines: list[str] = []
    for actor in (Actor.OPERATOR, Actor.GENUINE):
        subset = [record for record in records if record.actor is actor]
        if not subset:
            continue
        lines.append(f"  {actor.value}:")
        grouped = Counter((record.step.value, record.outcome.value) for record in subset)
        for (step, outcome), count in sorted(grouped.items()):
            lines.append(f"    {step:<9} {outcome:<24} {count}")
    return lines
