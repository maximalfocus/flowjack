"""The sensitive business flow, and strategy C.

Seat acquisition is genuinely two steps — place a hold, then confirm it. That shape is required,
not incidental: it is what makes it possible to show that a control guarding the step a user
interface happens to call first is not a control on the flow.

**Strategy C — flow-scoped enforcement.** The server records that a flow was entered, by whom, and
how far it has progressed. Every subsequent step re-reads that record and requires it to exist, to
belong to the *same* authenticated identity, and to be at the expected step. A caller who arrives
directly at the confirmation step has no flow state to present, so there is nothing to skip past;
a caller who presents someone else's hold fails the identity check; a caller who replays a
finished flow fails the ordering check. All three are the same refusal.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from flowjack.auth import Patron, demo_token
from flowjack.config import Settings
from flowjack.errors import FlowLimitRefusedError
from flowjack.limits import expire_due_holds, require_identity_supply, require_seat_entitlement


@dataclass(frozen=True, slots=True)
class HoldResult:
    hold_id: str
    seat_id: str
    seat_label: str
    show_id: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class TicketResult:
    ticket_id: str
    hold_id: str
    seat_id: str
    seat_label: str
    show_id: str


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    patron_id: str
    display_name: str
    seat_entitlement: int
    token: str


def register_patron(
    conn: sqlite3.Connection,
    *,
    display_name: str,
    eligibility_ref: str,
    settings: Settings,
    now: float,
) -> RegistrationResult:
    """Self-service registration, governed as a sensitive flow in its own right (strategy B)."""
    require_identity_supply(
        conn,
        eligibility_ref=eligibility_ref,
        registration_cap=settings.self_service_registration_cap,
    )

    sequence = _next_sequence(conn, "SELECT COUNT(*) FROM registrations")
    patron_id = f"PATRON-SS-{sequence:03d}"
    token = demo_token(patron_id)

    conn.execute(
        "INSERT INTO patrons (patron_id, display_name, seat_entitlement, created_via)"
        " VALUES (?, ?, ?, 'self_service')",
        (patron_id, display_name, settings.seat_quota_default),
    )
    conn.execute(
        "INSERT INTO tokens (token, patron_id, expires_at) VALUES (?, ?, ?)",
        (token, patron_id, now + 86_400.0),
    )
    conn.execute(
        "UPDATE eligibility_refs SET consumed_by = ? WHERE eligibility_ref = ?",
        (patron_id, eligibility_ref),
    )
    conn.execute(
        "INSERT INTO registrations (registration_id, patron_id, eligibility_ref, created_at)"
        " VALUES (?, ?, ?, ?)",
        (f"REG-{sequence:03d}", patron_id, eligibility_ref, now),
    )

    return RegistrationResult(
        patron_id=patron_id,
        display_name=display_name,
        seat_entitlement=settings.seat_quota_default,
        token=token,
    )


def place_hold(
    conn: sqlite3.Connection,
    *,
    patron: Patron,
    show_id: str,
    settings: Settings,
    now: float,
) -> HoldResult:
    """Flow step 1. Charged against the patron's seat entitlement (strategy A)."""
    expire_due_holds(conn, now=now)
    _require_show(conn, show_id)

    require_seat_entitlement(
        conn,
        patron_id=patron.patron_id,
        show_id=show_id,
        entitlement=patron.seat_entitlement,
        rehold_allowance=settings.rehold_allowance,
        step="hold",
    )

    seat = conn.execute(
        "SELECT s.seat_id, s.seat_label FROM seats s"
        " WHERE s.show_id = ?"
        "   AND NOT EXISTS (SELECT 1 FROM holds h WHERE h.seat_id = s.seat_id AND h.state = 'held')"
        "   AND NOT EXISTS (SELECT 1 FROM tickets t WHERE t.seat_id = s.seat_id)"
        " ORDER BY s.seat_id LIMIT 1",
        (show_id,),
    ).fetchone()
    if seat is None:
        # Sold out. Identical refusal to "your entitlement is used" — no oracle.
        raise FlowLimitRefusedError(step="hold", show_id=show_id, patron_id=patron.patron_id)

    sequence = _next_sequence(conn, "SELECT COUNT(*) FROM holds")
    hold_id = f"HOLD-{sequence:06d}"
    expires_at = now + settings.hold_ttl_seconds

    conn.execute(
        "INSERT INTO holds (hold_id, show_id, seat_id, patron_id, placed_at, expires_at, state)"
        " VALUES (?, ?, ?, ?, ?, ?, 'held')",
        (hold_id, show_id, seat["seat_id"], patron.patron_id, now, expires_at),
    )
    # Strategy C: record that this flow was legitimately entered, and by whom.
    conn.execute(
        "INSERT INTO flow_states (flow_id, hold_id, patron_id, show_id, step, entered_at)"
        " VALUES (?, ?, ?, ?, 'held', ?)",
        (f"FLOW-{sequence:06d}", hold_id, patron.patron_id, show_id, now),
    )

    return HoldResult(
        hold_id=hold_id,
        seat_id=str(seat["seat_id"]),
        seat_label=str(seat["seat_label"]),
        show_id=show_id,
        expires_at=expires_at,
    )


def confirm_hold(
    conn: sqlite3.Connection,
    *,
    patron: Patron,
    hold_id: str,
    now: float,
) -> TicketResult:
    """Flow step 2. Refuses unless this identity's flow reached step 1 first (strategy C)."""
    expire_due_holds(conn, now=now)

    state = conn.execute(
        "SELECT f.flow_id, f.step, f.patron_id AS flow_patron, h.state AS hold_state,"
        "       h.show_id, h.seat_id, s.seat_label"
        " FROM flow_states f"
        " JOIN holds h ON h.hold_id = f.hold_id"
        " JOIN seats s ON s.seat_id = h.seat_id"
        " WHERE f.hold_id = ?",
        (hold_id,),
    ).fetchone()

    # No flow state: this request entered the flow at step 2. Wrong identity: this is somebody
    # else's flow. Wrong step: this flow is already finished. Lapsed hold: the claim is gone.
    if (
        state is None
        or str(state["flow_patron"]) != patron.patron_id
        or str(state["step"]) != "held"
        or str(state["hold_state"]) != "held"
    ):
        raise FlowLimitRefusedError(step="confirm", patron_id=patron.patron_id)

    sequence = _next_sequence(conn, "SELECT COUNT(*) FROM tickets")
    ticket_id = f"TICKET-{sequence:06d}"

    conn.execute(
        "INSERT INTO tickets (ticket_id, hold_id, show_id, seat_id, patron_id, confirmed_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (ticket_id, hold_id, state["show_id"], state["seat_id"], patron.patron_id, now),
    )
    conn.execute("UPDATE holds SET state = 'confirmed' WHERE hold_id = ?", (hold_id,))
    conn.execute("UPDATE flow_states SET step = 'confirmed' WHERE hold_id = ?", (hold_id,))

    return TicketResult(
        ticket_id=ticket_id,
        hold_id=hold_id,
        seat_id=str(state["seat_id"]),
        seat_label=str(state["seat_label"]),
        show_id=str(state["show_id"]),
    )


def _require_show(conn: sqlite3.Connection, show_id: str) -> None:
    row = conn.execute("SELECT 1 FROM shows WHERE show_id = ?", (show_id,)).fetchone()
    if row is None:
        raise FlowLimitRefusedError(step="hold", show_id=show_id)


def _next_sequence(conn: sqlite3.Connection, count_sql: str) -> int:
    row = conn.execute(count_sql).fetchone()
    return (int(row[0]) if row is not None else 0) + 1
