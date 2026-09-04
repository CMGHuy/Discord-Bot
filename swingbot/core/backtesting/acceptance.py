"""The acceptance gate -- what a feature must prove before it ships on.

Read `docs/claude/backtest-methodology.md` before changing anything here.
The clause set and its constants are PRE-REGISTERED: they are the bar, and
a component that fails them is dropped and documented, never re-measured
against a bar moved to fit it.

Win rate is the objective; expectancy is a non-inferiority constraint. The
two move against each other along the *geometry* axis (break-even win rate
at reward:risk X is 1/(1+X), so a nearer target buys win rate and no
profit) and together only along the *discrimination* axis. Clause 3 exists
to force a feature onto the second axis.

numpy only -- scipy is NOT in requirements.txt and is absent from the
Docker image this module ships in.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

VERSION = 2   # acceptance-procedure version, recorded in every results doc


@dataclass(frozen=True)
class ArmTrade:
    """One trade in one arm, carrying exactly what the clauses read.

    Deliberately not BacktestTrade: that record has no ticker/strategy/
    horizon (they live on its BacktestSummary parent) and the measurement
    scripts each carry their own row dialect. This is the shared shape both
    adapt into.
    """
    ticker: str
    strategy: str
    horizon_key: str
    entry_date: str
    outcome: str                  # win | loss | scratch | timeout | not_triggered
    r_multiple: float | None
    planned_rr: float | None

    @property
    def key(self) -> tuple:
        """Pairing key across arms."""
        return (self.ticker, self.strategy, self.horizon_key, self.entry_date)

    @property
    def stratum(self) -> tuple:
        """Mix-standardisation and per-stratum reporting unit."""
        return (self.strategy, self.horizon_key)


def planned_rr(entry: float, stop: float, target: float) -> float | None:
    """Reward:risk as the plan was written, before the market answered.

    Direction-agnostic by construction (both legs are absolute), so a
    bearish plan and its mirror-image bullish plan return the same number.
    None on zero risk -- a plan that cannot lose cannot be priced.
    """
    risk = abs(entry - stop)
    if not risk:
        return None
    return abs(target - entry) / risk


def arm_trade_from_plan(plan, *, entry_date: str, outcome: str,
                        r_multiple: float | None) -> ArmTrade:
    """Adapt a TradePlanV2 (what replay_scenarios yields) plus its outcome."""
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    return ArmTrade(ticker=plan.ticker, strategy=plan.strategy,
                    horizon_key=plan.horizon_key, entry_date=entry_date,
                    outcome=outcome, r_multiple=r_multiple,
                    planned_rr=planned_rr(entry, plan.stop_loss, plan.tp1))


def arm_trade_from_backtest(trade, *, ticker: str, strategy: str,
                            horizon_key: str) -> ArmTrade:
    """Adapt a BacktestTrade. The three context fields live on the trade's
    BacktestSummary parent, not the trade, so the caller supplies them."""
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key=horizon_key,
                    entry_date=trade.entry_date, outcome=trade.outcome,
                    r_multiple=trade.r_multiple,
                    planned_rr=planned_rr(trade.entry, trade.stop_loss,
                                          trade.take_profit))


#: Outcomes that count toward the win-rate denominator.
DECIDED = ("win", "loss")
#: Outcomes that count as a closed trade for expectancy.
CLOSED = ("win", "loss", "scratch", "timeout")


def win_rate(trades) -> float | None:
    """Percent, over decided trades only. None when nothing was decided."""
    decided = [t for t in trades if t.outcome in DECIDED]
    if not decided:
        return None
    return 100.0 * sum(1 for t in decided if t.outcome == "win") / len(decided)


def expectancy_r(trades) -> float | None:
    """Mean R over all CLOSED trades -- scratches and timeouts drag it down,
    which is the point: they are capital that was committed and returned
    nothing."""
    rs = [t.r_multiple for t in trades
          if t.outcome in CLOSED and t.r_multiple is not None]
    if not rs:
        return None
    return float(np.mean(rs))


def _by_stratum(trades) -> dict:
    out = defaultdict(list)
    for t in trades:
        out[t.stratum].append(t)
    return out


def stratum_weights(trades) -> dict:
    """Share of DECIDED trades in each (strategy, horizon) stratum."""
    counts = Counter(t.stratum for t in trades if t.outcome in DECIDED)
    total = sum(counts.values())
    if not total:
        return {}
    return {k: v / total for k, v in counts.items()}


def standardised_win_rate(trades, weights: dict) -> float | None:
    """The win rate this arm would show if its stratum mix matched
    `weights` -- i.e. holding composition fixed so only within-stratum
    skill can move the number.

    Strata the arm has no decided trade in are dropped and the remaining
    weights renormalised, rather than imputed: an arm that emptied a
    stratum has no win rate there to standardise, and inventing one would
    reward exactly the mix shift this function exists to neutralise.
    """
    grouped = _by_stratum(trades)
    total = 0.0
    weight_sum = 0.0
    for stratum, weight in weights.items():
        wr = win_rate(grouped.get(stratum, []))
        if wr is None:
            continue
        total += weight * wr
        weight_sum += weight
    if not weight_sum:
        return None
    return total / weight_sum


def stratum_table(baseline, component) -> list:
    """One row per stratum present in EITHER arm, sorted for stable output."""
    b, c = _by_stratum(baseline), _by_stratum(component)
    rows = []
    for stratum in sorted(set(b) | set(c)):
        bt, ct = b.get(stratum, []), c.get(stratum, [])
        rows.append({
            "stratum": stratum,
            "baseline_n": sum(1 for t in bt if t.outcome in DECIDED),
            "component_n": sum(1 for t in ct if t.outcome in DECIDED),
            "baseline_win_rate": win_rate(bt),
            "component_win_rate": win_rate(ct),
            "baseline_expectancy_r": expectancy_r(bt),
            "component_expectancy_r": expectancy_r(ct),
        })
    return rows


#: Pre-registered. 10k resamples resolves a one-sided p at the 0.05 bar with
#: room to spare; tests override it downward for speed, never a real run.
BOOTSTRAP_RESAMPLES = 10_000
ALPHA = 0.05


@dataclass(frozen=True)
class BootstrapResult:
    point: float | None
    lo: float | None
    hi: float | None
    p_greater_than_zero: float | None
    n_resamples: int
    seed: int


def delta_standardised_win_rate(baseline, component) -> float | None:
    """ΔWR in percentage points, holding the BASELINE's stratum mix fixed.

    Standardising to the baseline (not the component, not the pool) is the
    choice that makes the number mean 'what this feature did to the book we
    already have'.
    """
    weights = stratum_weights(baseline)
    b = standardised_win_rate(baseline, weights)
    c = standardised_win_rate(component, weights)
    if b is None or c is None:
        return None
    return c - b


def delta_expectancy_r(baseline, component) -> float | None:
    b, c = expectancy_r(baseline), expectancy_r(component)
    if b is None or c is None:
        return None
    return c - b


def _group_by_ticker(trades) -> dict:
    out = defaultdict(list)
    for t in trades:
        out[t.ticker].append(t)
    return out


def cluster_bootstrap(baseline, component, statistic, *,
                      n_resamples: int = BOOTSTRAP_RESAMPLES,
                      seed: int = 42) -> np.ndarray:
    """Resample TICKERS with replacement, recomputing `statistic` on each
    draw. Both arms are resampled with the SAME ticker draw, so the pairing
    between arms survives -- resampling them independently would break the
    very comparison being measured.

    Draws where the statistic is undefined (an arm with no decided trade)
    are dropped, not zero-filled: a missing statistic is missing data, and
    zero is a specific, wrong claim about it.
    """
    b_by, c_by = _group_by_ticker(baseline), _group_by_ticker(component)
    tickers = sorted(set(b_by) | set(c_by))
    if not tickers:
        return np.array([])
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(tickers), size=(n_resamples, len(tickers)))
    out = []
    for row in picks:
        b_draw, c_draw = [], []
        for j in row:
            name = tickers[j]
            b_draw.extend(b_by.get(name, ()))
            c_draw.extend(c_by.get(name, ()))
        value = statistic(b_draw, c_draw)
        if value is not None:
            out.append(value)
    return np.asarray(out, dtype=float)


def bootstrap_delta(baseline, component, statistic, *,
                    n_resamples: int = BOOTSTRAP_RESAMPLES,
                    seed: int = 42) -> BootstrapResult:
    """Point estimate on the real data, interval and one-sided p from the
    ticker-cluster bootstrap.

    `p_greater_than_zero` is the share of draws at or below zero -- the
    bootstrap reading of 'could this delta have been no improvement at
    all'.
    """
    point = statistic(baseline, component)
    draws = cluster_bootstrap(baseline, component, statistic,
                              n_resamples=n_resamples, seed=seed)
    if point is None or draws.size == 0:
        return BootstrapResult(point, None, None, None, n_resamples, seed)
    lo, hi = (float(np.percentile(draws, 100 * ALPHA / 2)),
              float(np.percentile(draws, 100 * (1 - ALPHA / 2))))
    p = float(np.mean(draws <= 0.0))
    return BootstrapResult(float(point), lo, hi, p, n_resamples, seed)


MDE_POWER = 0.80

#: Standard normal quantiles, hardcoded because scipy is NOT in
#: requirements.txt and this module ships in the Docker image.
#: z(1-0.05) = 1.6449 (one-sided alpha), z(0.80) = 0.8416 (power).
_Z_ALPHA_ONE_SIDED = {0.05: 1.6449, 0.01: 2.3263, 0.10: 1.2816}
_Z_POWER = {0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449}


def intracluster_correlation(trades) -> float:
    """ICC of the win indicator, grouped by ticker, by the one-way ANOVA
    estimator. Clamped to [0, 1] -- a negative estimate is sampling noise
    around zero, and letting it through would shrink the design effect
    below 1 and overstate power, the exact error this exists to prevent.
    """
    grouped = _group_by_ticker([t for t in trades if t.outcome in DECIDED])
    groups = [[1.0 if t.outcome == "win" else 0.0 for t in g]
              for g in grouped.values() if g]
    k = len(groups)
    n_total = sum(len(g) for g in groups)
    if k < 2 or n_total <= k:
        return 0.0
    grand = float(np.mean([v for g in groups for v in g]))
    ms_between = sum(len(g) * (float(np.mean(g)) - grand) ** 2
                     for g in groups) / (k - 1)
    ms_within = sum((v - float(np.mean(g))) ** 2
                    for g in groups for v in g) / (n_total - k)
    # Mean cluster size, ANOVA-corrected for unequal sizes.
    m0 = (n_total - sum(len(g) ** 2 for g in groups) / n_total) / (k - 1)
    if m0 <= 0 or (ms_between + (m0 - 1) * ms_within) == 0:
        return 0.0
    icc = (ms_between - ms_within) / (ms_between + (m0 - 1) * ms_within)
    return float(min(1.0, max(0.0, icc)))


def design_effect(trades) -> float:
    """DEFF = 1 + (mean cluster size - 1) * ICC. The factor by which
    clustering inflates the variance over the independent-sample formula.
    """
    decided = [t for t in trades if t.outcome in DECIDED]
    grouped = _group_by_ticker(decided)
    if not grouped:
        return 1.0
    mean_size = len(decided) / len(grouped)
    return 1.0 + (mean_size - 1.0) * intracluster_correlation(decided)


def mde_win_rate(population, *, target_n: int, power: float = MDE_POWER,
                 alpha: float = ALPHA) -> float | None:
    """Smallest ΔWR, in percentage points, detectable at `power` with a
    one-sided test at `alpha`, given `target_n` decided trades per arm and
    the clustering `population` exhibits.

    A TRAIN effect smaller than this is not a small edge -- it is an
    unanswerable question, and firing a one-shot budget at it wastes the
    shot whatever the answer comes back as.
    """
    decided = [t for t in population if t.outcome in DECIDED]
    if not decided or target_n <= 0:
        return None
    p = win_rate(decided) / 100.0
    z_a = _Z_ALPHA_ONE_SIDED.get(alpha)
    z_b = _Z_POWER.get(power)
    if z_a is None or z_b is None:
        raise ValueError(f"no tabulated z for alpha={alpha}, power={power}")
    n_eff = target_n / design_effect(decided)
    if n_eff <= 0:
        return None
    return 100.0 * (z_a + z_b) * float(np.sqrt(2.0 * p * (1.0 - p) / n_eff))


def project_target_n(*, observed_n: int, observed_days: int,
                     target_days: int) -> int:
    """Project achievable N by window length, from a window we are allowed
    to look at. Reading a count out of 2024-25 to size a run is still
    contact with the validation window."""
    if observed_days <= 0:
        return 0
    return int(round(observed_n * target_days / observed_days))
