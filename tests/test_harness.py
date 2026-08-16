"""The harness, driven directly — no terminal-input simulation anywhere.

Every assertion here is an exact count. Nothing is a rate, a probability, or a tolerance, because
nothing in this demonstration depends on timing or interleaving.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from flowjack.config import Settings
from flowjack.harness import (
    VERDICT_ABSENT,
    VERDICT_HELD,
    Actor,
    HarnessConfig,
    Outcome,
    Step,
    run_harness,
)
from flowjack.harness.fixtures import (
    GENUINE_SOURCE_PREFIX,
    OPERATOR_SOURCE_LABELS,
    SOURCE_HEADER,
)
from flowjack.harness.transcript import PERFORMANCE_DISCLAIMER, render

from .conftest import AppFactory

SMALL = HarnessConfig(operator_identities=10, genuine_patrons=5, concurrency=4)


def test_the_operator_is_held_to_its_documented_ceiling(client: TestClient) -> None:
    settings = Settings()
    result = run_harness(client, HarnessConfig(), settings)
    ledger = result.require_ledger()

    assert ledger.operator_seats == settings.operator_seat_ceiling == 6
    assert ledger.operator_identities == settings.self_service_registration_cap == 3


def test_the_full_genuine_demand_is_served(client: TestClient) -> None:
    ledger = run_harness(client, HarnessConfig()).require_ledger()

    assert ledger.demand_offered == 80
    assert ledger.demand_served == 80
    assert ledger.genuine_seats == 80
    assert ledger.genuine_identities == 40


def test_the_verdict_is_flow_limit_held(client: TestClient) -> None:
    assert run_harness(client, HarnessConfig()).require_ledger().verdict == VERDICT_HELD


def test_the_ledger_reconciles_against_the_venues_own_report(client: TestClient) -> None:
    ledger = run_harness(client, HarnessConfig()).require_ledger()

    assert ledger.seats_allocated == 120
    assert ledger.seats_held + ledger.seats_confirmed + ledger.seats_available == 120
    assert ledger.operator_seats + ledger.genuine_seats == (
        ledger.seats_held + ledger.seats_confirmed
    )
    assert ledger.seats_available == 120 - 6 - 80


def test_counts_are_identical_across_two_consecutive_runs(make_client: AppFactory) -> None:
    """No assertion in this project is a rate, a probability, or a tolerance."""

    def counts() -> tuple[int, ...]:
        with make_client() as instance:
            ledger = run_harness(instance, HarnessConfig()).require_ledger()
            return (
                ledger.operator_seats,
                ledger.genuine_seats,
                ledger.operator_identities,
                ledger.genuine_identities,
                ledger.demand_served,
                ledger.requests_issued,
                ledger.invalid_requests,
                ledger.seats_available,
            )

    assert counts() == counts()


def test_concurrency_does_not_change_any_count(make_client: AppFactory) -> None:
    """Concurrency shortens the run. It is not part of the mechanism."""

    def counts(concurrency: int) -> tuple[int, ...]:
        with make_client() as instance:
            ledger = run_harness(
                instance, replace(HarnessConfig(), concurrency=concurrency)
            ).require_ledger()
            return (
                ledger.operator_seats,
                ledger.genuine_seats,
                ledger.demand_served,
                ledger.requests_issued,
                ledger.seats_available,
            )

    assert counts(1) == counts(8)


def test_every_request_the_harness_issues_is_individually_valid(client: TestClient) -> None:
    """The defining property of this class: refusals happen, invalid requests do not."""
    result = run_harness(client, HarnessConfig())

    assert result.require_ledger().invalid_requests == 0
    assert all(not record.individually_invalid for record in result.records)
    assert {record.outcome for record in result.records} <= {
        Outcome.GRANTED,
        Outcome.REFUSED_BY_FLOW_LIMIT,
    }


def test_records_carry_identity_source_step_status_and_outcome(client: TestClient) -> None:
    records = run_harness(client, SMALL).records
    assert records

    for record in records:
        assert record.identity
        assert record.source_label
        assert record.step in set(Step)
        assert record.status > 0
        assert record.outcome in set(Outcome)

    operator_sources = {r.source_label for r in records if r.actor is Actor.OPERATOR}
    assert operator_sources <= set(OPERATOR_SOURCE_LABELS)
    genuine_sources = {r.source_label for r in records if r.actor is Actor.GENUINE}
    assert genuine_sources
    assert all(label.startswith(GENUINE_SOURCE_PREFIX) for label in genuine_sources)
    # One label per patron: forty people on forty connections, not a crowd behind one address.
    assert len(genuine_sources) == len({r.identity for r in records if r.actor is Actor.GENUINE})


def test_the_operator_distributes_across_every_source_label(client: TestClient) -> None:
    records = run_harness(client, HarnessConfig()).records
    used = {r.source_label for r in records if r.actor is Actor.OPERATOR}
    assert used == set(OPERATOR_SOURCE_LABELS)


def test_the_source_label_reaches_the_application_as_a_header(client: TestClient) -> None:
    """The header stands in for a network origin, so no address machinery is needed."""
    response = client.post(
        "/patrons",
        json={"display_name": "Demo", "eligibility_ref": "NOPE"},
        headers={SOURCE_HEADER: "src-alpha"},
    )
    # Nothing consumes it yet; it must simply be accepted and ignored.
    assert response.status_code == 409


def test_the_status_distribution_covers_every_request(client: TestClient) -> None:
    result = run_harness(client, SMALL)
    ledger = result.require_ledger()
    assert sum(ledger.status_distribution.values()) == ledger.requests_issued
    assert ledger.requests_issued == len(result.records)


def test_an_absent_flow_limit_would_be_reported_as_such(client: TestClient) -> None:
    """The verdict is a real test, not a constant: an unbounded operator flips it."""
    result = run_harness(client, HarnessConfig())
    ledger = replace(result.require_ledger(), operator_seats=120, genuine_seats=0, demand_served=0)
    assert ledger.verdict == VERDICT_ABSENT
    assert ledger.conclusion.startswith("VULNERABLE")


def test_the_transcript_is_human_readable_and_leaks_nothing(client: TestClient) -> None:
    config = HarnessConfig()
    result = run_harness(client, config)
    text = render(result, config, verbose=True)

    assert "allocation ledger" in text
    assert "VERDICT" in text
    assert VERDICT_HELD in text
    assert "seats to the AUTOMATED actor" in text
    assert "individually INVALID       : 0" in text
    assert PERFORMANCE_DISCLAIMER in text

    assert "flowjack-demo-token" not in text
    assert "Bearer" not in text

    # Outside the disclaimer that denies them, none of these words may appear at all — the
    # transcript must not slip into reporting a rate, a duration, or a benchmark.
    body = text.replace(PERFORMANCE_DISCLAIMER, "").lower()
    for forbidden in ("throughput", "latency", "benchmark", "per second", "elapsed", "ms)"):
        assert forbidden not in body
