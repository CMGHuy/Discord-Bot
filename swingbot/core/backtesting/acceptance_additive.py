"""Additive-strategy acceptance gate (v230 spec Part C, plan v238).

Read docs/claude/backtest-methodology.md's "Additive gate" section before
changing anything here. The clause set and its constants are PRE-REGISTERED.

The v72 gate makes the book's pooled win rate the objective. A strategy that
only ADDS rows at reward:risk 2 breaks even at a 33% win rate, so it can pay
while lowering the pooled win rate, and v72 refuses it (v180 died on a
-0.21pp pooled dWR). This gate judges an added strategy on its own rows:

1. own_expectancy (the objective): the added rows' net ExpR.
2. win_rate_above_breakeven: their decided win rate against their OWN
   realised break-even, avg loss / (avg win + avg loss).
3. book_net_gain: the book's total R must not fall when an added position
   displaces a baseline plan (SKIPPED with no displacement).
4. stability: the added rows' ExpR per walk-forward fold.

Every interval is week-clustered (instrument.stats): an added strategy's
signals bunch on market days, so one bad week is one bet. Both arms must be
net of costs; that precondition is checked by the caller
(validate_component.py, provenance.check_r_basis), not here. numpy only.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .acceptance import (
    ALPHA, BOOTSTRAP_RESAMPLES, CLOSED, DECIDED, ClauseResult, expectancy_r,
    population_split, win_rate,
)
from .arms.pairing import index_by_key
from .instrument.stats import week_cluster_bootstrap

ADDITIVE_VERSION = 1   # additive-procedure version, recorded in every results doc
ADDITIVE_GATE_MISUSE = "ADDITIVE_GATE_MISUSE"
CLAUSES = ("own_expectancy", "win_rate_above_breakeven", "book_net_gain", "stability")

#: Strict thresholds: a value equal to its bar FAILs whatever its last bit.
_EPS = 1e-9


@dataclass(frozen=True)
class AdditiveSplit:
    """The component against the baseline, by pairing key.

    ``added`` are component rows with no baseline key; ``displaced`` are
    baseline rows with no component key (an added position blocked them).
    ``misuse`` is None for an add-only arm, else the refusal reason."""
    added: tuple
    displaced: tuple
    misuse: str | None = None


def _r_changed(baseline_trade, component_trade) -> bool:
    b, c = baseline_trade.r_multiple, component_trade.r_multiple
    if (b is None) != (c is None):
        return True
    return b is not None and abs(b - c) > _EPS


def _misuse(split: dict, moved: list) -> str | None:
    added, removed = split["added"], split["removed"]
    if not added:
        return (f"{ADDITIVE_GATE_MISUSE}: the component adds no row; a filter or "
                f"veto belongs to the v72 gate")
    if moved:
        return (f"{ADDITIVE_GATE_MISUSE}: {len(moved)} shared row(s) changed outcome "
                f"or R (first {moved[0].key}); an exit or geometry change belongs "
                f"to the v92 harvest gate")
    if len(removed) > len(added):
        return (f"{ADDITIVE_GATE_MISUSE}: {len(removed)} baseline row(s) vanished but "
                f"only {len(added)} were added; every displaced row needs an added "
                f"position")
    return None


def split_additive(baseline, component) -> AdditiveSplit:
    """Partition the arms and decide whether the component only adds rows.

    A duplicate key in either arm raises (``index_by_key``): pairing would
    silently keep one row and every clause would be wrong."""
    index_by_key(baseline)
    index_by_key(component)
    split = population_split(baseline, component)
    moved = [bt for bt, _ in split["changed"]]
    moved += [bt for bt, ct in split["unchanged"] if _r_changed(bt, ct)]
    return AdditiveSplit(added=tuple(split["added"]),
                         displaced=tuple(split["removed"]),
                         misuse=_misuse(split, moved))


def _closed(rows) -> list:
    return [t for t in rows if t.outcome in CLOSED and t.r_multiple is not None]


def added_bootstrap(added, statistic, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
                    seed: int = 42) -> np.ndarray:
    """``statistic(rows)`` on each week-cluster draw of the added rows alone
    (no baseline), undefined draws dropped."""
    return week_cluster_bootstrap([], list(added),
                                  lambda _baseline, rows: statistic(rows),
                                  n_resamples=n_resamples, seed=seed)


def _interval(draws) -> tuple:
    """(lower 95% bound, upper 95% bound, one-sided p = share of draws <= 0)."""
    lo = float(np.percentile(draws, 100 * ALPHA / 2))
    hi = float(np.percentile(draws, 100 * (1 - ALPHA / 2)))
    return lo, hi, float(np.mean(draws <= 0.0))


def clause_own_expectancy(added, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
                          seed: int = 42) -> ClauseResult:
    """Clause 1, the objective: the added rows' net ExpR, lower 95% bound > 0."""
    closed = _closed(added)
    point = expectancy_r(closed)
    if point is None:
        return ClauseResult(CLAUSES[0], "FAIL",
                            "no closed added row with an R; own ExpR undefined",
                            None, 0.0)
    lo, hi, p = _interval(added_bootstrap(closed, expectancy_r,
                                          n_resamples=n_resamples, seed=seed))
    ok = lo > _EPS
    return ClauseResult(
        CLAUSES[0], "PASS" if ok else "FAIL",
        f"own net ExpR {point:+.4f}R [{lo:+.4f},{hi:+.4f}] p={p:.4f} "
        f"N={len(closed)} (lower bound must be > 0)", point, 0.0)


def _mean_or_zero(values) -> float:
    return float(np.mean(values)) if values else 0.0


def realised_breakeven(rows) -> float | None:
    """The win rate (a fraction) at which these rows' own average win and
    average loss break even: avg loss / (avg win + avg loss), decided rows
    only. No winner gives 1.0, no loser 0.0; no decided row gives None."""
    decided = [t for t in rows if t.outcome in DECIDED and t.r_multiple is not None]
    avg_win = _mean_or_zero([t.r_multiple for t in decided if t.outcome == "win"])
    avg_loss = _mean_or_zero([-t.r_multiple for t in decided if t.outcome == "loss"])
    total = avg_win + avg_loss
    if not decided or total <= 0.0:
        return None
    return avg_loss / total


def clause_win_rate_above_breakeven(added, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
                                    seed: int = 42) -> ClauseResult:
    """Clause 2: the decided win rate's lower 95% bound (percent) above the
    added rows' realised break-even (percent). Replaces v72's pooled
    win-rate comparison with the strategy's own arithmetic."""
    decided = [t for t in added if t.outcome in DECIDED and t.r_multiple is not None]
    point, breakeven = win_rate(decided), realised_breakeven(decided)
    if point is None or breakeven is None:
        return ClauseResult(CLAUSES[1], "FAIL",
                            "no decided added row; win rate and break-even undefined",
                            None, None)
    bar = 100.0 * breakeven
    lo, hi, _ = _interval(added_bootstrap(decided, win_rate,
                                          n_resamples=n_resamples, seed=seed))
    ok = lo > bar + _EPS
    return ClauseResult(
        CLAUSES[1], "PASS" if ok else "FAIL",
        f"own WR {point:.2f}% [{lo:.2f},{hi:.2f}] vs realised break-even "
        f"{bar:.2f}% (avg loss / (avg win + avg loss)), N={len(decided)}", lo, bar)


# --- clause 3: book_net_gain ----------------------------------------------------------

#: PRE-REGISTERED (spec Part C): the book's total R may fall by at most 10%
#: of the added rows' own total R at the lower bound.
TOLERANCE_SHARE = 0.10


def _book_total(rows) -> float:
    return float(sum(t.r_multiple for t in _closed(rows)))


def _book_delta(baseline, component) -> float:
    """Strategy on minus strategy off, the book's total R (a sum, not a mean)."""
    return _book_total(component) - _book_total(baseline)


def _book_verdict(point: float, lo: float, floor: float) -> bool:
    return point > _EPS and lo > floor + _EPS


def clause_book_net_gain(baseline, component, split: AdditiveSplit, *,
                         n_resamples: int = BOOTSTRAP_RESAMPLES,
                         seed: int = 42) -> ClauseResult:
    """Clause 3: an added position that displaces a baseline plan (heat, one
    position per ticker) must not cost the book its total R. Paired: both
    arms resampled with the same week draw, so unchanged rows cancel."""
    if not split.displaced:
        return ClauseResult(CLAUSES[2], "SKIPPED",
                            "no baseline row displaced; the book only gains rows",
                            None, None)
    added_total = _book_total(split.added)
    floor = -TOLERANCE_SHARE * added_total
    point = _book_delta(baseline, component)
    lo, hi, p = _interval(week_cluster_bootstrap(
        list(baseline), list(component), _book_delta,
        n_resamples=n_resamples, seed=seed))
    ok = _book_verdict(point, lo, floor)
    return ClauseResult(
        CLAUSES[2], "PASS" if ok else "FAIL",
        f"book total R {point:+.2f}R [{lo:+.2f},{hi:+.2f}] p={p:.4f}; floor "
        f"{floor:+.2f}R (-{TOLERANCE_SHARE:.0%} of the added rows' {added_total:+.2f}R); "
        f"{len(split.added)} added, {len(split.displaced)} displaced", point, floor)


# --- clause 4: stability --------------------------------------------------------------

#: PRE-REGISTERED (spec Part C): the walk-forward test years and the bar.
FOLD_YEARS = ("2021", "2022", "2023")
FOLD_FLOOR_R = -0.10
FOLD_MIN_N = 30
FOLDS_POSITIVE = 2


def _fold_row(fold: dict) -> dict:
    split = split_additive(fold["baseline"], fold["component"])
    closed = _closed(split.added)
    return {"year": str(fold["test_year"]), "n": len(closed),
            "exp_r": expectancy_r(closed), "misuse": split.misuse}


def _fold_problem(rows: list) -> str | None:
    years = tuple(row["year"] for row in rows)
    if years != FOLD_YEARS:
        return f"folds must be {'/'.join(FOLD_YEARS)}, got {'/'.join(years) or 'none'}"
    for row in rows:
        if row["misuse"]:
            return f"fold {row['year']}: {row['misuse']}"
    return None


def _fold_text(row: dict) -> str:
    exp = "n/a" if row["exp_r"] is None else f"{row['exp_r']:+.4f}R"
    return f"{row['year']} {exp} N={row['n']}"


def _stability_detail(rows: list, positive: int, thin: list, sunk: list) -> str:
    parts = [_fold_text(row) for row in rows]
    parts.append(f"positive {positive}/{len(FOLD_YEARS)} (need {FOLDS_POSITIVE}), "
                 f"floor {FOLD_FLOOR_R:+.2f}R, min N {FOLD_MIN_N}")
    if thin:
        parts.append(f"thin: {', '.join(thin)}")
    if sunk:
        parts.append(f"below floor: {', '.join(sunk)}")
    return "; ".join(parts)


def _fold_tallies(rows: list) -> tuple:
    """(positive fold count, thin fold years, fold years below the floor)."""
    scored = [row for row in rows if row["exp_r"] is not None]
    positive = sum(1 for row in scored if row["exp_r"] > _EPS)
    thin = [row["year"] for row in rows if row["n"] < FOLD_MIN_N]
    sunk = [row["year"] for row in scored if row["exp_r"] < FOLD_FLOOR_R - _EPS]
    return positive, thin, sunk


def clause_stability(folds: list) -> ClauseResult:
    """Clause 4: the added rows' net ExpR per walk-forward fold (2021, 2022,
    2023) is > 0 in at least two, below -0.10R in none, on N >= 30 each."""
    rows = sorted((_fold_row(fold) for fold in folds), key=lambda row: row["year"])
    problem = _fold_problem(rows)
    if problem:
        return ClauseResult(CLAUSES[3], "FAIL", problem, None, float(FOLDS_POSITIVE))
    positive, thin, sunk = _fold_tallies(rows)
    ok = positive >= FOLDS_POSITIVE and not thin and not sunk
    return ClauseResult(CLAUSES[3], "PASS" if ok else "FAIL",
                        _stability_detail(rows, positive, thin, sunk),
                        float(positive), float(FOLDS_POSITIVE))
