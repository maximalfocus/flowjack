"""Fixed, checked-in fixtures for the automation harness.

Everything the harness distributes across is enumerated here, in source, and never generated,
discovered, or rotated at scale. That is a deliberate boundary: this project demonstrates a design
defect using requests the API is built to accept, and needs no capability for obtaining identities
or network positions that were not handed to it.
"""

from __future__ import annotations

from flowjack.db import ELIGIBILITY_REFS, GENUINE_PATRON_COUNT

#: Stand-ins for distinct network origins. The application receives these in an explicit request
#: header (:data:`SOURCE_HEADER`) rather than from a socket, so the demo needs no proxy, network
#: namespace, or address-spoofing machinery to show a per-source limit counting the wrong thing.
SOURCE_HEADER = "X-Demo-Source"

OPERATOR_SOURCE_LABELS: tuple[str, ...] = (
    "src-alpha",
    "src-bravo",
    "src-charlie",
    "src-delta",
    "src-echo",
    "src-foxtrot",
    "src-golf",
    "src-hotel",
)

GENUINE_SOURCE_LABEL = "src-public"

#: Eligibility references the operator presents when registering. The first four are the ones the
#: venue actually issued; the rest are invented and must be refused. Sixty candidates in total,
#: which is what it would take to drain a 120-seat allocation two seats at a time.
OPERATOR_ELIGIBILITY_CANDIDATES: tuple[str, ...] = (
    *ELIGIBILITY_REFS,
    *(f"ALDER-MEMBER-{9000 + index}" for index in range(1, 57)),
)

#: The genuine patrons seeded by the application, and how many seats each of them wants.
GENUINE_PATRON_IDS: tuple[str, ...] = tuple(
    f"PATRON-{index:03d}" for index in range(1, GENUINE_PATRON_COUNT + 1)
)
GENUINE_SEATS_EACH = 2
