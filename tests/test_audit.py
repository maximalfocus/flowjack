"""The rejection audit event: exactly one per refusal, and incurious."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from flowjack.audit import ALLOWED_FIELDS, EVENT_NAME
from flowjack.config import SHOW_ID
from flowjack.db import ELIGIBILITY_REFS

from .conftest import auth


def _events(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    captured = capsys.readouterr().out
    return [
        json.loads(line)
        for line in captured.splitlines()
        if line.startswith("{") and EVENT_NAME in line
    ]


def test_exactly_one_event_per_refusal(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
    client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
    capsys.readouterr()

    client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
    assert len(_events(capsys)) == 1


def test_a_successful_request_emits_no_event(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    assert client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001")).status_code == 201
    assert _events(capsys) == []


def test_an_authentication_failure_emits_no_flow_limit_event(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    client.post(f"/shows/{SHOW_ID}/holds")
    assert _events(capsys) == []


def test_the_event_carries_only_permitted_fields(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    client.post("/patrons", json={"display_name": "Demo", "eligibility_ref": "NOPE"})

    events = _events(capsys)
    assert len(events) == 1
    assert set(events[0]) == ALLOWED_FIELDS
    assert events[0]["outcome"] == "refused"
    assert events[0]["step"] == "register"


def test_the_event_is_correlatable(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    response = client.post("/holds/HOLD-999999/confirm", headers=auth("PATRON-001"))

    events = _events(capsys)
    assert events[0]["request_id"] == response.headers["X-Request-Id"]


def test_the_event_discloses_no_stock_headroom_or_ceiling(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    for _ in range(3):
        client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
    for ref in [*ELIGIBILITY_REFS, "UNKNOWN"]:
        client.post("/patrons", json={"display_name": "Demo", "eligibility_ref": ref})

    forbidden = {
        "seats_available",
        "seats_remaining",
        "quota",
        "headroom",
        "entitlement",
        "cap",
        "ceiling",
        "reason",
        "limit",
    }
    for event in _events(capsys):
        assert not forbidden & set(event)


def test_no_token_or_secret_reaches_the_event(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    client.post("/holds/HOLD-999999/confirm", headers=auth("PATRON-001"))

    for event in _events(capsys):
        assert "flowjack-demo-token" not in json.dumps(event)
