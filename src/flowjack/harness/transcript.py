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

    if verbose:
        lines.extend(["", "per-request records", "-" * 19])
        lines.extend(
            f"  {r.actor.value:<8} {r.identity:<20} {r.source_label:<12} "
            f"{r.step.value:<8} {r.status:<4} {r.outcome.value}"
            for r in result.records
        )

    lines.extend(["", PERFORMANCE_DISCLAIMER, ""])
    return "\n".join(lines)


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
