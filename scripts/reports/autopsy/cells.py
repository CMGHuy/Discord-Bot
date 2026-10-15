"""Cell statistics for the book autopsy (spec section 1, binding).

A cell is the trades of one cut whose key equals one value. It is compared with
its COMPLEMENT -- the same cut's other placed trades -- never with a pool that
contains it: delta = mean net R(cell) - mean net R(complement). The 95% interval
is the percentile interval of week_cluster_bootstrap(complement, cell, ...),
both arms drawn with the same ISO-week resample; p is two-sided; q is
Benjamini-Hochberg over every cell tested in the run. The bootstrap is fed
per-week sums (objects with an ``.entry_date``), not trades, so a 10 000
resample run finishes in minutes. Thin cells are tested and counted, never
ranked as evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict, namedtuple
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from swingbot.core.analytics.gate_counterfactual_report import two_sided_bootstrap_p
from swingbot.core.backtesting.instrument import stats

from .rows import BookRow

THIN_MIN_N = 30
THIN_MIN_WEEKS = 8

WeekSum = namedtuple("WeekSum", "entry_date total n")


def _r4(value):
    return None if value is None else round(float(value), 4)


@dataclass
class CellStats:
    id: str
    cut: str
    value: str
    n: int
    weeks: int
    win_rate: float
    net_expr: float
    gross_expr: float
    delta: float | None
    ci: tuple[float, float] | None
    p: float | None
    q: float | None
    thin: bool
    bar_covered_n: int | None = None
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "id": self.id, "cut": self.cut, "value": self.value,
            "n": self.n, "weeks": self.weeks, "win_rate": _r4(self.win_rate),
            "net_expr": _r4(self.net_expr), "gross_expr": _r4(self.gross_expr),
            "delta": _r4(self.delta),
            "ci": None if self.ci is None else [_r4(self.ci[0]), _r4(self.ci[1])],
            "p": _r4(self.p), "q": _r4(self.q), "thin": self.thin,
            "bar_covered_n": self.bar_covered_n, "extra": dict(self.extra),
        }


@dataclass
class Tally:
    id: str
    cut: str
    value: str
    count: int
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"id": self.id, "cut": self.cut, "value": self.value,
                "count": self.count, "extra": dict(self.extra)}


def is_thin(n: int, weeks: int) -> bool:
    return n < THIN_MIN_N or weeks < THIN_MIN_WEEKS


def net_value(trade) -> float:
    """Modelled net R; the gross R stands in when the net could not be modelled."""
    return trade.net_r if trade.net_r is not None else trade.gross_r


def week_sums(trades) -> list[WeekSum]:
    """One (entry_date, total net R, n) per ISO week, in week order."""
    by_week = defaultdict(list)
    for trade in trades:
        by_week[stats.iso_week_key(trade.entry_date)].append(trade)
    return [WeekSum(group[0].entry_date, sum(net_value(t) for t in group), len(group))
            for _, group in sorted(by_week.items())]


def _mean_gap(complement_draw, cell_draw) -> float | None:
    """Cell pooled mean minus complement pooled mean for one week draw."""
    complement_n = sum(w.n for w in complement_draw)
    cell_n = sum(w.n for w in cell_draw)
    if not complement_n or not cell_n:
        return None
    return (sum(w.total for w in cell_draw) / cell_n
            - sum(w.total for w in complement_draw) / complement_n)


def _mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def _interval(members, complement, n_resamples: int, seed: int):
    """((low, high), p), or (None, None) when there is nothing to compare."""
    if not members or not complement:
        return None, None
    draws = stats.week_cluster_bootstrap(week_sums(complement), week_sums(members), _mean_gap,
                                         n_resamples=n_resamples, seed=seed)
    if draws.size == 0:
        return None, None
    low, high = np.percentile(draws, [2.5, 97.5])
    return (float(low), float(high)), two_sided_bootstrap_p(draws)


def _extra(members) -> dict:
    counts = Counter(t.ticker for t in members)
    out = {"tickers": len(counts),
           "top_ticker_share": round(max(counts.values()) / len(members), 4) if members else 0.0}
    missing = sum(1 for t in members if t.net_r is None)
    if missing:
        out["net_modelled_missing"] = missing
    return out


def cell_stats(cut: str, value: str, members: list, complement: list, *,
               n_resamples: int, seed: int) -> CellStats:
    """One cell against its complement (the same cut's other placed trades)."""
    n = len(members)
    weeks = len({stats.iso_week_key(t.entry_date) for t in members})
    net = [net_value(t) for t in members]
    ci, p = _interval(members, complement, n_resamples, seed)
    delta = None if ci is None else _mean(net) - _mean([net_value(t) for t in complement])
    return CellStats(
        id=f"{cut}={value}", cut=cut, value=value, n=n, weeks=weeks,
        win_rate=sum(1 for t in members if t.gross_r > 0) / n if n else 0.0,
        net_expr=_mean(net), gross_expr=_mean([t.gross_r for t in members]),
        delta=delta, ci=ci, p=p, q=None, thin=is_thin(n, weeks), extra=_extra(members),
    )


def cut_cells(cut: str, trades: list, key: Callable[[BookRow], str | None], *,
              n_resamples: int, seed: int) -> list[CellStats]:
    """One cell per distinct key value; unplaced trades sit in neither arm."""
    keyed = [(key(t), t) for t in trades]
    uncovered = sum(1 for k, _ in keyed if k is None)
    placed = [(str(k).replace(";", ","), t) for k, t in keyed if k is not None]
    out = []
    for value in sorted({k for k, _ in placed}):
        members = [t for k, t in placed if k == value]
        complement = [t for k, t in placed if k != value]
        cell = cell_stats(cut, value, members, complement, n_resamples=n_resamples, seed=seed)
        cell.extra["uncovered"] = uncovered
        out.append(cell)
    return out


def apply_bh(cells: list[CellStats]) -> int:
    """One BH pass over every cell of the run; returns how many were tested."""
    for cell, q in zip(cells, stats.bh_qvalues([c.p for c in cells])):
        cell.q = q
    return sum(1 for c in cells if c.p is not None)
