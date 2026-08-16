"""No refusal tells the caller which limit it hit.

A caller that can distinguish "sold out" from "your entitlement is used" can probe the venue's
remaining stock, or map exactly where a limit sits, without being entitled to either fact.
"""

from __future__ import annotations

from httpx2 import Response

from flowjack.config import SHOW_ID
from flowjack.db import ELIGIBILITY_REFS
from flowjack.errors import REFUSAL_DETAIL, REFUSAL_STATUS

from .conftest import AppFactory, auth


def _signature(response: Response) -> tuple[int, str]:
    return response.status_code, response.text


def test_every_refusal_shape_is_byte_identical(make_client: AppFactory) -> None:
    with make_client(seats_allocated=2) as client:
        # entitlement used
        client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
        client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
        entitlement_used = client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))

        # sold out — a different patron, with entitlement to spare, finds no seat
        sold_out = client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-002"))

        # flow not entered
        flow_not_entered = client.post("/holds/HOLD-999999/confirm", headers=auth("PATRON-003"))

        # somebody else's flow
        others_flow = client.post("/holds/HOLD-000001/confirm", headers=auth("PATRON-004"))

        # identity supply reached
        for ref in ELIGIBILITY_REFS[:3]:
            client.post("/patrons", json={"display_name": "Demo", "eligibility_ref": ref})
        identity_supply = client.post(
            "/patrons",
            json={"display_name": "Demo", "eligibility_ref": ELIGIBILITY_REFS[3]},
        )

        shapes = [
            entitlement_used,
            sold_out,
            flow_not_entered,
            others_flow,
            identity_supply,
        ]
        assert all(r.status_code == REFUSAL_STATUS for r in shapes)
        assert all(r.json() == {"detail": REFUSAL_DETAIL} for r in shapes)
        assert len({_signature(r) for r in shapes}) == 1


def test_refusal_headers_carry_no_distinguishing_signal(make_client: AppFactory) -> None:
    with make_client(seats_allocated=2) as client:
        client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
        client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
        entitlement_used = client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
        sold_out = client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-002"))

    volatile = {"x-request-id", "date", "content-length"}
    left = {k.lower(): v for k, v in entitlement_used.headers.items() if k.lower() not in volatile}
    right = {k.lower(): v for k, v in sold_out.headers.items() if k.lower() not in volatile}
    assert left == right
