"""Harvest acceptance gate (v92) -- expectancy-primary, win-rate-floor.

Read docs/claude/backtest-methodology.md's "Harvest acceptance gate" section
before changing anything here. `Edge: harvest` features are out of scope for
the v72 funnel (acceptance.py) by design -- its clause 3 (geometry lock)
rejects any exit/target/sizing change on sight, because that clause exists
to stop a *selectivity* feature from buying win rate by pulling targets
nearer, a different failure mode than a harvest feature's.

Win rate and expectancy swap roles versus v72: expectancy is the objective,
win rate a floor -- the inversion the methodology doc itself names as
legitimate. Reuses acceptance.py's ArmTrade / cluster-bootstrap /
population_split machinery wholesale; only the clause set differs.

numpy only -- scipy is NOT in requirements.txt.
"""
from __future__ import annotations

import numpy as np

from .acceptance import (
    ArmTrade, CLOSED, DECIDED, win_rate, expectancy_r,
    delta_expectancy_r, delta_standardised_win_rate,
    cluster_bootstrap, bootstrap_delta, BootstrapResult, ClauseResult,
    AcceptanceResult, population_split, stratum_table, design_effect,
    _clause_volume, _clause_permutation, render_markdown,
    BOOTSTRAP_RESAMPLES, ALPHA, _Z_ALPHA_ONE_SIDED, _Z_POWER, STAGES,
)

__all__ = [
    "HARVEST_VERSION", "WIN_RATE_FLOOR_PP", "mde_expectancy_r",
    "evaluate_harvest", "render_markdown",
]

HARVEST_VERSION = 1

#: PRE-REGISTERED gate constant. Changing it is a new pre-registration, not
#: a tuning step -- mirrors v72's GEOMETRY_MAX_DROP_PCT=2.0 tolerance for
#: "how much secondary-axis slip is acceptable" (see spec S3).
WIN_RATE_FLOOR_PP = -2.0


def mde_expectancy_r(population, *, target_n: int, power: float = 0.80,
                     alpha: float = ALPHA) -> float | None:
    """Smallest ΔExpR detectable at `power` with a one-sided test at
    `alpha`, given `target_n` closed trades per arm and the clustering
    `population` exhibits. Same z-score/design-effect math as
    acceptance.mde_win_rate, with the sample variance of `r_multiple`
    standing in for the binomial variance term."""
    closed = [t for t in population if t.outcome in CLOSED and t.r_multiple is not None]
    if not closed or target_n <= 0:
        return None
    z_a = _Z_ALPHA_ONE_SIDED.get(alpha)
    z_b = _Z_POWER.get(power)
    if z_a is None or z_b is None:
        raise ValueError(f"no tabulated z for alpha={alpha}, power={power}")
    variance = float(np.var([t.r_multiple for t in closed], ddof=1))
    n_eff = target_n / design_effect(closed)
    if n_eff <= 0:
        return None
    return float((z_a + z_b) * np.sqrt(2.0 * variance / n_eff))


def _clause_expectancy_gain(baseline, component, n_resamples, seed) -> ClauseResult:
    """The objective clause: ExpR must IMPROVE, not merely hold -- the
    inverse of v72 clause 2's non-inferiority floor, because for
    Edge:harvest work expectancy is what the feature exists to buy."""
    res = bootstrap_delta(baseline, component, delta_expectancy_r,
                          n_resamples=n_resamples, seed=seed)
    if res.point is None or res.p_greater_than_zero is None:
        return ClauseResult("expectancy_gain", "FAIL",
                            "no closed trades in one arm", None, 0.0)
    ok = res.point > 0.0 and res.p_greater_than_zero < ALPHA
    return ClauseResult(
        "expectancy_gain", "PASS" if ok else "FAIL",
        f"dExpR {res.point:+.4f}R [{res.lo:+.4f},{res.hi:+.4f}] "
        f"p={res.p_greater_than_zero:.4f}", res.point, 0.0)


def _clause_win_rate_floor(baseline, component, n_resamples, seed, *,
                          structurally_immune: bool = False) -> ClauseResult:
    """The floor clause: standardised WR may not fall by more than
    WIN_RATE_FLOOR_PP. A mechanism that only touches behaviour after the
    win/loss decision (e.g. the runner leg, post-TP1) cannot move WR at
    all -- pass structurally_immune=True to report that fact instead of
    bootstrapping a quantity with zero variance."""
    if structurally_immune:
        return ClauseResult("win_rate_floor", "PASS",
                            "mechanism acts only after the win/loss decision "
                            "(post-TP1) -- win rate cannot move by construction",
                            0.0, WIN_RATE_FLOOR_PP)
    res = bootstrap_delta(baseline, component, delta_standardised_win_rate,
                          n_resamples=n_resamples, seed=seed)
    if res.point is None or res.lo is None:
        return ClauseResult("win_rate_floor", "FAIL",
                            "no decided trades in one arm", None, WIN_RATE_FLOOR_PP)
    ok = res.lo >= WIN_RATE_FLOOR_PP
    return ClauseResult(
        "win_rate_floor", "PASS" if ok else "FAIL",
        f"standardised dWR {res.point:+.2f}pp, lower bound {res.lo:+.2f}pp "
        f"vs floor {WIN_RATE_FLOOR_PP:+.2f}pp", res.lo, WIN_RATE_FLOOR_PP)
