"""Run every scenario and collect one row each.

Like the harness engine, this is a plain callable over an injected client factory, so the test
suite drives it directly and never simulates terminal input.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from flowjack.config import Settings
from flowjack.harness.engine import Client, HarnessConfig, run_harness
from flowjack.harness.ledger import Ledger
from flowjack.harness.records import RequestRecord
from flowjack.harness.scenarios import SCENARIOS
from flowjack.harness.validity import ValidityReport, replay


@dataclass(frozen=True, slots=True)
class ComparisonTarget:
    """One row of the comparison: a scenario, and the application it runs against."""

    scenario: str
    #: The policy the target application enforces, as the run should label it.
    control: str
    #: Compose service name for the application serving this row.
    service: str
    #: Shown in the narrative when a row is a boundary rather than a shape.
    negative_control: bool = False

    @property
    def config(self) -> HarnessConfig:
        return SCENARIOS[self.scenario]


#: The full set, in the order the walkthrough tells it: the reference, then the ladder, then the
#: boundary that marks what this flaw is not.
DEFAULT_TARGETS: tuple[ComparisonTarget, ...] = (
    ComparisonTarget("secure-baseline", "all three flow limits", "secure-app-harness"),
    ComparisonTarget("no-anti-automation", "none", "vulnerable-app"),
    ComparisonTarget("abandoned-holds", "none (holds abandoned)", "vulnerable-app-abandon"),
    ComparisonTarget("per-source-rate-limit", "per-source rate limit", "vulnerable-app-rate-limit"),
    ComparisonTarget("per-account-quota", "per-account quota (2 seats)", "vulnerable-app-quota"),
    ComparisonTarget(
        "front-door-gate", "verification gate at the front door", "vulnerable-app-gate"
    ),
    ComparisonTarget(
        "slow-and-sequential",
        "per-source rate limit, stayed under",
        "vulnerable-app-sequential",
        negative_control=True,
    ),
)


@dataclass(frozen=True, slots=True)
class ComparisonRow:
    target: ComparisonTarget
    ledger: Ledger
    validity: ValidityReport
    records: list[RequestRecord]

    @property
    def verdict(self) -> str:
        return self.ledger.verdict

    @property
    def secure(self) -> bool:
        return self.ledger.verdict == "flow limit held"


def run_comparison(
    open_client: Callable[[ComparisonTarget], Client],
    targets: tuple[ComparisonTarget, ...] = DEFAULT_TARGETS,
    settings: Settings | None = None,
    sleep: Callable[[float], None] | None = None,
) -> list[ComparisonRow]:
    """Run each target's scenario against its own application and collect the rows."""
    resolved_settings = settings if settings is not None else Settings()
    rows: list[ComparisonRow] = []
    for target in targets:
        client = open_client(target)
        result = run_harness(client, target.config, resolved_settings, sleep=sleep)
        rows.append(
            ComparisonRow(
                target=target,
                ledger=result.require_ledger(),
                validity=replay(result.records),
                records=result.records,
            )
        )
    return rows
