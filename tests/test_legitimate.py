"""Legitimate behaviour is preserved.

A flow limit that stops the attack by refusing genuine use has failed twice over. The household
patron carries a documented higher entitlement and must complete an ordinary booking.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from flowjack.config import SHOW_ID, Settings
from flowjack.db import GENUINE_PATRON_COUNT, HOUSEHOLD_PATRON_ID
from flowjack.errors import REFUSAL_STATUS

from .conftest import auth


def _book(client: TestClient, patron: str, seats: int) -> list[int]:
    statuses: list[int] = []
    for _ in range(seats):
        hold = client.post(f"/shows/{SHOW_ID}/holds", headers=auth(patron))
        if hold.status_code != 201:
            statuses.append(hold.status_code)
            continue
        confirmed = client.post(f"/holds/{hold.json()['hold_id']}/confirm", headers=auth(patron))
        statuses.append(confirmed.status_code)
    return statuses


def test_an_ordinary_two_seat_booking_succeeds(client: TestClient) -> None:
    assert _book(client, "PATRON-001", 2) == [201, 201]


def test_the_household_patron_books_four_seats(client: TestClient) -> None:
    assert _book(client, HOUSEHOLD_PATRON_ID, 4) == [201, 201, 201, 201]


def test_the_household_patrons_fifth_seat_is_refused(client: TestClient) -> None:
    _book(client, HOUSEHOLD_PATRON_ID, 4)
    fifth = client.post(f"/shows/{SHOW_ID}/holds", headers=auth(HOUSEHOLD_PATRON_ID))
    assert fifth.status_code == REFUSAL_STATUS


def test_the_full_genuine_demand_is_served(client: TestClient) -> None:
    """Forty genuine patrons wanting two seats each are all served in full."""
    for index in range(1, GENUINE_PATRON_COUNT + 1):
        assert _book(client, f"PATRON-{index:03d}", 2) == [201, 201]

    show = client.get(f"/shows/{SHOW_ID}").json()
    assert show["seats_confirmed"] == GENUINE_PATRON_COUNT * Settings().seat_quota_default == 80
    assert show["seats_available"] == show["seats_allocated"] - 80


def test_the_show_reports_its_own_allocation(client: TestClient) -> None:
    settings = Settings()
    show = client.get(f"/shows/{SHOW_ID}").json()
    assert show["seats_allocated"] == settings.seats_allocated
    assert show["seats_available"] == settings.seats_allocated
    assert show["venue"] == "Alder Hall"

    _book(client, "PATRON-001", 2)
    after = client.get(f"/shows/{SHOW_ID}").json()
    assert after["seats_confirmed"] == 2
    assert after["seats_available"] == settings.seats_allocated - 2


def test_allocation_reconciles_holds_and_tickets(client: TestClient) -> None:
    client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
    _book(client, "PATRON-002", 2)

    allocation = client.get(f"/shows/{SHOW_ID}/allocation").json()
    holdings = {row["patron_id"]: row for row in allocation["holdings"]}
    assert holdings["PATRON-001"]["seats_held"] == 1
    assert holdings["PATRON-002"]["seats_confirmed"] == 2
    assert (
        allocation["seats_held"] + allocation["seats_confirmed"] + allocation["seats_available"]
        == allocation["seats_allocated"]
    )
