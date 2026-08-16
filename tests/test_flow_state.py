"""Strategy C — flow-scoped enforcement.

A control that guards the step a client happens to call first is not a control on the flow.
These tests pin the four ways a caller can try to arrive somewhere it did not walk to.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from flowjack.clock import FakeClock
from flowjack.config import SHOW_ID
from flowjack.errors import REFUSAL_DETAIL, REFUSAL_STATUS

from .conftest import auth


def _hold(client: TestClient, patron: str) -> str:
    response = client.post(f"/shows/{SHOW_ID}/holds", headers=auth(patron))
    assert response.status_code == 201
    return str(response.json()["hold_id"])


def test_the_ordinary_two_step_flow_succeeds(client: TestClient) -> None:
    hold_id = _hold(client, "PATRON-001")
    confirmed = client.post(f"/holds/{hold_id}/confirm", headers=auth("PATRON-001"))
    assert confirmed.status_code == 201
    assert confirmed.json()["hold_id"] == hold_id


def test_entering_the_flow_at_the_confirmation_step_is_refused(
    client: TestClient,
) -> None:
    response = client.post("/holds/HOLD-999999/confirm", headers=auth("PATRON-001"))
    assert response.status_code == REFUSAL_STATUS
    assert response.json() == {"detail": REFUSAL_DETAIL}


def test_confirming_another_identitys_flow_is_refused(client: TestClient) -> None:
    hold_id = _hold(client, "PATRON-001")
    response = client.post(f"/holds/{hold_id}/confirm", headers=auth("PATRON-002"))
    assert response.status_code == REFUSAL_STATUS


def test_replaying_a_finished_flow_is_refused(client: TestClient) -> None:
    hold_id = _hold(client, "PATRON-001")
    assert client.post(f"/holds/{hold_id}/confirm", headers=auth("PATRON-001")).status_code == 201

    replay = client.post(f"/holds/{hold_id}/confirm", headers=auth("PATRON-001"))
    assert replay.status_code == REFUSAL_STATUS


def test_confirming_a_lapsed_hold_is_refused(client: TestClient, clock: FakeClock) -> None:
    hold_id = _hold(client, "PATRON-001")
    clock.advance(601.0)

    response = client.post(f"/holds/{hold_id}/confirm", headers=auth("PATRON-001"))
    assert response.status_code == REFUSAL_STATUS


def test_a_refused_confirmation_creates_no_ticket(client: TestClient) -> None:
    hold_id = _hold(client, "PATRON-001")
    client.post(f"/holds/{hold_id}/confirm", headers=auth("PATRON-002"))

    allocation = client.get(f"/shows/{SHOW_ID}/allocation").json()
    assert allocation["seats_confirmed"] == 0
    holdings = {row["patron_id"]: row for row in allocation["holdings"]}
    assert "PATRON-002" not in holdings
