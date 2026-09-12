"""Pre-registered v82 earnings-blackout measurement arithmetic."""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, replace

import numpy as np

from swingbot.core.backtesting.acceptance import NON_INFERIORITY_R, VOLUME_MAX_CUT_PCT, ArmTrade, delta_expectancy_r, delta_standardised_win_rate, expectancy_r, win_rate
from swingbot.core.backtesting.backtest_wf import plateau_report
from swingbot.core.market.earnings_calendar import is_exposed, next_reaction_distance

PARAM_NAME = "EARNINGS_BLACKOUT_SESSIONS"
GRID = (1, 2, 3, 5)
COVERAGE_FLOOR_PCT = 90.0
RUN1_WINDOW, SELECTION_WINDOW = ("2018-06-01", "2023-12-31"), ("2018-06-01", "2020-12-31")
SELECTION_OBSERVED_DAYS, MDE_TARGET_DAYS = 945, 730
FOLD_TEST_YEARS, VALIDATION_WINDOW = ("2021", "2022", "2023"), ("2024-01-01", "2025-12-31")
PERMUTATION_N, PERMUTATION_SEED, PERMUTATION_SHIFT_RANGE = 200, 42, (20, 200)
SELECTED, NO_ELIGIBLE_K, SPIKE, INSUFFICIENT_COVERAGE = "SELECTED", "NO_ELIGIBLE_K", "SPIKE", "INSUFFICIENT_COVERAGE"


@dataclass(frozen=True)
class ExposureRow:
    trade: ArmTrade
    population: str
    is_etf: bool
    covered: bool
    signal_pos: int
    distance: int | None
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, value): return cls(ArmTrade(**value["trade"]), value["population"], value["is_etf"], value["covered"], value["signal_pos"], value["distance"])


def in_window(rows, window):
    return [row for row in rows if window[0] <= row.trade.entry_date <= window[1]]


def in_year(rows, year):
    return [row for row in rows if row.trade.entry_date.startswith(year)]


def coverage_pct(rows):
    stocks = [row for row in rows if not row.is_etf]
    return None if not stocks else 100.0 * sum(row.covered for row in stocks) / len(stocks)


def split(rows, k):
    baseline = [row.trade for row in rows]
    removed = [row.trade for row in rows if is_exposed(row.distance, k)]
    component = [row.trade for row in rows if not is_exposed(row.distance, k)]
    return baseline, component, removed


def arms_blob(rows, k):
    baseline, component, _ = split(rows, k)
    return {"baseline": [asdict(trade) for trade in baseline], "component": [asdict(trade) for trade in component]}


def folds_blob(rows, k):
    return {"folds": [{"test_year": year, **arms_blob(in_year(rows, year), k)} for year in FOLD_TEST_YEARS]}


@dataclass(frozen=True)
class Candidate:
    k: int; removed_n: int; removed_win_rate: float | None; retained_win_rate: float | None; removed_expectancy_r: float | None; volume_cut_pct: float; delta_win_rate_pp: float | None; delta_expectancy_r: float | None; eligible: bool; reasons: tuple[str, ...]


def score_candidate(rows, k):
    baseline, component, removed = split(rows, k)
    removed_wr, retained_wr, removed_expr = win_rate(removed), win_rate(component), expectancy_r(removed)
    cut = 100.0 * len(removed) / len(baseline) if baseline else 100.0
    dwr, dexpr = delta_standardised_win_rate(baseline, component), delta_expectancy_r(baseline, component)
    reasons = []
    if removed_wr is None or retained_wr is None or removed_wr >= retained_wr: reasons.append("mechanism: removed win rate is not below retained")
    if removed_expr is None or removed_expr > 0: reasons.append("mechanism: removed expectancy is above 0")
    if cut > VOLUME_MAX_CUT_PCT: reasons.append(f"volume: cut {cut:.2f}% > {VOLUME_MAX_CUT_PCT}%")
    if dexpr is None or dexpr < NON_INFERIORITY_R: reasons.append(f"profit: dExpR below {NON_INFERIORITY_R}R")
    if dwr is None: reasons.append("win rate: no decided trades to compare")
    return Candidate(k, len(removed), removed_wr, retained_wr, removed_expr, cut, dwr, dexpr, not reasons, tuple(reasons))


@dataclass(frozen=True)
class Selection:
    candidates: tuple[Candidate, ...]; selected_k: int | None; plateau: dict | None; verdict: str


def select_k(rows, grid=GRID):
    candidates = tuple(score_candidate(rows, k) for k in grid)
    eligible = [candidate for candidate in candidates if candidate.eligible]
    if not eligible: return Selection(candidates, None, None, NO_ELIGIBLE_K)
    best = max(eligible, key=lambda candidate: (candidate.delta_win_rate_pp, -candidate.k))
    expectancies = [expectancy_r(split(rows, k)[1]) for k in grid]
    plateau = plateau_report(PARAM_NAME, list(grid), [float("nan") if value is None else value for value in expectancies], best.k)
    return Selection(candidates, best.k if plateau["is_plateau"] else None, plateau, SELECTED if plateau["is_plateau"] else SPIKE)


def permutation_test(rows, k, reactions_by_ticker, n_sessions, *, n=PERMUTATION_N, seed=PERMUTATION_SEED):
    baseline, component, _ = split(rows, k); real = delta_standardised_win_rate(baseline, component)
    shifts = np.random.default_rng(seed).integers(*PERMUTATION_SHIFT_RANGE, size=n); permuted = []
    for shift in shifts:
        moved_positions = {ticker: sorted((position + int(shift)) % n_sessions for position in positions) for ticker, positions in reactions_by_ticker.items()}
        moved = [replace(row, distance=next_reaction_distance(row.signal_pos, moved_positions.get(row.trade.ticker, []))) if row.covered else row for row in rows]
        b, c, _ = split(moved, k); permuted.append(delta_standardised_win_rate(b, c))
    valid = [value for value in permuted if value is not None]
    return {"real_delta_win_rate_pp": real, "p_value": None if real is None or not valid else float(np.mean([value >= real for value in valid])), "n": int(n), "n_valid": len(valid), "seed": seed, "shift_range": list(PERMUTATION_SHIFT_RANGE)}
