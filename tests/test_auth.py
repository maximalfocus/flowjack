"""Authentication is correct in flowjack, and tells the caller nothing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from flowjack.config import SHOW_ID
from flowjack.db import EXPIRED_TOKEN

from .conftest import auth

BAD_HEADERS: dict[str, dict[str, str]] = {
    "missing": {},
    "malformed-scheme": {"Authorization": "NotBearer x"},
    "malformed-empty": {"Authorization": "Bearer"},
    "malformed-prefix": {"Authorization": "Bearer not-a-flowjack-token"},
    "unknown": {"Authorization": "Bearer flowjack-demo-token-nobody"},
    "expired": {"Authorization": f"Bearer {EXPIRED_TOKEN}"},
}


@pytest.mark.parametrize("headers", list(BAD_HEADERS.values()), ids=list(BAD_HEADERS))
def test_every_authentication_failure_returns_generic_401(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post(f"/shows/{SHOW_ID}/holds", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication is required."}


def test_authentication_failures_are_byte_identical(client: TestClient) -> None:
    signatures = {
        (response.status_code, response.text)
        for response in (
            client.post(f"/shows/{SHOW_ID}/holds", headers=headers)
            for headers in BAD_HEADERS.values()
        )
    }
    assert len(signatures) == 1


def test_a_valid_demo_token_authenticates(client: TestClient) -> None:
    response = client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
    assert response.status_code == 201


def test_tokens_never_appear_in_a_success_payload(client: TestClient) -> None:
    response = client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
    assert "flowjack-demo-token" not in response.text
