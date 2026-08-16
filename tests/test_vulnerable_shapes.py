"""The vulnerable shapes, and the containment that keeps them local.

Read the assertions together. Each of these runs drains a 120-seat public allocation, and each of
them does it with **zero** individually invalid requests. That pairing is the whole class: there is
no bad request to find, so no request-level control can find one.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from flowjack.clock import FakeClock
from flowjack.config import SHOW_ID
from flowjack.harness import VERDICT_ABSENT, VERDICT_HELD, Actor, Outcome, run_harness
from flowjack.harness.scenarios import ABANDONED_HOLDS, NO_ANTI_AUTOMATION, SECURE_BASELINE
from flowjack.policy import SECURE, VULNERABLE_NONE
from flowjack.vulnerable_app import (
    ACKNOWLEDGEMENT_ENV,
    VulnerableDemoNotAcknowledgedError,
    acknowledged,
    create_vulnerable_app,
)

from .conftest import AppFactory, auth


def test_one_identity_takes_the_entire_allocation(vulnerable_client: TestClient) -> None:
    """`FR-012` — no anti-automation at all."""
    result = run_harness(vulnerable_client, NO_ANTI_AUTOMATION)
    ledger = result.require_ledger()

    assert ledger.operator_seats == 120
    assert ledger.operator_identities == 1
    assert ledger.seats_confirmed == 120
    assert ledger.seats_available == 0
    assert ledger.verdict == VERDICT_ABSENT


def test_genuine_patrons_are_served_nothing(vulnerable_client: TestClient) -> None:
    ledger = run_harness(vulnerable_client, NO_ANTI_AUTOMATION).require_ledger()

    assert ledger.genuine_seats == 0
    assert ledger.genuine_identities == 0
    assert ledger.demand_offered == 80
    assert ledger.demand_served == 0


def test_every_request_in_the_attack_is_individually_valid(
    vulnerable_client: TestClient,
) -> None:
    """The defining property. There is no malicious request here to detect."""
    result = run_harness(vulnerable_client, NO_ANTI_AUTOMATION)

    assert result.require_ledger().invalid_requests == 0
    assert all(not record.individually_invalid for record in result.records)


def test_the_operators_requests_all_succeed(vulnerable_client: TestClient) -> None:
    result = run_harness(vulnerable_client, NO_ANTI_AUTOMATION)
    operator = [record for record in result.records if record.actor is Actor.OPERATOR]

    assert operator
    assert all(record.outcome is Outcome.GRANTED for record in operator)
    assert {record.status for record in operator} == {201}


def test_abandoned_holds_deny_the_allocation_without_selling_a_ticket(
    vulnerable_client: TestClient, clock: FakeClock
) -> None:
    """`FR-013` — harm with no completed transaction anywhere."""
    ledger = run_harness(
        vulnerable_client,
        replace(ABANDONED_HOLDS, abandon_wait_seconds=601.0),
        sleep=clock.advance,
    ).require_ledger()

    assert ledger.seats_confirmed == 0
    assert ledger.seats_held == 120
    assert ledger.seats_available == 0
    assert ledger.operator_seats == 120
    assert ledger.genuine_seats == 0
    assert ledger.demand_served == 0
    assert ledger.invalid_requests == 0
    assert ledger.verdict == VERDICT_ABSENT


def test_abandoned_holds_survive_expiry_by_re_holding(
    vulnerable_client: TestClient, clock: FakeClock
) -> None:
    """Letting a hold lapse buys the venue nothing when the operator simply holds again."""
    result = run_harness(
        vulnerable_client,
        replace(ABANDONED_HOLDS, abandon_wait_seconds=601.0),
        sleep=clock.advance,
    )
    holds = [record for record in result.records if record.step.value == "hold"]

    # Two full rounds of 120, all granted: the first lapsed, the second replaced it.
    assert sum(1 for record in holds if record.outcome is Outcome.GRANTED) == 240
    assert not [record for record in result.records if record.step.value == "confirm"]


def test_the_secure_application_survives_the_same_runs(client: TestClient) -> None:
    """The identical scenario against every limit in force."""
    ledger = run_harness(client, NO_ANTI_AUTOMATION).require_ledger()

    assert ledger.operator_seats == 2  # one identity, one quota
    assert ledger.demand_served == 80
    assert ledger.verdict == VERDICT_HELD


def test_the_secure_baseline_is_unchanged_by_the_policy_refactor(client: TestClient) -> None:
    ledger = run_harness(client, SECURE_BASELINE).require_ledger()

    assert ledger.operator_seats == 6
    assert ledger.operator_identities == 3
    assert ledger.demand_served == 80
    assert ledger.invalid_requests == 0
    assert ledger.verdict == VERDICT_HELD


def test_the_vulnerable_policy_has_no_limits_and_the_secure_one_has_all_three() -> None:
    assert VULNERABLE_NONE.is_vulnerable
    assert not VULNERABLE_NONE.seat_quota
    assert not VULNERABLE_NONE.governed_identity_supply
    assert not VULNERABLE_NONE.flow_state

    assert not SECURE.is_vulnerable
    assert SECURE.seat_quota
    assert SECURE.governed_identity_supply
    assert SECURE.flow_state


def test_registration_needs_no_eligibility_reference_when_supply_is_ungoverned(
    vulnerable_client: TestClient,
) -> None:
    """Identities are free, so a quota keyed on them is worth what they cost."""
    for _ in range(25):
        response = vulnerable_client.post("/patrons", json={"display_name": "Demo Operator"})
        assert response.status_code == 201


def test_the_flow_can_be_entered_at_the_confirmation_step(
    vulnerable_client: TestClient,
) -> None:
    """Without server-side flow state, somebody else's hold is as good as your own."""
    hold = vulnerable_client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
    assert hold.status_code == 201

    stolen = vulnerable_client.post(
        f"/holds/{hold.json()['hold_id']}/confirm", headers=auth("PATRON-002")
    )
    assert stolen.status_code == 201


def test_authentication_is_still_correct_in_the_vulnerable_variant(
    vulnerable_client: TestClient,
) -> None:
    """Authentication is not what is broken here, in any variant."""
    assert vulnerable_client.post(f"/shows/{SHOW_ID}/holds").status_code == 401
    assert (
        vulnerable_client.post(
            f"/shows/{SHOW_ID}/holds", headers={"Authorization": "Bearer nope"}
        ).status_code
        == 401
    )


def test_the_vulnerable_entry_point_refuses_without_the_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ACKNOWLEDGEMENT_ENV, raising=False)
    assert not acknowledged()

    with pytest.raises(VulnerableDemoNotAcknowledgedError) as raised:
        create_vulnerable_app()
    assert ACKNOWLEDGEMENT_ENV in str(raised.value)
    assert "must never be deployed" in str(raised.value)


@pytest.mark.parametrize("value", ["", "false", "0", "yes", "TRUE ", " true"])
def test_only_an_exact_acknowledgement_starts_the_vulnerable_entry_point(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(ACKNOWLEDGEMENT_ENV, value)
    if value.strip().lower() == "true":
        assert acknowledged()
    else:
        assert not acknowledged()
        with pytest.raises(VulnerableDemoNotAcknowledgedError):
            create_vulnerable_app()


def test_the_acknowledged_entry_point_builds_a_vulnerable_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ACKNOWLEDGEMENT_ENV, "true")
    app = create_vulnerable_app()
    assert app.state.policy is VULNERABLE_NONE
    assert app.state.policy.is_vulnerable


def test_the_secure_and_vulnerable_variants_expose_identical_success_payloads(
    client: TestClient, vulnerable_client: TestClient
) -> None:
    """Both variants answer a legitimate request the same way. Only the limits differ."""
    secure_hold = client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
    vulnerable_hold = vulnerable_client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))

    assert secure_hold.status_code == vulnerable_hold.status_code == 201
    assert set(secure_hold.json()) == set(vulnerable_hold.json())
    assert secure_hold.json()["seat_id"] == vulnerable_hold.json()["seat_id"]


def test_a_vulnerable_app_is_constructible_for_tests_without_the_env_gate(
    make_client: AppFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate belongs to the deployable entry point, not the library."""
    monkeypatch.delenv(ACKNOWLEDGEMENT_ENV, raising=False)
    with make_client(policy=VULNERABLE_NONE) as instance:
        assert (
            instance.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001")).status_code == 201
        )
