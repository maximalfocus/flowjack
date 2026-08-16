"""The HTTP walkthrough.

Everything this asserts is established through the application's own HTTP boundary against a
running container — not in-process, and never by inspecting the database. It is the check that the
secure application behaves as promised when reached the way a real client reaches it.

It runs sequentially, one request at a time. Nothing here depends on concurrency.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field

import httpx

from flowjack.auth import demo_token
from flowjack.config import SHOW_ID
from flowjack.db import ELIGIBILITY_REFS, EXPIRED_TOKEN, HOUSEHOLD_PATRON_ID
from flowjack.errors import REFUSAL_DETAIL, REFUSAL_STATUS


@dataclass
class Report:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def record(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append((name, passed, detail))
        marker = "PASS" if passed else "FAIL"
        line = f"  [{marker}] {name}"
        if detail:
            line += f" — {detail}"
        print(line, flush=True)

    @property
    def failed(self) -> list[str]:
        return [name for name, passed, _ in self.checks if not passed]


def _auth(patron_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {demo_token(patron_id)}"}


def _wait_for_health(client: httpx.Client, attempts: int = 60) -> None:
    for _ in range(attempts):
        try:
            if client.get("/healthz", timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise SystemExit("secure application did not become healthy")


def _is_generic_refusal(response: httpx.Response) -> bool:
    return response.status_code == REFUSAL_STATUS and response.json() == {"detail": REFUSAL_DETAIL}


def run(base_url: str, hold_ttl_seconds: float) -> int:
    report = Report()
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        _wait_for_health(client)

        print("\nflowjack — secure application walkthrough")
        print(f"  target        : {base_url}")
        print(f"  show          : {SHOW_ID}")
        print(f"  hold window   : {hold_ttl_seconds}s (short by design; see README)\n")

        show = client.get(f"/shows/{SHOW_ID}").json()
        report.record(
            "show reports its full allocation before any booking",
            show["seats_available"] == show["seats_allocated"],
            f"{show['seats_available']}/{show['seats_allocated']} available",
        )

        _check_generic_401(client, report)
        _check_entitlement(client, report)
        _check_hold_charges_entitlement(client, report)
        _check_flow_scoped_enforcement(client, report)
        _check_identity_supply(client, report)
        _check_household_booking(client, report)
        _check_refusals_are_identical(client, report)
        _check_rehold_allowance(client, report, hold_ttl_seconds)

    print()
    if report.failed:
        print(f"WALKTHROUGH FAILED — {len(report.failed)} check(s): {', '.join(report.failed)}")
        return 1
    print(f"WALKTHROUGH PASSED — {len(report.checks)} checks")
    return 0


def _check_generic_401(client: httpx.Client, report: Report) -> None:
    cases = {
        "missing": {},
        "malformed": {"Authorization": "NotBearer whatever"},
        "unknown": {"Authorization": "Bearer flowjack-demo-token-nobody"},
        "expired": {"Authorization": f"Bearer {EXPIRED_TOKEN}"},
    }
    responses = {
        label: client.post(f"/shows/{SHOW_ID}/holds", headers=headers)
        for label, headers in cases.items()
    }
    bodies = {label: (r.status_code, r.text) for label, r in responses.items()}
    all_401 = all(r.status_code == 401 for r in responses.values())
    identical = len(set(bodies.values())) == 1
    report.record(
        "missing / malformed / unknown / expired tokens all return generic 401",
        all_401 and identical,
        f"statuses={sorted({r.status_code for r in responses.values()})}",
    )


def _check_entitlement(client: httpx.Client, report: Report) -> None:
    patron = "PATRON-001"
    first = client.post(f"/shows/{SHOW_ID}/holds", headers=_auth(patron))
    second = client.post(f"/shows/{SHOW_ID}/holds", headers=_auth(patron))
    third = client.post(f"/shows/{SHOW_ID}/holds", headers=_auth(patron))
    report.record(
        "two seats succeed and the third is refused against a two-seat entitlement",
        first.status_code == 201 and second.status_code == 201 and _is_generic_refusal(third),
        f"{first.status_code}, {second.status_code}, {third.status_code}",
    )

    confirmed = client.post(f"/holds/{first.json()['hold_id']}/confirm", headers=_auth(patron))
    after_confirm = client.post(f"/shows/{SHOW_ID}/holds", headers=_auth(patron))
    report.record(
        "confirming a hold does not free entitlement for another seat",
        confirmed.status_code == 201 and _is_generic_refusal(after_confirm),
        f"confirm={confirmed.status_code}, next hold={after_confirm.status_code}",
    )


def _check_hold_charges_entitlement(client: httpx.Client, report: Report) -> None:
    patron = "PATRON-002"
    holds = [client.post(f"/shows/{SHOW_ID}/holds", headers=_auth(patron)) for _ in range(2)]
    blocked = client.post(f"/shows/{SHOW_ID}/holds", headers=_auth(patron))
    report.record(
        "an outstanding hold consumes entitlement exactly as a confirmed ticket does",
        all(r.status_code == 201 for r in holds) and _is_generic_refusal(blocked),
        "two unconfirmed holds exhaust a two-seat entitlement",
    )


def _check_flow_scoped_enforcement(client: httpx.Client, report: Report) -> None:
    owner, stranger = "PATRON-003", "PATRON-004"
    hold = client.post(f"/shows/{SHOW_ID}/holds", headers=_auth(owner))
    hold_id = hold.json()["hold_id"]

    entered_at_step_two = client.post("/holds/HOLD-999999/confirm", headers=_auth(stranger))
    report.record(
        "entering the flow at the confirmation step is refused",
        _is_generic_refusal(entered_at_step_two),
        f"status={entered_at_step_two.status_code}",
    )

    someone_elses_flow = client.post(f"/holds/{hold_id}/confirm", headers=_auth(stranger))
    report.record(
        "confirming another identity's hold is refused",
        _is_generic_refusal(someone_elses_flow),
        f"status={someone_elses_flow.status_code}",
    )

    mine = client.post(f"/holds/{hold_id}/confirm", headers=_auth(owner))
    replayed = client.post(f"/holds/{hold_id}/confirm", headers=_auth(owner))
    report.record(
        "the owner's in-order confirmation succeeds and a replay is refused",
        mine.status_code == 201 and _is_generic_refusal(replayed),
        f"confirm={mine.status_code}, replay={replayed.status_code}",
    )


def _check_identity_supply(client: httpx.Client, report: Report) -> None:
    unknown = client.post(
        "/patrons", json={"display_name": "Demo Operator", "eligibility_ref": "NOT-A-REF"}
    )
    report.record(
        "registration with an unknown eligibility reference is refused",
        _is_generic_refusal(unknown),
        f"status={unknown.status_code}",
    )

    granted = [
        client.post(
            "/patrons",
            json={"display_name": f"Demo Operator {index}", "eligibility_ref": ref},
        )
        for index, ref in enumerate(ELIGIBILITY_REFS[:3], start=1)
    ]
    report.record(
        "the venue grants exactly its documented self-service registrations",
        all(r.status_code == 201 for r in granted),
        f"{sum(r.status_code == 201 for r in granted)} granted",
    )

    reused = client.post(
        "/patrons",
        json={"display_name": "Demo Operator R", "eligibility_ref": ELIGIBILITY_REFS[0]},
    )
    report.record(
        "reusing a spent eligibility reference is refused",
        _is_generic_refusal(reused),
        f"status={reused.status_code}",
    )

    over_cap = client.post(
        "/patrons",
        json={"display_name": "Demo Operator 4", "eligibility_ref": ELIGIBILITY_REFS[3]},
    )
    report.record(
        "registration beyond the identity-supply cap is refused, valid reference or not",
        _is_generic_refusal(over_cap),
        f"status={over_cap.status_code}",
    )


def _check_household_booking(client: httpx.Client, report: Report) -> None:
    holds = [
        client.post(f"/shows/{SHOW_ID}/holds", headers=_auth(HOUSEHOLD_PATRON_ID)) for _ in range(4)
    ]
    confirms = [
        client.post(
            f"/holds/{response.json()['hold_id']}/confirm",
            headers=_auth(HOUSEHOLD_PATRON_ID),
        )
        for response in holds
        if response.status_code == 201
    ]
    fifth = client.post(f"/shows/{SHOW_ID}/holds", headers=_auth(HOUSEHOLD_PATRON_ID))
    report.record(
        "the four-seat household booking succeeds and the fifth seat is refused",
        all(r.status_code == 201 for r in holds)
        and all(r.status_code == 201 for r in confirms)
        and _is_generic_refusal(fifth),
        f"{len(confirms)} of 4 seats confirmed, fifth refused",
    )


def _check_refusals_are_identical(client: httpx.Client, report: Report) -> None:
    entitlement_used = client.post(f"/shows/{SHOW_ID}/holds", headers=_auth("PATRON-001"))
    flow_not_entered = client.post("/holds/HOLD-999998/confirm", headers=_auth("PATRON-005"))
    identity_supply = client.post(
        "/patrons", json={"display_name": "Demo Operator X", "eligibility_ref": "NOT-A-REF"}
    )
    shapes = [entitlement_used, flow_not_entered, identity_supply]
    signatures = {(r.status_code, r.text) for r in shapes}
    report.record(
        "'entitlement used', 'flow not entered', and 'identity supply reached' are "
        "indistinguishable to the caller",
        len(signatures) == 1 and all(_is_generic_refusal(r) for r in shapes),
        f"{len(signatures)} distinct response signature(s)",
    )


def _check_rehold_allowance(client: httpx.Client, report: Report, hold_ttl_seconds: float) -> None:
    patron = "PATRON-010"
    settle = hold_ttl_seconds + 1.0
    cycles = 0
    for _ in range(3):
        placed = client.post(f"/shows/{SHOW_ID}/holds", headers=_auth(patron))
        if placed.status_code != 201:
            break
        cycles += 1
        time.sleep(settle)

    exhausted = client.post(f"/shows/{SHOW_ID}/holds", headers=_auth(patron))
    report.record(
        "hold expiry does not restore entitlement beyond the documented re-hold allowance",
        _is_generic_refusal(exhausted),
        f"{cycles} hold/expire cycles before the flow was refused",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="flowjack secure-application walkthrough")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("FLOWJACK_BASE_URL", "http://secure-app:8000"),
    )
    parser.add_argument(
        "--hold-ttl-seconds",
        type=float,
        default=float(os.environ.get("FLOWJACK_HOLD_TTL_SECONDS", "600")),
    )
    args = parser.parse_args()
    return run(args.base_url, args.hold_ttl_seconds)


if __name__ == "__main__":
    sys.exit(main())
