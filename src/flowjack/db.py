"""SQLite storage: schema, connection handling, and deterministic fixtures.

Storage is deliberately plain ``sqlite3`` with explicit SQL rather than an ORM, so that the
flow-limit logic in :mod:`flowjack.limits` and :mod:`flowjack.flow` reads as application code a
reviewer can diff against the vulnerable variants added by later slices.

A single connection guarded by one lock serialises database access. That is an artefact of using
an in-memory SQLite database and is **not** the security control this project demonstrates:
nothing in flowjack depends on concurrency, interleaving, or isolation. The demo that turns on
those properties is ``racejack``.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from flowjack.auth import demo_token
from flowjack.clock import Clock
from flowjack.config import SHOW_DATE, SHOW_ID, SHOW_TITLE, Settings

SCHEMA = """
CREATE TABLE patrons (
    patron_id        TEXT PRIMARY KEY,
    display_name     TEXT NOT NULL,
    seat_entitlement INTEGER NOT NULL,
    created_via      TEXT NOT NULL CHECK (created_via IN ('fixture', 'self_service'))
);

CREATE TABLE tokens (
    token      TEXT PRIMARY KEY,
    patron_id  TEXT NOT NULL REFERENCES patrons(patron_id),
    expires_at REAL NOT NULL
);

CREATE TABLE eligibility_refs (
    eligibility_ref TEXT PRIMARY KEY,
    consumed_by     TEXT REFERENCES patrons(patron_id)
);

CREATE TABLE shows (
    show_id          TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    performance_date TEXT NOT NULL,
    venue            TEXT NOT NULL,
    seats_allocated  INTEGER NOT NULL
);

CREATE TABLE seats (
    seat_id    TEXT PRIMARY KEY,
    show_id    TEXT NOT NULL REFERENCES shows(show_id),
    seat_label TEXT NOT NULL
);

CREATE TABLE holds (
    hold_id    TEXT PRIMARY KEY,
    show_id    TEXT NOT NULL REFERENCES shows(show_id),
    seat_id    TEXT NOT NULL REFERENCES seats(seat_id),
    patron_id  TEXT NOT NULL REFERENCES patrons(patron_id),
    placed_at  REAL NOT NULL,
    expires_at REAL NOT NULL,
    state      TEXT NOT NULL CHECK (state IN ('held', 'confirmed', 'expired'))
);

CREATE TABLE tickets (
    ticket_id    TEXT PRIMARY KEY,
    hold_id      TEXT NOT NULL UNIQUE REFERENCES holds(hold_id),
    show_id      TEXT NOT NULL REFERENCES shows(show_id),
    seat_id      TEXT NOT NULL REFERENCES seats(seat_id),
    patron_id    TEXT NOT NULL REFERENCES patrons(patron_id),
    confirmed_at REAL NOT NULL
);

-- Strategy C. Server-side record that a flow was legitimately entered, by whom, and how far it
-- has progressed. A step that cannot find its own flow state is refused.
CREATE TABLE flow_states (
    flow_id    TEXT PRIMARY KEY,
    hold_id    TEXT NOT NULL UNIQUE REFERENCES holds(hold_id),
    patron_id  TEXT NOT NULL REFERENCES patrons(patron_id),
    show_id    TEXT NOT NULL REFERENCES shows(show_id),
    step       TEXT NOT NULL CHECK (step IN ('held', 'confirmed')),
    entered_at REAL NOT NULL
);

CREATE TABLE registrations (
    registration_id TEXT PRIMARY KEY,
    patron_id       TEXT NOT NULL REFERENCES patrons(patron_id),
    eligibility_ref TEXT NOT NULL REFERENCES eligibility_refs(eligibility_ref),
    created_at      REAL NOT NULL
);

CREATE INDEX idx_holds_patron_show ON holds (patron_id, show_id, state);
CREATE INDEX idx_holds_seat_state ON holds (seat_id, state);
CREATE INDEX idx_tickets_patron_show ON tickets (patron_id, show_id);
"""

GENUINE_PATRON_COUNT = 40
HOUSEHOLD_PATRON_ID = "PATRON-HOUSEHOLD"
EXPIRED_TOKEN = "flowjack-demo-token-expired"
ELIGIBILITY_REFS = (
    "ALDER-MEMBER-4411",
    "ALDER-MEMBER-4412",
    "ALDER-MEMBER-4413",
    "ALDER-MEMBER-4414",
)


class Database:
    """One connection, one lock, deterministic fixtures."""

    def __init__(self, settings: Settings, clock: Clock) -> None:
        self._settings = settings
        self._clock = clock
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            settings.database_path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self.reset()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")

    def close(self) -> None:
        self._connection.close()

    def reset(self) -> None:
        """Recreate the whole database from scratch, so no run inherits another run's state."""
        with self._lock:
            existing = self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            self._connection.execute("PRAGMA foreign_keys = OFF")
            for row in existing:
                self._connection.execute(f'DROP TABLE IF EXISTS "{row["name"]}"')
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.executescript(SCHEMA)
            self._seed(self._connection)

    def _seed(self, conn: sqlite3.Connection) -> None:
        settings = self._settings
        token_expiry = self._clock.now() + 86_400.0

        conn.execute(
            "INSERT INTO shows (show_id, title, performance_date, venue, seats_allocated)"
            " VALUES (?, ?, ?, ?, ?)",
            (SHOW_ID, SHOW_TITLE, SHOW_DATE, "Alder Hall", settings.seats_allocated),
        )
        conn.executemany(
            "INSERT INTO seats (seat_id, show_id, seat_label) VALUES (?, ?, ?)",
            [
                (f"SEAT-{index:03d}", SHOW_ID, f"Stalls {index:03d}")
                for index in range(1, settings.seats_allocated + 1)
            ],
        )

        patrons: list[tuple[str, str, int, str]] = [
            (
                f"PATRON-{index:03d}",
                f"Demo Patron {index:03d}",
                settings.seat_quota_default,
                "fixture",
            )
            for index in range(1, GENUINE_PATRON_COUNT + 1)
        ]
        patrons.append(
            (
                HOUSEHOLD_PATRON_ID,
                "Demo Household Patron",
                settings.household_entitlement,
                "fixture",
            )
        )
        conn.executemany(
            "INSERT INTO patrons (patron_id, display_name, seat_entitlement, created_via)"
            " VALUES (?, ?, ?, ?)",
            patrons,
        )
        conn.executemany(
            "INSERT INTO tokens (token, patron_id, expires_at) VALUES (?, ?, ?)",
            [(demo_token(patron_id), patron_id, token_expiry) for patron_id, _, _, _ in patrons],
        )
        # One deliberately expired demo token, so the generic 401 contract is testable.
        conn.execute(
            "INSERT INTO tokens (token, patron_id, expires_at) VALUES (?, ?, ?)",
            (EXPIRED_TOKEN, "PATRON-001", self._clock.now() - 1.0),
        )
        conn.executemany(
            "INSERT INTO eligibility_refs (eligibility_ref, consumed_by) VALUES (?, NULL)",
            [(ref,) for ref in ELIGIBILITY_REFS],
        )
