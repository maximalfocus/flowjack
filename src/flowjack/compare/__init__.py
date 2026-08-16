"""The comparison: every scenario, side by side, on one screen.

Each scenario already runs on its own. What this adds is the view where the point is unmissable —
one row per shape, with the operator's share of the allocation next to the count of requests that
were individually invalid. The second column is zero in every row, including the rows where the
operator took everything.
"""

from flowjack.compare.engine import (
    DEFAULT_TARGETS,
    ComparisonRow,
    ComparisonTarget,
    run_comparison,
)
from flowjack.compare.report import render

__all__ = [
    "DEFAULT_TARGETS",
    "ComparisonRow",
    "ComparisonTarget",
    "render",
    "run_comparison",
]
