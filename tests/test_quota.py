"""Strategy A — the outcome quota on the business flow."""

from __future__ import annotations

from fastapi.testclient import TestClient
from httpx2 import Response

from flowjack.clock import FakeClock
from flowjack.config import SHOW_ID
from flowjack.errors import REFUSAL_DETAIL, REFUSAL_STATUS

from .conftest import AppFactory, auth


def _hold(client: TestClient, patron: str) -> Response:
    return client.post(f"/shows/{SHOW_ID}/holds", headers=auth(patron))


def test_third_seat_against_a_two_seat_entitlement_is_refused(client: TestClient) -> None:
    assert _hold(client, "PATRON-001").status_code == 201
    assert _hold(client, "PATRON-001").status_code == 201

    third = _hold(client, "PATRON-001")
    assert third.status_code == REFUSAL_STATUS
    assert third.json() == {"detail": REFUSAL_DETAIL}


def test_an_outstanding_hold_costs_the_same_as_a_confirmed_ticket(
    client: TestClient,
) -> None:
    first = _hold(client, "PATRON-002")
    assert (
        client.post(
            f"/holds/{first.json()['hold_id']}/confirm", headers=auth("PATRON-002")
        ).status_code
        == 201
    )

    # One ticket + one outstanding hold exhausts a two-seat entitlement.
    assert _hold(client, "PATRON-002").status_code == 201
    assert _hold(client, "PATRON-002").status_code == REFUSAL_STATUS


def test_two_unconfirmed_holds_alone_exhaust_the_entitlement(client: TestClient) -> None:
    assert _hold(client, "PATRON-003").status_code == 201
    assert _hold(client, "PATRON-003").status_code == 201
    assert _hold(client, "PATRON-003").status_code == REFUSAL_STATUS


def test_the_quota_counts_seats_not_requests(client: TestClient) -> None:
    """Refused attempts do not themselves consume anything; the limit is an outcome limit."""
    for _ in range(10):
        _hold(client, "PATRON-004")

    allocation = client.get(f"/shows/{SHOW_ID}/allocation").json()
    holdings = {row["patron_id"]: row for row in allocation["holdings"]}
    assert holdings["PATRON-004"]["seats_held"] == 2


def test_expiry_returns_entitlement_only_within_the_rehold_allowance(
    client: TestClient, clock: FakeClock
) -> None:
    patron = "PATRON-005"
    cycles = 0
    for _ in range(5):
        if _hold(client, patron).status_code != 201:
            break
        cycles += 1
        clock.advance(601.0)  # past the default hold window

    # allowance 1 forgives the first lapse; the third lapse leaves the entitlement spent.
    assert cycles == 3
    assert _hold(client, patron).status_code == REFUSAL_STATUS


def test_expired_holds_return_their_seat_to_the_pool(client: TestClient, clock: FakeClock) -> None:
    before = client.get(f"/shows/{SHOW_ID}").json()["seats_available"]
    _hold(client, "PATRON-006")
    during = client.get(f"/shows/{SHOW_ID}").json()["seats_available"]
    clock.advance(601.0)
    after = client.get(f"/shows/{SHOW_ID}").json()["seats_available"]

    assert during == before - 1
    assert after == before


def test_sold_out_is_the_same_generic_refusal(make_client: AppFactory) -> None:
    with make_client(seats_allocated=2) as client:
        assert _hold(client, "PATRON-001").status_code == 201
        assert _hold(client, "PATRON-002").status_code == 201

        sold_out = _hold(client, "PATRON-003")
        assert sold_out.status_code == REFUSAL_STATUS
        assert sold_out.json() == {"detail": REFUSAL_DETAIL}
