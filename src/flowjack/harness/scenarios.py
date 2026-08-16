"""Named harness runs, shared by the CLI and the regression suite.

Each scenario is a set of run parameters, not a different harness. The same engine drives all of
them; what changes is which application it points at and how the operator behaves.
"""

from __future__ import annotations

from flowjack.harness.engine import HarnessConfig, Mode

#: The secure reference: the operator does its worst against every limit being in force.
SECURE_BASELINE = HarnessConfig()

#: `FR-012`. One identity, running the flow 120 times, against an application with no
#: anti-automation at all. Every response is a success.
NO_ANTI_AUTOMATION = HarnessConfig(
    operator_identities=1,
    operator_seats_per_identity=120,
)

#: `FR-013`. The same single identity holds every seat and never confirms one, re-holding as each
#: hold lapses. The allocation is denied just as completely, with no ticket sold and no payment
#: taken — so there is nothing for a fraud control to look at.
ABANDONED_HOLDS = HarnessConfig(
    mode=Mode.ABANDON,
    operator_identities=1,
    operator_seats_per_identity=120,
    abandon_rounds=2,
    # Long enough to outlast the demo's compressed hold window; tests override it and advance a
    # fake clock instead, so nothing sleeps in the suite.
    abandon_wait_seconds=4.0,
)

#: `FR-014`. Eight identities across the eight fixed source labels, paced so no source ever exceeds
#: the enforced limit. The limit holds perfectly; the allocation drains anyway.
PER_SOURCE_RATE_LIMIT = HarnessConfig(
    operator_identities=8,
    operator_seats_per_identity=15,
    concurrency=8,
    pace_seconds=0.12,
)

#: `FR-015`. Sixty manufactured identities taking exactly the two seats each is entitled to. Every
#: quota check passes; not one is violated; the allocation is gone.
PER_ACCOUNT_QUOTA = HarnessConfig(
    operator_identities=60,
    operator_seats_per_identity=2,
)

#: `FR-016`. One challenge, paid legitimately, then 120 unchallenged requests.
FRONT_DOOR_GATE = HarnessConfig(
    operator_identities=1,
    operator_seats_per_identity=120,
    pass_verification=True,
)

#: `FR-017`. The negative control. Concurrency 1, paced deliberately below the enforced rate limit,
#: one identity, one source — and the entire allocation, just more slowly. Nothing here is
#: simultaneous; this is not a race.
SLOW_AND_SEQUENTIAL = HarnessConfig(
    operator_identities=1,
    operator_seats_per_identity=120,
    concurrency=1,
    pace_seconds=0.12,
)

SCENARIOS: dict[str, HarnessConfig] = {
    "secure-baseline": SECURE_BASELINE,
    "no-anti-automation": NO_ANTI_AUTOMATION,
    "abandoned-holds": ABANDONED_HOLDS,
    "per-source-rate-limit": PER_SOURCE_RATE_LIMIT,
    "per-account-quota": PER_ACCOUNT_QUOTA,
    "front-door-gate": FRONT_DOOR_GATE,
    "slow-and-sequential": SLOW_AND_SEQUENTIAL,
}
