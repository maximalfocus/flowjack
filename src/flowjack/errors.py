"""The single refusal type, and the single refusal response.

Every reason the secure application declines a flow — the show is sold out, this patron's
entitlement is used, this flow was never legitimately entered, the identity-supply limit is
reached — raises the *same* exception and produces the *same* client-visible response.

That is not tidiness. A caller who can tell "sold out" from "your entitlement is used" has an
oracle: it can probe the venue's remaining stock, or discover exactly where a limit sits, without
being entitled to either fact. The reason is recorded nowhere the client can reach it.
"""

from __future__ import annotations

from typing import Final

from flowjack.audit import RequestStep

#: The one body every refusal returns, byte for byte.
REFUSAL_DETAIL: Final = "This request could not be completed."

#: The one status code every refusal returns.
REFUSAL_STATUS: Final = 409


#: A verification challenge is required. Distinct from a flow-limit refusal on purpose: this is a
#: conventional, advertised control that tells the caller exactly what to go and do.
VERIFICATION_REQUIRED_STATUS: Final = 403
VERIFICATION_REQUIRED_DETAIL: Final = "Human verification is required for this step."


class RateLimitedError(Exception):
    """A per-source request rate limit declined this request.

    Not a flow limit. It is here so the demonstration can show one holding perfectly while the
    allocation drains past it.
    """


class VerificationRequiredError(Exception):
    """A verification gate declined this request for want of a token.

    Nothing in this project attempts to defeat, solve, replay, or machine-answer the token. The
    shape being demonstrated is *where* the gate sits, not how strong it is.
    """


class FlowLimitRefusedError(Exception):
    """A flow limit declined this request.

    ``step`` and ``patron_id`` are carried only so the audit event can be written; they never
    reach the client.
    """

    def __init__(
        self,
        *,
        step: RequestStep,
        show_id: str | None = None,
        patron_id: str | None = None,
    ) -> None:
        super().__init__(REFUSAL_DETAIL)
        self.step = step
        self.show_id = show_id
        self.patron_id = patron_id
