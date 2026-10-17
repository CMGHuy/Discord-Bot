"""Purged, embargoed anchored walk-forward folds (v136 spec section 1, "Folds").

Anchored yearly folds over the instrument's research span: test year Y is
[Y-01-01, Y-12-31]; its train fold runs from ``research_start`` to the day
before. A trade belongs to a test fold by its ENTRY date (under v2 that is the
fill date; folds never read ``signal_date``). In the matching train fold:

* purge   -- a train trade entered before the test start whose exit is on or
             after it (or that never closed) is dropped: its outcome overlaps
             the test fold;
* embargo -- a train trade entered within ``embargo_days`` after the test end
             is dropped. Under anchored folds no train trade enters after the
             test end, so the embargo never fires there; it is implemented for
             any fold whose train side continues past the test fold.

``out_of_fold`` selects a config per fold on that fold's train trades only and
pools each selected config's test trades: every trade counts once, in its own
test year. The pooled out-of-fold ExpR is the v2 verdict statistic.

Dates compare as ISO day strings (``str(value)[:10]``), the convention of
``pit_membership.is_member``.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from swingbot.core.market.strategy_types import HORIZONS

#: Spec section 1: at least four training years before the first test fold.
MIN_TRAIN_YEARS = 4


@dataclass(frozen=True)
class Fold:
    """One anchored fold; every bound is an inclusive ISO day."""

    test_year: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str


@dataclass(frozen=True)
class OutOfFold:
    """Per-fold choices ((test_year, config), ...) and the pooled test trades."""

    choices: tuple[tuple[int, Any], ...]
    trades: list


def _check_years(spec) -> None:
    years = tuple(spec.fold_test_years)
    if not years:
        raise ValueError("fold_scheme 'anchored_yearly' needs fold_test_years")
    if list(years) != sorted(set(years)):
        raise ValueError(f"fold_test_years must be strictly increasing: {years}")
    if years[0] - int(spec.research_start[:4]) < MIN_TRAIN_YEARS:
        raise ValueError(f"first test year {years[0]} leaves fewer than "
                         f"{MIN_TRAIN_YEARS} training years after {spec.research_start}")
    if f"{years[-1]}-12-31" > spec.research_end:
        raise ValueError(f"test year {years[-1]} ends after research_end {spec.research_end}: "
                         "that is the sealed holdout")


def anchored_folds(spec) -> tuple[Fold, ...]:
    """The instrument's folds; () when its fold_scheme is 'none' (v1)."""
    if spec.fold_scheme == "none":
        return ()
    if spec.fold_scheme != "anchored_yearly":
        raise ValueError(f"unknown fold scheme {spec.fold_scheme!r}")
    _check_years(spec)
    return tuple(Fold(test_year=y, train_start=spec.research_start, train_end=f"{y - 1}-12-31",
                      test_start=f"{y}-01-01", test_end=f"{y}-12-31")
                 for y in spec.fold_test_years)


def embargo_days_for(horizon_key: str) -> int:
    """The horizon's maximum holding period (strategy_types.HORIZONS)."""
    try:
        return int(HORIZONS[horizon_key]["max_holding_days"])
    except KeyError:
        raise ValueError(f"unknown horizon {horizon_key!r}") from None


def _day(value) -> str:
    return str(value)[:10]


def _inside(day: str, start: str, end: str) -> bool:
    return start <= day <= end


def _purged(trade, fold: Fold) -> bool:
    """Entered before the test fold and still open on or after its first day."""
    if _day(trade.entry_date) >= fold.test_start:
        return False
    return trade.exit_date is None or _day(trade.exit_date) >= fold.test_start


def _train_keeps(trade, fold: Fold, embargo_end: str, purge: bool) -> bool:
    day = _day(trade.entry_date)
    if not _inside(day, fold.train_start, fold.train_end):
        return False
    if _inside(day, fold.test_start, fold.test_end):
        return False
    if purge and _purged(trade, fold):
        return False
    return not fold.test_end < day <= embargo_end


def split_fold(trades, fold: Fold, *, embargo_days: int,
               purge: bool = True) -> tuple[list, list]:
    """(train, test) for one fold. Test = entered inside the test window.
    Train = entered inside the train window and outside the test window,
    minus purged and embargoed trades. Input order is preserved."""
    if embargo_days < 0:
        raise ValueError(f"embargo_days must be >= 0, got {embargo_days}")
    embargo_end = (date.fromisoformat(fold.test_end) + timedelta(days=embargo_days)).isoformat()
    test = [t for t in trades if _inside(_day(t.entry_date), fold.test_start, fold.test_end)]
    train = [t for t in trades if _train_keeps(t, fold, embargo_end, purge)]
    return train, test


def _check_disjoint(folds) -> None:
    ordered = sorted(folds, key=lambda f: f.test_start)
    for a, b in zip(ordered, ordered[1:]):
        if b.test_start <= a.test_end:
            raise ValueError(f"test windows overlap: {a.test_year} and {b.test_year} "
                             "(a trade would count twice)")


def out_of_fold(trades_by_config: Mapping[Any, Sequence], folds,
                select: Callable[[Mapping[Any, list]], Any], *, embargo_days: int,
                purge: bool = True) -> OutOfFold:
    """Per fold: `select` sees {config: train trades} only and returns a config;
    that config's test trades join the pool. Each trade counts once."""
    _check_disjoint(folds)
    choices, pooled = [], []
    for fold in folds:
        train = {cfg: split_fold(trades, fold, embargo_days=embargo_days, purge=purge)[0]
                 for cfg, trades in trades_by_config.items()}
        choice = select(train)
        if choice not in trades_by_config:
            raise ValueError(f"select returned {choice!r}, not one of the configs")
        choices.append((fold.test_year, choice))
        pooled += split_fold(trades_by_config[choice], fold, embargo_days=embargo_days,
                             purge=purge)[1]
    return OutOfFold(choices=tuple(choices), trades=pooled)
