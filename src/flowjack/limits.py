"""Flow limits — strategies A and B.

**Strategy A — an outcome quota on the business flow.** The limit counts *seats*, not requests,
per identity per show. Crucially it counts outstanding holds together with confirmed tickets: a
hold is a claim on a seat nobody else can have, so it must cost the holder exactly what a ticket
costs. A limit that counted only confirmations would count the wrong event, and holding without
ever confirming would be free.

Expiry does not simply hand entitlement back. A patron may re-hold after an expiry
``rehold_allowance`` times; past that bound, expired holds keep consuming entitlement. Without
that bound, "hold, let it lapse, hold again" is an unlimited flow wearing a limit's clothes.

**Strategy B — governed identity supply.** A quota keyed on an identity is only ever as strong as
the cost of obtaining that identity. Registration is therefore treated as a sensitive flow in its
own right: it consumes a single-use eligibility reference the venue issued out of band, *and* it
counts against a documented cap on self-service registrations. The ceiling is deliberately modest
rather than absolute — an operator is limited, not eliminated, which is the honest outcome for
this control.
"""

from __future__ import annotations

import sqlite3

from flowjack.audit import RequestStep
from flowjack.errors import FlowLimitRefusedError


def expire_due_holds(conn: sqlite3.Connection, *, now: float) -> int:
    """Lapse every hold whose window has closed. Returns how many lapsed."""
    cursor = conn.execute(
        "UPDATE holds SET state = 'expired' WHERE state = 'held' AND expires_at <= ?",
        (now,),
    )
    return int(cursor.rowcount)


def seats_charged(
    conn: sqlite3.Connection,
    *,
    patron_id: str,
    show_id: str,
    rehold_allowance: int,
) -> int:
    """Seats this patron's entitlement is currently paying for.

    Outstanding holds and confirmed tickets both count in full. Expired holds are forgiven up to
    ``rehold_allowance`` and charged thereafter.
    """
    held = _scalar(
        conn,
        "SELECT COUNT(*) FROM holds WHERE patron_id = ? AND show_id = ? AND state = 'held'",
        (patron_id, show_id),
    )
    ticketed = _scalar(
        conn,
        "SELECT COUNT(*) FROM tickets WHERE patron_id = ? AND show_id = ?",
        (patron_id, show_id),
    )
    expired = _scalar(
        conn,
        "SELECT COUNT(*) FROM holds WHERE patron_id = ? AND show_id = ? AND state = 'expired'",
        (patron_id, show_id),
    )
    forgiven = min(expired, rehold_allowance)
    return held + ticketed + (expired - forgiven)


def require_seat_entitlement(
    conn: sqlite3.Connection,
    *,
    patron_id: str,
    show_id: str,
    entitlement: int,
    rehold_allowance: int,
    step: RequestStep,
) -> None:
    """Strategy A gate. Refuses generically when the patron's seat entitlement is spent."""
    charged = seats_charged(
        conn, patron_id=patron_id, show_id=show_id, rehold_allowance=rehold_allowance
    )
    if charged >= entitlement:
        raise FlowLimitRefusedError(step=step, show_id=show_id, patron_id=patron_id)


def require_identity_supply(
    conn: sqlite3.Connection,
    *,
    eligibility_ref: str,
    registration_cap: int,
) -> None:
    """Strategy B gate. Refuses generically when identity supply is exhausted.

    Both conditions are the same refusal to the caller: an eligibility reference that is unknown
    or already spent, and a self-service registration cap that has been reached.
    """
    granted = _scalar(conn, "SELECT COUNT(*) FROM registrations", ())
    if granted >= registration_cap:
        raise FlowLimitRefusedError(step="register")

    row = conn.execute(
        "SELECT consumed_by FROM eligibility_refs WHERE eligibility_ref = ?",
        (eligibility_ref,),
    ).fetchone()
    if row is None or row["consumed_by"] is not None:
        raise FlowLimitRefusedError(step="register")


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple[object, ...]) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row is not None else 0
