"""ASGI entry point for the **vulnerable** application.

This application deliberately has no anti-automation on a sensitive business flow. It exists to be
drained, on a loopback-only, egress-less network, so the mechanism is legible. It is local
educational material and must never be deployed.

Reaching it takes **two deliberate actions**, and both are required:

1. enable the opt-in Compose profile ``vulnerable``; and
2. set ``ALLOW_VULNERABLE_DEMO=true``.

The gate lives here, on the deployable entry point, rather than in :func:`flowjack.app.create_app`.
That is the right boundary: the library must stay constructible so the regression suite can pin
what the vulnerable shapes actually do, while the thing that can be *started and served* stays
behind the acknowledgement.

There is deliberately no module-level ``app``. The service is started through uvicorn's factory
mode::

    uvicorn flowjack.vulnerable_app:create_vulnerable_app --factory

so the acknowledgement is checked when the server tries to build the application — importing this
module to read or test it never constructs one.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from flowjack.app import create_app
from flowjack.policy import VULNERABLE_NONE, VULNERABLE_POLICIES, Policy

ACKNOWLEDGEMENT_ENV = "ALLOW_VULNERABLE_DEMO"
POLICY_ENV = "FLOWJACK_POLICY"

_REFUSAL = (
    "Refusing to start the deliberately vulnerable flowjack application.\n"
    f"Set {ACKNOWLEDGEMENT_ENV}=true and enable the 'vulnerable' Compose profile to run it.\n"
    "It is local educational material with no anti-automation on a sensitive business flow, "
    "and must never be deployed."
)


class VulnerableDemoNotAcknowledgedError(RuntimeError):
    """Raised when the vulnerable entry point is started without the explicit acknowledgement."""


class UnknownVulnerableShapeError(RuntimeError):
    """Raised when FLOWJACK_POLICY names something that is not a vulnerable shape."""


def acknowledged() -> bool:
    return os.environ.get(ACKNOWLEDGEMENT_ENV, "").strip().lower() == "true"


def selected_policy() -> Policy:
    """Read the vulnerable shape from ``FLOWJACK_POLICY``.

    Only a vulnerable shape may be selected here. Asking this entry point for the secure
    application is a configuration mistake, not a shortcut, and is refused.
    """
    name = os.environ.get(POLICY_ENV, "").strip()
    if not name:
        return VULNERABLE_NONE
    for policy in VULNERABLE_POLICIES:
        if policy.name == name:
            return policy
    known = ", ".join(policy.name for policy in VULNERABLE_POLICIES)
    raise UnknownVulnerableShapeError(
        f"{POLICY_ENV}={name!r} is not a vulnerable shape. Known shapes: {known}."
    )


def create_vulnerable_app(policy: Policy | None = None) -> FastAPI:
    if not acknowledged():
        raise VulnerableDemoNotAcknowledgedError(_REFUSAL)
    return create_app(policy=policy if policy is not None else selected_policy())
