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
    standing in for the binomial variance term.

    KNOWN LIMITATION (flagged, not fixed -- see docs/claude/backtest-
    methodology.md's "Harvest acceptance gate" section): this formula is
    an UNPAIRED-design MDE -- sqrt(2*var(r)/n_eff), appropriate for two
    independent populations. Both H1 and H2 (v92) are paired, exit-only
    designs (the same entries replayed under two exit rules), for which
    the relevant variance is the variance of the per-trade CHANGE in R,
    not the variance of R itself -- typically far smaller than what this
    formula assumes, so the MDE it reports is likely overstated for that
    design. This is a defect in the spec's own Stage 0 instruction (v92
    §3), not an implementation bug, and is deliberately NOT being changed
    here. A future harvest spec relying on Stage 0 to rule out small
    effects should first derive a paired variant (variance of the
    per-trade R delta) before citing this function's output as a bound."""
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
    # BOTH conditions of the pre-registration, not just p: res.lo is the
    # bootstrap's 2.5th percentile, so lo > 0 implies p < 0.025 -- but the
    # inverse doesn't hold. Checking p alone would silently accept a draw
    # with 0.025 <= p < 0.05 whose lower tail still crosses zero.
    ok = (res.point > 0.0 and res.lo is not None and res.lo > 0.0
          and res.p_greater_than_zero < ALPHA)
    return ClauseResult(
        "expectancy_gain", "PASS" if ok else "FAIL",
        f"dExpR {res.point:+.4f}R [{res.lo:+.4f},{res.hi:+.4f}] "
        f"p={res.p_greater_than_zero:.4f}", res.point, 0.0)


def _clause_win_rate_floor(baseline, component, n_resamples, seed, *,
                          structurally_immune: bool = False,
                          split: dict | None = None) -> ClauseResult:
    """The floor clause: standardised WR may not fall by more than
    WIN_RATE_FLOOR_PP. A mechanism that only touches behaviour after the
    win/loss decision (e.g. the runner leg, post-TP1) cannot move WR at
    all -- pass structurally_immune=True to report that fact instead of
    bootstrapping a quantity with zero variance.

    The immunity claim is verified, not trusted blindly: with
    `one_at_a_time=True` in the backtest harness, a runner-leg exit that
    changes timing COULD change which later entries fire for the same
    ticker, so 'this hypothesis is exit-only' does not by itself guarantee
    'WR cannot move'. `population_split` (reused from `evaluate_harvest`
    when the caller already computed it, to avoid doing it twice) must
    show no added, removed or changed trades before the claim is honoured.
    If the populations differ despite `structurally_immune=True`, this
    falls through to a real bootstrap instead of reporting SKIPPED on
    a false premise."""
    if structurally_immune:
        if split is None:
            split = population_split(baseline, component)
        immunity_confirmed = not split["added"] and not split["removed"] and not split["changed"]
        if immunity_confirmed:
            return ClauseResult("win_rate_floor", "SKIPPED",
                                "mechanism acts only after the win/loss decision "
                                "(post-TP1) -- win rate cannot move by construction",
                                0.0, WIN_RATE_FLOOR_PP)
        # Claimed immunity does not hold: the two arms' trade populations
        # actually differ (added/removed/changed), so fall through and
        # bootstrap for real rather than trusting the claim.
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


def evaluate_harvest(baseline, component, *, stage: str,
                    structurally_immune_to_wr: bool = False,
                    permutation_p: float | None = None,
                    n_resamples: int = BOOTSTRAP_RESAMPLES,
                    seed: int = 42) -> AcceptanceResult:
    """The harvest gate. Every applicable clause must PASS.

    No `mechanism` clause (v72 clause 6) -- these hypotheses don't remove
    trades, they change how already-accepted trades exit, so there is no
    removed population to interrogate. The caller's results doc should
    instead report the win->non-win outcome-flip count from
    population_split(baseline, component)['changed'] as a disclosure table
    (informational, not gating -- expectancy_gain already prices in
    whatever those flips cost or bought)."""
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}, got {stage!r}")
    split = population_split(baseline, component)
    clauses = (
        _clause_expectancy_gain(baseline, component, n_resamples, seed),
        _clause_win_rate_floor(baseline, component, n_resamples, seed,
                              structurally_immune=structurally_immune_to_wr,
                              split=split),
        _clause_volume(baseline, component),
        _clause_permutation(stage, permutation_p),
    )
    verdict = "FAIL" if any(c.verdict == "FAIL" for c in clauses) else "PASS"
    return AcceptanceResult(stage=stage, verdict=verdict, clauses=clauses,
                            strata=stratum_table(baseline, component),
                            split={k: len(v) if isinstance(v, list) else v
                                   for k, v in split.items()},
                            seed=seed, version=HARVEST_VERSION)
