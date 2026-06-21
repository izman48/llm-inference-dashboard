"""Tiny shared stats helpers (kept pure and dependency-free)."""

from __future__ import annotations

import math
from collections.abc import Sequence


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile. Returns 0.0 for an empty input."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]
