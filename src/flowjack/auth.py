"""Demo-only bearer authentication.

Authentication is **correct** in flowjack, in every variant, and is not what the demonstration is
about. It exists so that every request in the walkthrough carries an identity — which is precisely
what makes the point: the attack this project demonstrates is made entirely of requests that
authenticate successfully and are authorised to do exactly what they do.

Missing, malformed, unknown, and expired tokens are indistinguishable to the caller.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Final

TOKEN_PREFIX: Final = "flowjack-demo-token-"
UNAUTHORIZED_DETAIL: Final = "Authentication is required."


def demo_token(patron_id: str) -> str:
    """Deterministic, unmistakably fake bearer token for a fictional patron."""
    return f"{TOKEN_PREFIX}{patron_id.lower()}"


@dataclass(frozen=True, slots=True)
class Patron:
    patron_id: str
    display_name: str
    seat_entitlement: int
    created_via: str


class AuthenticationFailedError(Exception):
    """Any authentication problem at all. The caller is never told which one."""


def authenticate(conn: sqlite3.Connection, authorization: str | None, *, now: float) -> Patron:
    """Resolve a bearer token to a patron, or fail generically."""
    token = _bearer_token(authorization)
    if token is None:
        raise AuthenticationFailedError

    row = conn.execute(
        "SELECT t.token, t.expires_at, p.patron_id, p.display_name, p.seat_entitlement,"
        " p.created_via"
        " FROM tokens t JOIN patrons p ON p.patron_id = t.patron_id"
        " WHERE t.token = ?",
        (token,),
    ).fetchone()
    if row is None:
        raise AuthenticationFailedError
    if float(row["expires_at"]) <= now:
        raise AuthenticationFailedError

    return Patron(
        patron_id=str(row["patron_id"]),
        display_name=str(row["display_name"]),
        seat_entitlement=int(row["seat_entitlement"]),
        created_via=str(row["created_via"]),
    )


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token or not token.startswith(TOKEN_PREFIX):
        return None
    return token
