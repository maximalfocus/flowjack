"""The business-flow automation harness.

The unit of observation for `API6:2023` is not a request — it is the aggregate outcome of a flow
run many times. This package runs the flow, records every request, and reconciles what the venue
has left against who took it.
"""

from flowjack.harness.engine import HarnessConfig, HarnessResult, run_harness
from flowjack.harness.ledger import VERDICT_ABSENT, VERDICT_HELD, Ledger, build_ledger
from flowjack.harness.records import Actor, Outcome, RequestRecord, Step

__all__ = [
    "VERDICT_ABSENT",
    "VERDICT_HELD",
    "Actor",
    "HarnessConfig",
    "HarnessResult",
    "Ledger",
    "Outcome",
    "RequestRecord",
    "Step",
    "build_ledger",
    "run_harness",
]
