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
)

SCENARIOS: dict[str, HarnessConfig] = {
    "secure-baseline": SECURE_BASELINE,
    "no-anti-automation": NO_ANTI_AUTOMATION,
    "abandoned-holds": ABANDONED_HOLDS,
}
