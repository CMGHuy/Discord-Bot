"""Group closed trades along any of DIMENSIONS (Task A14) into StatRow
summaries. Every ratio is delegated to metrics.py -- no local formulas --
per the Global Constraint "one definition per stat". The only non-pure
import here is performance.primary_strategy_label, a pure string
resolution helper with no file I/O of its own (see its docstring)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from swingbot.core.analytics import metrics
from swingbot.core.performance import primary_strategy_label


@dataclass
class StatRow:
    key: str
    n: int
    wins: int
    losses: int
    win_rate: float | None
    expectancy_r: float | None
    avg_r: float | None
    profit_factor: float | None
    total_pnl: float


def _row_for(key: str, trades: list[dict]) -> StatRow:
    wins = sum(1 for t in trades if t.get("status") == "win")
    losses = sum(1 for t in trades if t.get("status") == "loss")
    expectancy = metrics.expectancy_r(trades)
    total_pnl = sum(float(t.get("realized_pnl_amount") or 0.0) for t in trades)
    return StatRow(
        key=key, n=len(trades), wins=wins, losses=losses,
        win_rate=metrics.win_rate(trades), expectancy_r=expectancy, avg_r=expectancy,
        profit_factor=metrics.profit_factor(trades), total_pnl=round(total_pnl, 2),
    )


def stats_by(closed: list[dict], dimension: str) -> list[StatRow]:
    """Group `closed` by `dimension` (see DIMENSIONS in Task A14 for the
    full set) and return one StatRow per group, sorted by trade count
    descending -- the busiest bucket first, matching how every table in
    this cockpit wants "most-traded strategy/ticker/etc. at the top"."""
    from swingbot.core.analytics.aggregate import _EXTRACTORS  # populated by Task A14
    if dimension not in _EXTRACTORS:
        raise ValueError(f"Unknown aggregation dimension: {dimension!r}")

    groups: dict[str, list[dict]] = defaultdict(list)
    extractor = _EXTRACTORS[dimension]
    for t in closed:
        groups[extractor(t)].append(t)

    rows = [_row_for(key, trades) for key, trades in groups.items()]
    rows.sort(key=lambda r: r.n, reverse=True)
    return rows


# Task A14 replaces this stub with the full 10-entry table and DIMENSIONS tuple.
_EXTRACTORS: dict = {
    "strategy": lambda t: primary_strategy_label(t),
}
