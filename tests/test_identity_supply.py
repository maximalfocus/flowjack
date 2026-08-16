"""Strategy B — governed identity supply.

A quota keyed on an identity is only as strong as the cost of obtaining that identity. These
tests pin that cost: registration consumes a single-use eligibility reference *and* counts against
a documented cap.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from httpx2 import Response

from flowjack.config import SHOW_ID, Settings
from flowjack.db import ELIGIBILITY_REFS
from flowjack.errors import REFUSAL_DETAIL, REFUSAL_STATUS

from .conftest import AppFactory


def _register(client: TestClient, ref: str, name: str = "Demo Operator") -> Response:
    return client.post("/patrons", json={"display_name": name, "eligibility_ref": ref})


def test_registration_with_a_valid_reference_succeeds(client: TestClient) -> None:
    response = _register(client, ELIGIBILITY_REFS[0])
    assert response.status_code == 201
    body = response.json()
    assert body["seat_entitlement"] == Settings().seat_quota_default
    assert body["token"].startswith("flowjack-demo-token-")


def test_an_unknown_eligibility_reference_is_refused(client: TestClient) -> None:
    response = _register(client, "NOT-A-REAL-REFERENCE")
    assert response.status_code == REFUSAL_STATUS
    assert response.json() == {"detail": REFUSAL_DETAIL}


def test_a_spent_eligibility_reference_cannot_be_reused(client: TestClient) -> None:
    assert _register(client, ELIGIBILITY_REFS[0]).status_code == 201
    assert _register(client, ELIGIBILITY_REFS[0]).status_code == REFUSAL_STATUS


def test_registration_stops_at_the_documented_cap(client: TestClient) -> None:
    granted = [_register(client, ref) for ref in ELIGIBILITY_REFS[:3]]
    assert all(response.status_code == 201 for response in granted)

    # A fourth, still-unconsumed reference does not help: the cap is a separate limit.
    over_cap = _register(client, ELIGIBILITY_REFS[3])
    assert over_cap.status_code == REFUSAL_STATUS
    assert over_cap.json() == {"detail": REFUSAL_DETAIL}


def test_a_registered_patron_can_use_the_flow_within_its_own_quota(
    client: TestClient,
) -> None:
    token = _register(client, ELIGIBILITY_REFS[0]).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.post(f"/shows/{SHOW_ID}/holds", headers=headers).status_code == 201
    assert client.post(f"/shows/{SHOW_ID}/holds", headers=headers).status_code == 201
    assert client.post(f"/shows/{SHOW_ID}/holds", headers=headers).status_code == REFUSAL_STATUS


def test_governed_identity_supply_bounds_the_reachable_seat_ceiling(
    make_client: AppFactory,
) -> None:
    """The honest outcome: an operator is limited, not eliminated."""
    settings = Settings()
    with make_client() as client:
        obtained = 0
        for ref in ELIGIBILITY_REFS:
            registration = _register(client, ref)
            if registration.status_code != 201:
                continue
            headers = {"Authorization": f"Bearer {registration.json()['token']}"}
            while client.post(f"/shows/{SHOW_ID}/holds", headers=headers).status_code == 201:
                obtained += 1

        assert obtained == settings.operator_seat_ceiling == 6
