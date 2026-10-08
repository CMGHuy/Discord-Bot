"""The v140 screen's verdict (spec § The verdict).

Per kept event d = R_event - mean(R_null). All four hold -> SCREEN-PASS:
(1) mean(d) >= +0.10R; (2) lower 95% bound > 0, week-clustered bootstrap
over ISO entry weeks, 10,000 resamples, seed 42; (3) mean(d) > 0 in >= 7
of the 9 calendar years 2011..2019 (F14), an empty year counting against;
(4) N >= 300. N < 300 -> SCREEN-UNDERPOWERED. Otherwise SCREEN-FAIL.

The bootstrap is fed one WeekSum per ISO week (reading F5): identical draws
to one object per event with statistic mean(d), at a fraction of the cost.
The p reported to the ledger is the share of resamples <= 0 (reading F6).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from swingbot.core.backtesting.instrument import stats

PASS_EXP_R = 0.10
MIN_N = 300
MIN_POSITIVE_YEARS = 7
YEARS = tuple(range(2011, 2020))
SCREEN_PASS = "SCREEN-PASS"
SCREEN_FAIL = "SCREEN-FAIL"
SCREEN_UNDERPOWERED = "SCREEN-UNDERPOWERED"
_TOLERANCE = 1e-12    # mean([0.1] * n) may land one ulp under 0.1


@dataclass(frozen=True)
class PairedEvent:
    entry_date: str   # entry bar t+1 (frozen reading F9)
    d: float


@dataclass(frozen=True)
class WeekSum:
    entry_date: str
    total: float
    n: int


@dataclass(frozen=True)
class Verdict:
    verdict: str
    n: int
    delta_exp_r: float | None
    ci_low: float | None
    ci_high: float | None
    p: float | None
    years_positive: int
    per_year: dict
    clauses: dict


def mean_d(_baseline, component) -> float | None:
    values = [event.d for event in component]
    return float(np.mean(values)) if values else None


def week_sums(events) -> list:
    return [WeekSum(group[0].entry_date, float(sum(e.d for e in group)), len(group))
            for group in stats.group_by_week(events).values()]


def pooled_mean(_baseline, weeks) -> float | None:
    n = sum(week.n for week in weeks)
    return sum(week.total for week in weeks) / n if n else None


def per_year(events, years=YEARS) -> dict:
    table = {year: [] for year in years}
    for event in events:
        year = int(event.entry_date[:4])
        if year in table:
            table[year].append(event.d)
    return {year: (len(v), float(np.mean(v)) if v else None) for year, v in table.items()}


def years_positive(table) -> int:
    return sum(1 for n, mean in table.values() if n and mean is not None and mean > 0)


def mean_clause(delta) -> bool:
    return delta is not None and delta >= PASS_EXP_R - _TOLERANCE


def ci_clause(low) -> bool:
    return low is not None and low > 0


def years_clause(count: int) -> bool:
    return count >= MIN_POSITIVE_YEARS


def n_clause(n: int) -> bool:
    return n >= MIN_N


def bootstrap(events, *, n_resamples: int, seed: int):
    """(lower 2.5%, upper 97.5%, one-sided p) of mean(d), or Nones."""
    draws = stats.week_cluster_bootstrap([], week_sums(events), pooled_mean,
                                         n_resamples=n_resamples, seed=seed)
    if draws.size == 0:
        return None, None, None
    return (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)),
            float(np.mean(draws <= 0.0)))


def label(clauses: dict) -> str:
    if not clauses["n"]:
        return SCREEN_UNDERPOWERED
    return SCREEN_PASS if all(clauses.values()) else SCREEN_FAIL


def decide(events, *, n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES,
           seed: int = stats.WEEK_BOOTSTRAP_SEED) -> Verdict:
    events = list(events)
    delta = mean_d([], events)
    low, high, p = bootstrap(events, n_resamples=n_resamples, seed=seed)
    table = per_year(events)
    positive = years_positive(table)
    clauses = {"exp_r": mean_clause(delta), "ci": ci_clause(low),
               "years": years_clause(positive), "n": n_clause(len(events))}
    return Verdict(label(clauses), len(events), delta, low, high, p, positive,
                   table, clauses)
