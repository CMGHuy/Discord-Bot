"""The v140 screen's verdict (spec § The verdict).

Per kept event d = R_event - mean(R_null). All four hold -> SCREEN-PASS:
(1) mean(d) >= +0.10R; (2) lower 95% bound > 0, week-clustered bootstrap
over ISO entry weeks, 10,000 resamples, seed 42; (3) mean(d) > 0 in >= 7
of the 9 calendar years 2011..2019 (F14), an empty year counting against;
(4) N >= 300. N < 300 -> SCREEN-UNDERPOWERED. Otherwise SCREEN-FAIL.

The bootstrap is fed one WeekSum per ISO week (reading F5): identical draws
to one object per event with statistic mean(d), at a fraction of the cost.
The p reported to the ledger is the share of resamples <= 0 (reading F6).

v214 avoid mode mirrors the clauses for an idea that should be avoided, and
adds a control arm (d_c = R_event - mean(R_control)). All six hold ->
SCREEN-AVOID-PASS. Against the matched null: mean(d) <= -0.10R, upper 95%
bound < 0, mean(d) < 0 in >= 7 of 2011..2019 (an empty year counting
against), N >= 300. Against the control arm: mean(d_c) <= -0.10R, upper
bound < 0, N_c >= 300. N or N_c < 300 -> SCREEN-UNDERPOWERED; any other
failing clause -> SCREEN-FAIL. The avoid p is the share of resamples >= 0,
reported to the same ledger BH family. Edge mode is unchanged.
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
SCREEN_AVOID_PASS = "SCREEN-AVOID-PASS"
MODES = ("edge", "avoid")
_PASS_LABEL = {"edge": SCREEN_PASS, "avoid": SCREEN_AVOID_PASS}
_POWER_CLAUSES = {"edge": ("n",), "avoid": ("n", "control_n")}
_P_SIDE = {"edge": np.less_equal, "avoid": np.greater_equal}
_TOLERANCE = 1e-12    # mean([0.1] * n) may land one ulp under 0.1


@dataclass(frozen=True)
class PairedEvent:
    entry_date: str   # entry bar t+1 (frozen reading F9); v182 level mode: the event bar t
    d: float


@dataclass(frozen=True)
class WeekSum:
    entry_date: str
    total: float
    n: int


@dataclass(frozen=True)
class ControlArm:
    n: int
    delta_exp_r: float | None
    ci_low: float | None
    ci_high: float | None
    per_year: dict


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
    mode: str = "edge"
    years_negative: int | None = None
    control: ControlArm | None = None


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


def years_negative(table) -> int:
    return sum(1 for n, mean in table.values() if n and mean is not None and mean < 0)


def mean_clause(delta) -> bool:
    return delta is not None and delta >= PASS_EXP_R - _TOLERANCE


def ci_clause(low) -> bool:
    return low is not None and low > 0


def avoid_mean_clause(delta) -> bool:
    return delta is not None and delta <= -PASS_EXP_R + _TOLERANCE


def avoid_ci_clause(high) -> bool:
    return high is not None and high < 0


def years_clause(count: int) -> bool:
    return count >= MIN_POSITIVE_YEARS


def n_clause(n: int) -> bool:
    return n >= MIN_N


def bootstrap(events, *, n_resamples: int, seed: int, mode: str = "edge"):
    """(lower 2.5%, upper 97.5%, one-sided p) of mean(d), or Nones.

    Edge p is the share of draws <= 0; avoid p the share >= 0."""
    draws = stats.week_cluster_bootstrap([], week_sums(events), pooled_mean,
                                         n_resamples=n_resamples, seed=seed)
    if draws.size == 0:
        return None, None, None
    return (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)),
            float(np.mean(_P_SIDE[mode](draws, 0.0))))


def label(clauses: dict, mode: str = "edge") -> str:
    if not all(clauses[key] for key in _POWER_CLAUSES[mode]):
        return SCREEN_UNDERPOWERED
    return _PASS_LABEL[mode] if all(clauses.values()) else SCREEN_FAIL


def control_arm(events, *, n_resamples: int, seed: int) -> ControlArm:
    """The control arm's d_c = R_event - mean(R_control), same frozen seed."""
    events = list(events)
    low, high, _ = bootstrap(events, n_resamples=n_resamples, seed=seed)
    return ControlArm(len(events), mean_d([], events), low, high, per_year(events))


def _check_mode(mode: str, control) -> None:
    if mode not in MODES:
        raise ValueError(f"verdict mode {mode!r} is not one of {MODES}")
    if mode == "edge" and control is not None:
        raise ValueError("an edge verdict takes no control arm")


def _avoid_clauses(delta, high, negative: int, n: int, arm: ControlArm) -> dict:
    return {"exp_r": avoid_mean_clause(delta), "ci": avoid_ci_clause(high),
            "years": years_clause(negative), "n": n_clause(n),
            "control_exp_r": avoid_mean_clause(arm.delta_exp_r),
            "control_ci": avoid_ci_clause(arm.ci_high), "control_n": n_clause(arm.n)}


def _avoid_verdict(events, delta, bounds, table, positive, control, *,
                   n_resamples: int, seed: int) -> Verdict:
    low, high, p = bounds
    arm = control_arm(control or [], n_resamples=n_resamples, seed=seed)
    negative = years_negative(table)
    clauses = _avoid_clauses(delta, high, negative, len(events), arm)
    return Verdict(label(clauses, "avoid"), len(events), delta, low, high, p, positive,
                   table, clauses, mode="avoid", years_negative=negative, control=arm)


def decide(events, *, mode: str = "edge", control=None,
           n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES,
           seed: int = stats.WEEK_BOOTSTRAP_SEED) -> Verdict:
    _check_mode(mode, control)
    events = list(events)
    delta = mean_d([], events)
    low, high, p = bootstrap(events, n_resamples=n_resamples, seed=seed, mode=mode)
    table = per_year(events)
    positive = years_positive(table)
    if mode == "avoid":
        return _avoid_verdict(events, delta, (low, high, p), table, positive, control,
                              n_resamples=n_resamples, seed=seed)
    clauses = {"exp_r": mean_clause(delta), "ci": ci_clause(low),
               "years": years_clause(positive), "n": n_clause(len(events))}
    return Verdict(label(clauses), len(events), delta, low, high, p, positive,
                   table, clauses)
