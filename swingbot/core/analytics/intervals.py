"""v219: confidence intervals for the shares the admin analytics tabs show.

Pure functions, no I/O. The live book is small, so a share is shown with
its interval rather than alone; nothing here is a gate.
"""
from __future__ import annotations

from math import sqrt


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for `k` successes in `n` trials, as fractions in
    [0, 1] (z = 1.96 is 95%). None when there are no trials, so an empty
    group reads as "no share" instead of failing the report."""
    if n < 1:
        return None
    if not 0 <= k <= n:
        raise ValueError(f"successes {k} outside 0..{n}")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    # The exact ends are pinned: in floats centre - half drifts to ~1e-17 at
    # k == 0 (n = 11, 22, 27) and centre + half to 0.9999999999999999 at k == n.
    lo = 0.0 if k == 0 else max(0.0, centre - half)
    hi = 1.0 if k == n else min(1.0, centre + half)
    return (lo, hi)
