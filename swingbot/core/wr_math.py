"""Shared win-rate arithmetic, so no consumer re-derives it.

Lived at `core/gate/wr_math.py` until the 2026-08-06 gate removal. It was
never gate logic -- it is pure statistics, and `scripts/live_cohort_report.py`
(V29's monitoring harness) still depends on it -- so it was moved here rather
than deleted with the tree.

Golden numbers (hand-derived, mirrored in tests):
- breakeven_wr(1.5) = 100/(1+1.5) = 40.0
- implied_expectancy(95, 1.5) = 0.95*1.5 - 0.05*1.0 = +1.375R
- required_filter_precision(85, 95) = 1 - (85*5)/(95*15) = 0.7018
- wilson_lower_bound uses the CONTINUITY-CORRECTED Wilson interval
  (Newcombe 1998). The plain Wilson bound gives 35/35 -> 0.901 which
  would falsely "prove" 90% from 35 trades; the corrected bound gives
  35/35 -> 0.877 and 59/59 -> 0.924, which is the conservatism the
  95%-label rule is built on.
"""
import math


def breakeven_wr(rr: float) -> float:
    """WR (percent) where expectancy = 0 for a fixed reward:risk ratio."""
    return 100.0 / (1.0 + rr)


def implied_expectancy(wr_pct: float, avg_win_r: float, avg_loss_r: float = 1.0) -> float:
    """Expectancy in R implied by a WR and average win/loss sizes."""
    p = wr_pct / 100.0
    return p * avg_win_r - (1.0 - p) * avg_loss_r


def required_filter_precision(base_wr: float, target_wr: float) -> float:
    """Fraction of losers a filter must remove (keeping every winner)
    to lift base_wr to target_wr. Derivation: keep W winners, remove
    fraction f of L losers; W/(W+L(1-f)) = t  =>  f = 1 - (b(100-t))/(t(100-b))
    with b, t as percentages."""
    b, t = base_wr, target_wr
    return 1.0 - (b * (100.0 - t)) / (t * (100.0 - b))


def wilson_lower_bound(wins: int, n: int, z: float = 1.96) -> float:
    """Continuity-corrected Wilson score lower bound — the WR (as a
    fraction) a sample actually *proves* at ~95% confidence. Returns 0.0
    for n == 0 or wins == 0."""
    if n == 0 or wins == 0:
        return 0.0
    p = wins / n
    num = (
        2 * n * p + z * z - 1
        - z * math.sqrt(z * z - 2 - 1 / n + 4 * p * (n * (1 - p) + 1))
    )
    return max(0.0, num / (2 * (n + z * z)))
