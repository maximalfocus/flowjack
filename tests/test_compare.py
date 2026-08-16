"""The comparison, driven directly — no terminal-input simulation anywhere."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from flowjack.app import create_app
from flowjack.clock import FakeClock
from flowjack.compare import (
    DEFAULT_TARGETS,
    ComparisonRow,
    ComparisonTarget,
    render,
    run_comparison,
)
from flowjack.compare.report import PERFORMANCE_DISCLAIMER
from flowjack.config import Settings
from flowjack.db import Database
from flowjack.harness.engine import Client
from flowjack.policy import (
    SECURE,
    VULNERABLE_FRONT_DOOR_GATE,
    VULNERABLE_NONE,
    VULNERABLE_PER_ACCOUNT_QUOTA,
    VULNERABLE_PER_SOURCE_RATE_LIMIT,
    Policy,
)

#: Which policy each comparison row's application enforces, keyed by Compose service name.
_POLICY_BY_SERVICE: dict[str, Policy] = {
    "secure-app-harness": SECURE,
    "vulnerable-app": VULNERABLE_NONE,
    "vulnerable-app-abandon": VULNERABLE_NONE,
    "vulnerable-app-rate-limit": VULNERABLE_PER_SOURCE_RATE_LIMIT,
    "vulnerable-app-quota": VULNERABLE_PER_ACCOUNT_QUOTA,
    "vulnerable-app-gate": VULNERABLE_FRONT_DOOR_GATE,
    "vulnerable-app-sequential": VULNERABLE_PER_SOURCE_RATE_LIMIT,
}


@pytest.fixture(scope="module")
def rows() -> Iterator[list[ComparisonRow]]:
    """Run the whole comparison in process, once for this module, one application per row."""
    clock = FakeClock()
    databases: list[Database] = []
    opened: list[TestClient] = []

    def open_client(target: ComparisonTarget) -> Client:
        settings = Settings()
        database = Database(settings, clock)
        databases.append(database)
        app = create_app(
            settings=settings,
            clock=clock,
            database=database,
            policy=_POLICY_BY_SERVICE[target.service],
        )
        instance = TestClient(app, base_url="http://flowjack.test")
        opened.append(instance)
        return instance

    yield list(run_comparison(open_client, DEFAULT_TARGETS, sleep=clock.advance))
    for instance in opened:
        instance.close()
    for database in databases:
        database.close()


def test_every_target_has_its_own_application_and_policy() -> None:
    assert {target.service for target in DEFAULT_TARGETS} == set(_POLICY_BY_SERVICE)
    assert len({target.service for target in DEFAULT_TARGETS}) == len(DEFAULT_TARGETS)


def test_the_comparison_covers_the_whole_scenario_set(rows: list[ComparisonRow]) -> None:
    assert len(rows) == len(DEFAULT_TARGETS) == 7
    assert {row.target.scenario for row in rows} == {t.scenario for t in DEFAULT_TARGETS}


def test_exactly_one_row_is_secure(rows: list[ComparisonRow]) -> None:
    secure = [row for row in rows if row.secure]
    assert len(secure) == 1
    assert secure[0].target.scenario == "secure-baseline"


def test_every_vulnerable_row_loses_the_whole_allocation(rows: list[ComparisonRow]) -> None:
    for row in rows:
        if row.secure:
            continue
        assert row.ledger.operator_seats == 120, row.target.scenario
        assert row.ledger.demand_served == 0, row.target.scenario


def test_every_row_reports_zero_invalid_requests(rows: list[ComparisonRow]) -> None:
    """The finding, stated once across the whole comparison."""
    for row in rows:
        assert row.ledger.invalid_requests == 0, row.target.scenario
        assert row.validity.valid_percentage == 100.0, row.target.scenario


def test_the_secure_row_serves_the_full_genuine_demand(rows: list[ComparisonRow]) -> None:
    secure = next(row for row in rows if row.secure)
    assert secure.ledger.demand_served == secure.ledger.demand_offered == 80
    assert secure.ledger.operator_seats == 6


def test_the_table_shows_every_required_column(rows: list[ComparisonRow]) -> None:
    text = render(rows)
    for header in (
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
    ):
        assert header in text
    assert "SECURE" in text
    assert "VULNERABLE" in text


def test_the_table_names_the_control_in_force_for_each_row(rows: list[ComparisonRow]) -> None:
    text = render(rows)
    for expected in (
        "all three flow limits",
        "per-source rate limit",
        "per-account quota (2 seats)",
        "verification gate at the front door",
    ):
        assert expected in text


def test_the_narrative_states_the_finding(rows: list[ComparisonRow]) -> None:
    text = render(rows)
    assert "no bad request to find" in text
    assert "not a race" in text
    assert "racejack" in text
    assert "makes no performance claim" in text


def test_the_closing_notes_explain_each_row(rows: list[ComparisonRow]) -> None:
    text = render(rows)
    assert "without selling a single ticket" in text
    assert "verification challenge passed, legitimately" in text
    assert "identities were brought instead" in text
    assert "NEGATIVE CONTROL" in text


def test_verbose_adds_per_request_records_and_a_flow_timeline(rows: list[ComparisonRow]) -> None:
    plain = render(rows)
    detailed = render(rows, verbose=True)

    assert "per-request detail" not in plain
    assert "flow timeline by identity" not in plain
    assert "per-request detail" in detailed
    assert "flow timeline by identity" in detailed
    assert len(detailed) > len(plain)


def test_the_report_leaks_no_token_or_secret(rows: list[ComparisonRow]) -> None:
    text = render(rows, verbose=True)
    assert "flowjack-demo-token" not in text
    assert "Bearer" not in text
    assert "verify-0" not in text


def test_the_report_makes_no_performance_claim(rows: list[ComparisonRow]) -> None:
    text = render(rows, verbose=True)
    assert PERFORMANCE_DISCLAIMER in text

    body = text.replace(PERFORMANCE_DISCLAIMER, "").lower()
    for forbidden in ("throughput", "latency", "benchmark", "per second", "elapsed"):
        assert forbidden not in body


def test_the_engine_needs_no_terminal_input(rows: list[ComparisonRow]) -> None:
    """Every assertion above ran the engine as a plain callable. This states it explicitly."""
    assert rows
    assert all(row.records for row in rows)
