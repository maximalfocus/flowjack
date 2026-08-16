"""The application factory shared by every flowjack variant.

This slice ships the **secure** variant only. Later slices add vulnerable variants behind an
opt-in Compose profile; they will reuse this router and differ only in which limits govern the
flow.
"""

from __future__ import annotations

import itertools
import sqlite3
import threading
from collections.abc import Iterator

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from flowjack import audit
from flowjack.auth import UNAUTHORIZED_DETAIL, AuthenticationFailedError, Patron, authenticate
from flowjack.clock import Clock, SystemClock
from flowjack.config import Settings, load_settings
from flowjack.db import Database
from flowjack.errors import REFUSAL_DETAIL, REFUSAL_STATUS, FlowLimitRefusedError
from flowjack.flow import confirm_hold, place_hold, register_patron
from flowjack.limits import expire_due_holds
from flowjack.policy import SECURE, Policy
from flowjack.schemas import (
    AllocationResponse,
    HoldResponse,
    PatronHolding,
    RegistrationRequest,
    RegistrationResponse,
    ShowResponse,
    TicketResponse,
)


def create_app(
    *,
    settings: Settings | None = None,
    clock: Clock | None = None,
    database: Database | None = None,
    policy: Policy = SECURE,
) -> FastAPI:
    resolved_settings = settings if settings is not None else load_settings()
    resolved_clock = clock if clock is not None else SystemClock()
    db = database if database is not None else Database(resolved_settings, resolved_clock)

    variant = "VULNERABLE" if policy.is_vulnerable else "SECURE"
    app = FastAPI(
        title=f"flowjack — {policy.name} application",
        description=(
            "Local educational demo of unrestricted access to sensitive business flows "
            f"(API6:2023 / CWE-840). This is the {variant} variant "
            f"under policy {policy.name!r}."
        ),
        version="0.1.0",
    )
    app.state.policy = policy
    app.state.settings = resolved_settings
    app.state.clock = resolved_clock
    app.state.db = db

    counter = itertools.count(1)
    counter_lock = threading.Lock()

    @app.middleware("http")
    async def assign_request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        with counter_lock:
            sequence = next(counter)
        request_id = f"req-{sequence:06d}"
        audit.set_request_id(request_id)
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(FlowLimitRefusedError)
    async def handle_refusal(_: Request, exc: FlowLimitRefusedError) -> JSONResponse:
        # The single place a refusal becomes visible: exactly one audit event, one generic body.
        audit.emit_refusal(step=exc.step, show_id=exc.show_id, patron_id=exc.patron_id)
        return JSONResponse(status_code=REFUSAL_STATUS, content={"detail": REFUSAL_DETAIL})

    @app.exception_handler(AuthenticationFailedError)
    async def handle_auth_failure(_: Request, __: AuthenticationFailedError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": UNAUTHORIZED_DETAIL})

    def current_patron(authorization: str | None = Header(default=None)) -> Patron:
        with db.transaction() as conn:
            return authenticate(conn, authorization, now=resolved_clock.now())

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/patrons", response_model=RegistrationResponse, status_code=201)
    def post_patrons(body: RegistrationRequest) -> RegistrationResponse:
        with db.transaction() as conn:
            result = register_patron(
                conn,
                display_name=body.display_name,
                eligibility_ref=body.eligibility_ref,
                settings=resolved_settings,
                policy=policy,
                now=resolved_clock.now(),
            )
        return RegistrationResponse(
            patron_id=result.patron_id,
            display_name=result.display_name,
            seat_entitlement=result.seat_entitlement,
            token=result.token,
        )

    @app.post("/shows/{show_id}/holds", response_model=HoldResponse, status_code=201)
    def post_hold(show_id: str, patron: Patron = Depends(current_patron)) -> HoldResponse:
        with db.transaction() as conn:
            result = place_hold(
                conn,
                patron=patron,
                show_id=show_id,
                settings=resolved_settings,
                policy=policy,
                now=resolved_clock.now(),
            )
        return HoldResponse(
            hold_id=result.hold_id,
            show_id=result.show_id,
            seat_id=result.seat_id,
            seat_label=result.seat_label,
            expires_at=result.expires_at,
        )

    @app.post("/holds/{hold_id}/confirm", response_model=TicketResponse, status_code=201)
    def post_confirm(hold_id: str, patron: Patron = Depends(current_patron)) -> TicketResponse:
        with db.transaction() as conn:
            result = confirm_hold(
                conn,
                patron=patron,
                hold_id=hold_id,
                policy=policy,
                now=resolved_clock.now(),
            )
        return TicketResponse(
            ticket_id=result.ticket_id,
            hold_id=result.hold_id,
            show_id=result.show_id,
            seat_id=result.seat_id,
            seat_label=result.seat_label,
        )

    @app.get("/shows/{show_id}", response_model=ShowResponse)
    def get_show(show_id: str) -> ShowResponse:
        with db.transaction() as conn:
            expire_due_holds(conn, now=resolved_clock.now())
            row = conn.execute(
                "SELECT show_id, title, venue, performance_date, seats_allocated"
                " FROM shows WHERE show_id = ?",
                (show_id,),
            ).fetchone()
            if row is None:
                raise FlowLimitRefusedError(step="hold", show_id=show_id)
            held, confirmed = _seat_counts(conn, show_id)
            allocated = int(row["seats_allocated"])
            return ShowResponse(
                show_id=str(row["show_id"]),
                title=str(row["title"]),
                venue=str(row["venue"]),
                performance_date=str(row["performance_date"]),
                seats_allocated=allocated,
                seats_held=held,
                seats_confirmed=confirmed,
                seats_available=allocated - held - confirmed,
            )

    @app.get("/shows/{show_id}/allocation", response_model=AllocationResponse)
    def get_allocation(show_id: str) -> AllocationResponse:
        with db.transaction() as conn:
            expire_due_holds(conn, now=resolved_clock.now())
            row = conn.execute(
                "SELECT seats_allocated FROM shows WHERE show_id = ?", (show_id,)
            ).fetchone()
            if row is None:
                raise FlowLimitRefusedError(step="hold", show_id=show_id)
            held, confirmed = _seat_counts(conn, show_id)
            allocated = int(row["seats_allocated"])
            holdings = [
                PatronHolding(
                    patron_id=str(record["patron_id"]),
                    created_via=str(record["created_via"]),
                    seats_held=int(record["seats_held"]),
                    seats_confirmed=int(record["seats_confirmed"]),
                )
                for record in _holdings(conn, show_id)
            ]
            return AllocationResponse(
                show_id=show_id,
                seats_allocated=allocated,
                seats_held=held,
                seats_confirmed=confirmed,
                seats_available=allocated - held - confirmed,
                holdings=holdings,
            )

    return app


def _seat_counts(conn: sqlite3.Connection, show_id: str) -> tuple[int, int]:
    held_row = conn.execute(
        "SELECT COUNT(*) FROM holds WHERE show_id = ? AND state = 'held'", (show_id,)
    ).fetchone()
    confirmed_row = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE show_id = ?", (show_id,)
    ).fetchone()
    return int(held_row[0]), int(confirmed_row[0])


def _holdings(conn: sqlite3.Connection, show_id: str) -> Iterator[sqlite3.Row]:
    rows = conn.execute(
        "SELECT p.patron_id, p.created_via,"
        "       COALESCE(h.held, 0)  AS seats_held,"
        "       COALESCE(t.owned, 0) AS seats_confirmed"
        " FROM patrons p"
        " LEFT JOIN (SELECT patron_id, COUNT(*) AS held FROM holds"
        "            WHERE show_id = ? AND state = 'held' GROUP BY patron_id) h"
        "        ON h.patron_id = p.patron_id"
        " LEFT JOIN (SELECT patron_id, COUNT(*) AS owned FROM tickets"
        "            WHERE show_id = ? GROUP BY patron_id) t"
        "        ON t.patron_id = p.patron_id"
        " WHERE COALESCE(h.held, 0) > 0 OR COALESCE(t.owned, 0) > 0"
        " ORDER BY p.patron_id",
        (show_id, show_id),
    ).fetchall()
    yield from rows
