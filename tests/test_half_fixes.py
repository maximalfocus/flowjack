"""The three controls that look like fixes, and the two boundaries.

Every assertion here pairs a control that worked perfectly with an allocation that drained anyway.
That pairing is the demonstration: these are not broken controls, they are controls aimed at the
wrong quantity.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from flowjack.clock import FakeClock
from flowjack.config import SHOW_ID, Settings
from flowjack.errors import VERIFICATION_REQUIRED_STATUS
from flowjack.harness import VERDICT_ABSENT, VERDICT_HELD, Actor, Outcome, run_harness
from flowjack.harness.fixtures import OPERATOR_SOURCE_LABELS, SOURCE_HEADER
from flowjack.harness.scenarios import (
    FRONT_DOOR_GATE,
    PER_ACCOUNT_QUOTA,
    PER_SOURCE_RATE_LIMIT,
    SLOW_AND_SEQUENTIAL,
)
from flowjack.harness.validity import replay
from flowjack.policy import (
    VULNERABLE_FRONT_DOOR_GATE,
    VULNERABLE_PER_ACCOUNT_QUOTA,
    VULNERABLE_PER_SOURCE_RATE_LIMIT,
)
from flowjack.ratelimit import RATE_LIMIT_STATUS
from flowjack.verification import VERIFICATION_HEADER

from .conftest import AppFactory, auth

# Tests advance a fake clock instead of sleeping, so pacing is instant and exactly reproducible.
_PACE = 0.12


# --------------------------------------------------------------------------------------------
# FR-014 — a per-source rate limit, never exceeded, beside a drained allocation
# --------------------------------------------------------------------------------------------


def test_the_rate_limit_is_never_exceeded_while_the_allocation_drains(
    make_client: AppFactory, clock: FakeClock
) -> None:
    with make_client(policy=VULNERABLE_PER_SOURCE_RATE_LIMIT) as client:
        ledger = run_harness(client, PER_SOURCE_RATE_LIMIT, sleep=clock.advance).require_ledger()

    assert ledger.rate_limited_requests == 0, "the limit must hold perfectly"
    assert ledger.operator_seats == 120
    assert ledger.genuine_seats == 0
    assert ledger.demand_served == 0
    assert ledger.verdict == VERDICT_ABSENT


def test_the_operator_spreads_across_every_source_label(
    make_client: AppFactory, clock: FakeClock
) -> None:
    with make_client(policy=VULNERABLE_PER_SOURCE_RATE_LIMIT) as client:
        ledger = run_harness(client, PER_SOURCE_RATE_LIMIT, sleep=clock.advance).require_ledger()

    assert set(ledger.requests_by_source) == set(OPERATOR_SOURCE_LABELS)
    assert all(count > 0 for count in ledger.requests_by_source.values())


def test_the_limiter_is_genuinely_enforced_not_a_stub(make_client: AppFactory) -> None:
    """Point enough traffic at one source and it refuses. The operator simply never does."""
    limit = VULNERABLE_PER_SOURCE_RATE_LIMIT.per_source_rate_limit
    assert limit is not None

    with make_client(policy=VULNERABLE_PER_SOURCE_RATE_LIMIT) as client:
        headers = {**auth("PATRON-001"), SOURCE_HEADER: "src-alpha"}
        statuses = [
            client.post(f"/shows/{SHOW_ID}/holds", headers=headers).status_code
            for _ in range(limit + 5)
        ]

    assert statuses.count(RATE_LIMIT_STATUS) == 5
    assert statuses[:limit].count(RATE_LIMIT_STATUS) == 0


def test_a_rate_limited_request_is_not_an_invalid_request(make_client: AppFactory) -> None:
    """A rate limit refuses a request for arriving, not for being wrong."""
    with make_client(policy=VULNERABLE_PER_SOURCE_RATE_LIMIT) as client:
        headers = {**auth("PATRON-001"), SOURCE_HEADER: "src-alpha"}
        for _ in range(20):
            client.post(f"/shows/{SHOW_ID}/holds", headers=headers)

    from flowjack.harness.records import INDIVIDUALLY_INVALID

    assert Outcome.REFUSED_BY_RATE_LIMIT not in INDIVIDUALLY_INVALID


def test_the_secure_application_holds_under_the_same_scenario(
    client: TestClient, clock: FakeClock
) -> None:
    ledger = run_harness(client, PER_SOURCE_RATE_LIMIT, sleep=clock.advance).require_ledger()

    assert ledger.operator_seats <= Settings().operator_seat_ceiling
    assert ledger.demand_served == 80
    assert ledger.verdict == VERDICT_HELD


# --------------------------------------------------------------------------------------------
# FR-015 — a correct per-account quota, never violated, defeated by free identities
# --------------------------------------------------------------------------------------------


def test_sixty_manufactured_identities_drain_the_allocation(make_client: AppFactory) -> None:
    with make_client(policy=VULNERABLE_PER_ACCOUNT_QUOTA) as client:
        ledger = run_harness(client, PER_ACCOUNT_QUOTA).require_ledger()

    assert ledger.operator_seats == 120
    assert ledger.operator_identities == 60
    assert ledger.demand_served == 0
    assert ledger.verdict == VERDICT_ABSENT


def test_the_quota_itself_is_never_violated(make_client: AppFactory) -> None:
    """The limit was correct. Its key was free. That is the whole shape."""
    quota = Settings().seat_quota_default

    with make_client(policy=VULNERABLE_PER_ACCOUNT_QUOTA) as client:
        ledger = run_harness(client, PER_ACCOUNT_QUOTA).require_ledger()

    assert ledger.max_seats_per_identity == quota == 2
    assert ledger.operator_seats == ledger.operator_identities * quota


def test_the_quota_still_refuses_a_third_seat_from_one_identity(
    make_client: AppFactory,
) -> None:
    with make_client(policy=VULNERABLE_PER_ACCOUNT_QUOTA) as client:
        for _ in range(2):
            assert (
                client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001")).status_code
                == 201
            )
        third = client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))

    assert third.status_code == 409


def test_every_request_that_drained_it_was_compliant(make_client: AppFactory) -> None:
    with make_client(policy=VULNERABLE_PER_ACCOUNT_QUOTA) as client:
        result = run_harness(client, PER_ACCOUNT_QUOTA)

    report = replay(result.records)
    assert report.all_valid
    assert report.valid_percentage == 100.0


# --------------------------------------------------------------------------------------------
# FR-016 — a verification gate at the front door, paid once
# --------------------------------------------------------------------------------------------


def test_one_challenge_buys_the_whole_allocation(make_client: AppFactory) -> None:
    with make_client(policy=VULNERABLE_FRONT_DOOR_GATE) as client:
        ledger = run_harness(client, FRONT_DOOR_GATE).require_ledger()

    assert ledger.challenges_passed == 1
    assert ledger.operator_seats == 120
    assert ledger.verdict == VERDICT_ABSENT


def test_the_gate_is_genuinely_enforced_at_the_step_it_guards(
    make_client: AppFactory,
) -> None:
    with make_client(policy=VULNERABLE_FRONT_DOOR_GATE) as client:
        ungated = client.post("/patrons", json={"display_name": "Demo Operator"})
        assert ungated.status_code == VERIFICATION_REQUIRED_STATUS

        token = client.get("/verification/challenge").json()["token"]
        gated = client.post(
            "/patrons",
            json={"display_name": "Demo Operator"},
            headers={VERIFICATION_HEADER: token},
        )
        assert gated.status_code == 201


def test_a_verification_token_is_single_use_so_nothing_is_replayed(
    make_client: AppFactory,
) -> None:
    with make_client(policy=VULNERABLE_FRONT_DOOR_GATE) as client:
        token = client.get("/verification/challenge").json()["token"]
        headers = {VERIFICATION_HEADER: token}

        first = client.post("/patrons", json={"display_name": "Demo A"}, headers=headers)
        second = client.post("/patrons", json={"display_name": "Demo B"}, headers=headers)

    assert first.status_code == 201
    assert second.status_code == VERIFICATION_REQUIRED_STATUS


def test_the_flow_behind_the_gate_asks_for_nothing(make_client: AppFactory) -> None:
    """The gate prices entry. It says nothing about how much flow one entry may consume."""
    with make_client(policy=VULNERABLE_FRONT_DOOR_GATE) as client:
        for _ in range(5):
            hold = client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
            assert hold.status_code == 201
            confirmed = client.post(
                f"/holds/{hold.json()['hold_id']}/confirm", headers=auth("PATRON-001")
            )
            assert confirmed.status_code == 201


def test_a_missing_verification_token_counts_as_an_invalid_request() -> None:
    """Kept strict so the project's 100%-valid claim is never true by definition."""
    from flowjack.harness.records import INDIVIDUALLY_INVALID

    assert Outcome.REFUSED_BY_VERIFICATION in INDIVIDUALLY_INVALID


# --------------------------------------------------------------------------------------------
# FR-017 — slow, sequential, under every limit, and it still drains
# --------------------------------------------------------------------------------------------


def test_concurrency_one_under_the_rate_limit_still_takes_everything(
    make_client: AppFactory, clock: FakeClock
) -> None:
    with make_client(policy=VULNERABLE_PER_SOURCE_RATE_LIMIT) as client:
        result = run_harness(client, SLOW_AND_SEQUENTIAL, sleep=clock.advance)
    ledger = result.require_ledger()

    assert SLOW_AND_SEQUENTIAL.concurrency == 1
    assert SLOW_AND_SEQUENTIAL.pace_seconds == _PACE
    assert ledger.rate_limited_requests == 0
    assert ledger.operator_seats == 120
    assert ledger.demand_served == 0
    assert ledger.verdict == VERDICT_ABSENT


def test_the_sequential_run_used_exactly_one_source_and_one_identity(
    make_client: AppFactory, clock: FakeClock
) -> None:
    """No simultaneity, no distribution, no trick — just the flow, over and over."""
    with make_client(policy=VULNERABLE_PER_SOURCE_RATE_LIMIT) as client:
        ledger = run_harness(client, SLOW_AND_SEQUENTIAL, sleep=clock.advance).require_ledger()

    assert len(ledger.requests_by_source) == 1
    assert ledger.operator_identities == 1


def test_pacing_changes_only_how_long_it_takes(make_client: AppFactory, clock: FakeClock) -> None:
    """The identical outcome arrives paced and unpaced. Throttling is not a fix."""

    def seats(pace: float) -> int:
        with make_client(policy=VULNERABLE_PER_SOURCE_RATE_LIMIT) as client:
            config = replace(SLOW_AND_SEQUENTIAL, pace_seconds=pace)
            return run_harness(client, config, sleep=clock.advance).require_ledger().operator_seats

    assert seats(_PACE) == 120
    assert seats(_PACE * 4) == 120


# --------------------------------------------------------------------------------------------
# FR-018 — the legitimate power user, and the absence of a malicious request
# --------------------------------------------------------------------------------------------


def test_the_household_patron_still_books_four_seats(client: TestClient) -> None:
    from flowjack.db import HOUSEHOLD_PATRON_ID

    confirmed = 0
    for _ in range(4):
        hold = client.post(f"/shows/{SHOW_ID}/holds", headers=auth(HOUSEHOLD_PATRON_ID))
        assert hold.status_code == 201
        result = client.post(
            f"/holds/{hold.json()['hold_id']}/confirm", headers=auth(HOUSEHOLD_PATRON_ID)
        )
        assert result.status_code == 201
        confirmed += 1

    assert confirmed == 4


def test_every_shape_replays_as_one_hundred_percent_valid(
    make_client: AppFactory, clock: FakeClock
) -> None:
    """The finding, stated once for the whole ladder."""
    shapes = [
        (VULNERABLE_PER_SOURCE_RATE_LIMIT, PER_SOURCE_RATE_LIMIT),
        (VULNERABLE_PER_ACCOUNT_QUOTA, PER_ACCOUNT_QUOTA),
        (VULNERABLE_FRONT_DOOR_GATE, FRONT_DOOR_GATE),
        (VULNERABLE_PER_SOURCE_RATE_LIMIT, SLOW_AND_SEQUENTIAL),
    ]
    for policy, scenario in shapes:
        with make_client(policy=policy) as client:
            result = run_harness(client, scenario, sleep=clock.advance)
        report = replay(result.records)
        assert report.valid_percentage == 100.0, f"{policy.name} / {report.invalid_by_outcome}"
        assert report.all_valid
        assert result.require_ledger().operator_seats == 120


def test_the_validity_replay_reports_invalid_requests_when_there_are_some(
    make_client: AppFactory,
) -> None:
    """The replay is a real check, not a constant that always prints 100%."""
    with make_client(policy=VULNERABLE_FRONT_DOOR_GATE) as client:
        # Register without paying the challenge: a required per-request credential is absent.
        result = run_harness(client, replace(FRONT_DOOR_GATE, pass_verification=False))

    report = replay(result.records)
    assert not report.all_valid
    assert report.valid_percentage < 100.0
    assert Outcome.REFUSED_BY_VERIFICATION.value in report.invalid_by_outcome
    assert "some requests were individually invalid" in report.render()


def test_the_validity_report_renders_the_finding(make_client: AppFactory) -> None:
    with make_client(policy=VULNERABLE_PER_ACCOUNT_QUOTA) as client:
        result = run_harness(client, PER_ACCOUNT_QUOTA)

    text = replay(result.records).render()
    assert "individually VALID" in text
    assert "100.0%" in text
    assert "nothing to key on" in text


# --------------------------------------------------------------------------------------------
# FR-009 — identical payloads
# --------------------------------------------------------------------------------------------


def test_secure_and_every_vulnerable_shape_answer_a_legitimate_request_identically(
    client: TestClient, make_client: AppFactory
) -> None:
    baseline = client.post(f"/shows/{SHOW_ID}/holds", headers=auth("PATRON-001"))
    assert baseline.status_code == 201

    for policy in (
        VULNERABLE_PER_SOURCE_RATE_LIMIT,
        VULNERABLE_PER_ACCOUNT_QUOTA,
        VULNERABLE_FRONT_DOOR_GATE,
    ):
        with make_client(policy=policy) as variant:
            response = variant.post(
                f"/shows/{SHOW_ID}/holds",
                headers={**auth("PATRON-001"), SOURCE_HEADER: "src-alpha"},
            )
        assert response.status_code == baseline.status_code, policy.name
        assert response.json() == baseline.json(), policy.name


def test_the_genuine_actor_is_indistinguishable_from_the_operator_per_request(
    make_client: AppFactory, clock: FakeClock
) -> None:
    """Same routes, same bodies, same statuses. Only the totals differ."""
    with make_client(policy=VULNERABLE_PER_ACCOUNT_QUOTA) as client:
        result = run_harness(client, PER_ACCOUNT_QUOTA, sleep=clock.advance)

    operator = {r.status for r in result.records if r.actor is Actor.OPERATOR}
    genuine = {r.status for r in result.records if r.actor is Actor.GENUINE}
    assert operator <= {201, 409}
    assert genuine <= {201, 409}
