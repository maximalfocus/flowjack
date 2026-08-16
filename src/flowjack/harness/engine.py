"""The business-flow automation harness.

`flowjack` demonstrates a defect that no single request exposes. Every call the operator makes is
authenticated, authorised, and correct, so the unit of observation has to be *the aggregate outcome
of a flow run many times*. This is the thing that runs it many times and then asks the venue what
is left.

**Concurrency is a convenience here, not the mechanism.** It exists to shorten the walkthrough.
Nothing in this demo depends on interleaving: every count the harness asserts is identical on every
machine and in every run, and the negative control in a later slice proves the same outcome arrives
at concurrency 1. The demo where simultaneity *is* the mechanism is ``racejack``.

The engine is a plain callable taking a config and an HTTP client, so tests drive it directly
without simulating terminal input.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Lock
from typing import Any, Protocol

from flowjack.auth import demo_token
from flowjack.config import SHOW_ID, Settings
from flowjack.errors import REFUSAL_STATUS
from flowjack.harness.fixtures import (
    GENUINE_PATRON_IDS,
    GENUINE_SEATS_EACH,
    OPERATOR_ELIGIBILITY_CANDIDATES,
    OPERATOR_SOURCE_LABELS,
    SOURCE_HEADER,
    genuine_source_label,
)
from flowjack.harness.ledger import Ledger, build_ledger
from flowjack.harness.records import Actor, Outcome, RequestRecord, Step, classify
from flowjack.verification import VERIFICATION_HEADER


class Response(Protocol):
    @property
    def status_code(self) -> int: ...

    def json(self) -> Any: ...


class Client(Protocol):
    def get(self, url: str) -> Response: ...

    def post(
        self,
        url: str,
        *,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response: ...


class Mode(StrEnum):
    """What the operator does with the flow."""

    #: Run the flow to completion: hold, then confirm. Seats change hands.
    ACQUIRE = "acquire"
    #: Hold and never confirm, re-holding as each hold lapses. No ticket is ever sold, no payment
    #: is ever taken, and the allocation is denied all the same. Harm needs no transaction.
    ABANDON = "abandon"


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    """Volume, pace, and concurrency are run parameters. None of them is the mechanism."""

    mode: Mode = Mode.ACQUIRE

    show_id: str = SHOW_ID
    #: How many identities the operator attempts to obtain.
    operator_identities: int = 60
    #: Seats the operator attempts per identity. Deliberately more than any quota, so a limit that
    #: exists is visibly reached rather than merely untested.
    operator_seats_per_identity: int = 4
    #: Genuine patrons and the seats each of them wants.
    genuine_patrons: int = len(GENUINE_PATRON_IDS)
    genuine_seats_each: int = GENUINE_SEATS_EACH
    #: Threads used to shorten the run. Not part of the demonstrated mechanism.
    concurrency: int = 8
    #: Seconds to wait before **each** request an identity issues. The negative control uses this
    #: to stay deliberately under an enforced rate limit and drain the allocation anyway.
    pace_seconds: float = 0.0
    #: Obtain a human-verification token before registering. Nothing here defeats, solves, replays,
    #: or machine-answers a challenge; the harness simply pays it, once per registration attempt.
    pass_verification: bool = False
    source_labels: tuple[str, ...] = OPERATOR_SOURCE_LABELS
    #: Abandon mode only: how many hold-and-lapse rounds to run, and how long to wait for a hold
    #: to lapse between them.
    abandon_rounds: int = 2
    abandon_wait_seconds: float = 0.0

    @property
    def demand_offered(self) -> int:
        return self.genuine_patrons * self.genuine_seats_each


@dataclass
class HarnessResult:
    records: list[RequestRecord] = field(default_factory=list)
    ledger: Ledger | None = None

    def require_ledger(self) -> Ledger:
        if self.ledger is None:  # pragma: no cover - defensive
            raise RuntimeError("harness produced no ledger")
        return self.ledger


class _Recorder:
    """Thread-safe record collection. Order of arrival varies; counts do not."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: list[RequestRecord] = []

    def add(self, record: RequestRecord) -> None:
        with self._lock:
            self._records.append(record)

    def sorted_records(self) -> list[RequestRecord]:
        with self._lock:
            return sorted(
                self._records,
                key=lambda r: (r.actor.value, r.identity, r.step.value, r.status),
            )


def run_harness(
    client: Client,
    config: HarnessConfig | None = None,
    settings: Settings | None = None,
    sleep: Callable[[float], None] | None = None,
) -> HarnessResult:
    """Drive the whole flow at volume, then reconcile the venue's allocation.

    ``sleep`` is every place this harness lets time pass — pacing between requests, and waiting for
    a hold to lapse in abandon mode. It defaults to :func:`time.sleep`; tests inject a clock advance
    instead, so no test ever sleeps and every count stays exactly reproducible.
    """
    resolved_config = config if config is not None else HarnessConfig()
    resolved_settings = settings if settings is not None else Settings()
    recorder = _Recorder()
    rest = sleep if sleep is not None else time.sleep

    # The operator runs first. That is the honest worst case: automation reaches the flow before a
    # person does, which is exactly the situation a flow limit has to survive.
    #
    # Identities are obtained once. Abandon mode then re-runs only the *holding*, with the same
    # identities, because that is the shape: one actor letting its own holds lapse and immediately
    # taking them back.
    identities, challenges_passed = _obtain_operator_identities(
        client, resolved_config, recorder, rest
    )
    rounds = resolved_config.abandon_rounds if resolved_config.mode is Mode.ABANDON else 1
    for round_index in range(rounds):
        if round_index and resolved_config.abandon_wait_seconds:
            rest(resolved_config.abandon_wait_seconds)
        _run_operator_seats(client, resolved_config, recorder, identities, rest)

    _run_genuine_demand(client, resolved_config, recorder, rest)

    allocation = client.get(f"/shows/{resolved_config.show_id}/allocation").json()
    records = recorder.sorted_records()
    ledger = build_ledger(
        records=records,
        allocation=allocation,
        operator_ceiling=resolved_settings.operator_seat_ceiling,
        demand_offered=resolved_config.demand_offered,
        challenges_passed=challenges_passed,
    )
    return HarnessResult(records=records, ledger=ledger)


@dataclass(frozen=True, slots=True)
class _Identity:
    """An identity the operator successfully obtained, and how it presents itself."""

    patron_id: str
    source_label: str
    headers: dict[str, str]


def _obtain_operator_identities(
    client: Client,
    config: HarnessConfig,
    recorder: _Recorder,
    rest: Callable[[float], None],
) -> tuple[list[_Identity], int]:
    """Run the identity-supply flow. What comes back is what the operator managed to buy."""
    candidates = OPERATOR_ELIGIBILITY_CANDIDATES[: config.operator_identities]
    granted: list[_Identity] = []
    granted_lock = Lock()
    challenges = 0

    def one_identity(index: int, eligibility_ref: str) -> None:
        source = config.source_labels[index % len(config.source_labels)]
        headers = {SOURCE_HEADER: source}

        if config.pass_verification:
            # Pay the challenge. Once, legitimately, exactly as a person would — the demo neither
            # implements a challenge nor defeats one.
            issued = client.get("/verification/challenge")
            if issued.status_code == 200:
                headers[VERIFICATION_HEADER] = str(issued.json()["token"])
                with granted_lock:
                    nonlocal challenges
                    challenges += 1

        if config.pace_seconds:
            rest(config.pace_seconds)
        response = client.post(
            "/patrons",
            json={"display_name": f"Demo Operator {index:03d}", "eligibility_ref": eligibility_ref},
            headers=headers,
        )
        outcome = classify(response.status_code, refusal_status=REFUSAL_STATUS)
        recorder.add(
            RequestRecord(
                actor=Actor.OPERATOR,
                identity=eligibility_ref,
                source_label=source,
                step=Step.REGISTER,
                status=response.status_code,
                outcome=outcome,
            )
        )
        if outcome is not Outcome.GRANTED:
            return

        body = response.json()
        identity = _Identity(
            patron_id=str(body["patron_id"]),
            source_label=source,
            headers={"Authorization": f"Bearer {body['token']}", SOURCE_HEADER: source},
        )
        with granted_lock:
            granted.append(identity)

    _fan_out(config, list(enumerate(candidates)), one_identity)
    return sorted(granted, key=lambda identity: identity.patron_id), challenges


def _run_operator_seats(
    client: Client,
    config: HarnessConfig,
    recorder: _Recorder,
    identities: list[_Identity],
    rest: Callable[[float], None],
) -> None:
    def one_identity(index: int, identity: _Identity) -> None:
        del index
        _acquire_seats(
            client,
            config=config,
            recorder=recorder,
            actor=Actor.OPERATOR,
            identity=identity.patron_id,
            source=identity.source_label,
            headers=identity.headers,
            seats=config.operator_seats_per_identity,
            rest=rest,
        )

    _fan_out(config, list(enumerate(identities)), one_identity)


def _run_genuine_demand(
    client: Client, config: HarnessConfig, recorder: _Recorder, rest: Callable[[float], None]
) -> None:
    patrons = GENUINE_PATRON_IDS[: config.genuine_patrons]

    def one_patron(index: int, patron_id: str) -> None:
        del index
        source = genuine_source_label(patron_id)
        headers = {
            "Authorization": f"Bearer {demo_token(patron_id)}",
            SOURCE_HEADER: source,
        }
        _acquire_seats(
            client,
            config=config,
            recorder=recorder,
            actor=Actor.GENUINE,
            identity=patron_id,
            source=source,
            headers=headers,
            seats=config.genuine_seats_each,
            rest=rest,
        )

    _fan_out(config, list(enumerate(patrons)), one_patron)


def _acquire_seats(
    client: Client,
    *,
    config: HarnessConfig,
    recorder: _Recorder,
    actor: Actor,
    identity: str,
    source: str,
    headers: Mapping[str, str],
    seats: int,
    rest: Callable[[float], None],
) -> None:
    """Run the two-step flow ``seats`` times for one identity.

    Pacing applies before *every* request, so a configured pace is a genuine per-request rate the
    negative control can hold below an enforced limit.
    """
    for _ in range(seats):
        if config.pace_seconds:
            rest(config.pace_seconds)

        hold = client.post(f"/shows/{config.show_id}/holds", headers=headers)
        hold_outcome = classify(hold.status_code, refusal_status=REFUSAL_STATUS)
        recorder.add(
            RequestRecord(
                actor=actor,
                identity=identity,
                source_label=source,
                step=Step.HOLD,
                status=hold.status_code,
                outcome=hold_outcome,
            )
        )
        if hold_outcome is not Outcome.GRANTED:
            continue
        if config.mode is Mode.ABANDON:
            # The seat is claimed and nobody else can have it. Walking away here is the point.
            continue

        hold_id = str(hold.json()["hold_id"])
        if config.pace_seconds:
            rest(config.pace_seconds)
        confirm = client.post(f"/holds/{hold_id}/confirm", headers=headers)
        recorder.add(
            RequestRecord(
                actor=actor,
                identity=identity,
                source_label=source,
                step=Step.CONFIRM,
                status=confirm.status_code,
                outcome=classify(confirm.status_code, refusal_status=REFUSAL_STATUS),
            )
        )


def _fan_out[T](
    config: HarnessConfig,
    items: Sequence[tuple[int, T]],
    work: Callable[[int, T], None],
) -> None:
    if config.concurrency <= 1:
        for index, item in items:
            work(index, item)
        return
    with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        for future in [pool.submit(work, index, item) for index, item in items]:
            future.result()
