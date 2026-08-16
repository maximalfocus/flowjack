"""Request and response bodies.

Both application variants expose identical paths, request bodies, and success payloads. Later
slices add the vulnerable variants; the only thing that will differ between them and this one is
which limits govern the flow.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegistrationRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    eligibility_ref: str | None = Field(default=None, max_length=64)


class RegistrationResponse(BaseModel):
    patron_id: str
    display_name: str
    seat_entitlement: int
    token: str


class HoldResponse(BaseModel):
    hold_id: str
    show_id: str
    seat_id: str
    seat_label: str
    expires_at: float


class TicketResponse(BaseModel):
    ticket_id: str
    hold_id: str
    show_id: str
    seat_id: str
    seat_label: str


class ShowResponse(BaseModel):
    show_id: str
    title: str
    venue: str
    performance_date: str
    seats_allocated: int
    seats_held: int
    seats_confirmed: int
    seats_available: int


class PatronHolding(BaseModel):
    patron_id: str
    created_via: str
    seats_held: int
    seats_confirmed: int


class AllocationResponse(BaseModel):
    """The venue's own reconciliation surface.

    This is a demonstration affordance: it exists so every outcome the walkthrough claims can be
    read back through the product's own boundary instead of by inspecting the database. A real
    ticketing service would not publish a per-patron breakdown.
    """

    show_id: str
    seats_allocated: int
    seats_held: int
    seats_confirmed: int
    seats_available: int
    holdings: list[PatronHolding]
