"""Runtime configuration for the flowjack demo.

Every limit the secure application enforces is expressed here as a named, documented,
environment-overridable value, so the walkthrough and the tests can state exactly which ceiling
they are exercising.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

SHOW_ID = "SHOW-2026-11-07"
SHOW_TITLE = "the Meridian Quartet"
SHOW_DATE = "2026-11-07"
VENUE_NAME = "Alder Hall"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:  # pragma: no cover - defensive, surfaced at startup
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise ValueError(f"{name} must not be negative, got {value}")
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:  # pragma: no cover - defensive, surfaced at startup
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Documented ceilings for the secure application.

    ``seats_allocated``
        The show's public seat allocation.
    ``seat_quota_default``
        Strategy A. Seats — not requests — a single patron may hold or own for one show.
    ``household_entitlement``
        The documented higher entitlement a household patron carries. It exists so the
        demonstration can prove that a flow limit is not a blanket throttle.
    ``hold_ttl_seconds``
        How long an unconfirmed hold survives. Short by design so the walkthrough observes real
        expiry inside its time budget instead of waiting out a venue-realistic window.
    ``rehold_allowance``
        Strategy A. How many times an expired hold returns entitlement to its patron. Beyond this
        bound, expired holds keep consuming entitlement, which is what stops hold-and-abandon
        denial from being free.
    ``self_service_registration_cap``
        Strategy B. Total self-service registrations the venue will grant, independent of how many
        eligibility references are still unconsumed.
    """

    seats_allocated: int = 120
    seat_quota_default: int = 2
    household_entitlement: int = 4
    hold_ttl_seconds: float = 600.0
    rehold_allowance: int = 1
    self_service_registration_cap: int = 3
    database_path: str = ":memory:"

    @property
    def operator_seat_ceiling(self) -> int:
        """Seats an automated operator can reach through governed identity supply alone."""
        return self.self_service_registration_cap * self.seat_quota_default


def load_settings() -> Settings:
    return Settings(
        seats_allocated=_env_int("FLOWJACK_SEATS_ALLOCATED", 120),
        seat_quota_default=_env_int("FLOWJACK_SEAT_QUOTA_DEFAULT", 2),
        household_entitlement=_env_int("FLOWJACK_HOUSEHOLD_ENTITLEMENT", 4),
        hold_ttl_seconds=_env_float("FLOWJACK_HOLD_TTL_SECONDS", 600.0),
        rehold_allowance=_env_int("FLOWJACK_REHOLD_ALLOWANCE", 1),
        self_service_registration_cap=_env_int("FLOWJACK_SELF_SERVICE_REGISTRATION_CAP", 3),
        database_path=os.environ.get("FLOWJACK_DB_PATH", ":memory:"),
    )
