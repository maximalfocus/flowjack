"""ASGI entry point for the **secure** application.

The secure variant is the default service. Vulnerable variants arrive in a later slice behind an
opt-in Compose profile and an explicit acknowledgement; none exists yet.
"""

from __future__ import annotations

from flowjack.app import create_app

app = create_app()
