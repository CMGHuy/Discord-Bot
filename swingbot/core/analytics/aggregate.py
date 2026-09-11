"""Group closed trades along any of DIMENSIONS (Task A14) into StatRow
summaries. Every ratio is delegated to metrics.py -- no local formulas --
per the Global Constraint "one definition per stat". The only non-pure
import here is performance.primary_strategy_label, a pure string
resolution helper with no file I/O of its own (see its docstring)."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from swingbot.core.analytics import metrics
from swingbot.core.market.session import BERLIN_TZ as _BERLIN_TZ
from swingbot.core.tracking.performance import primary_strategy_label


_DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

#: Below this many trades in a cell, a rate is noise and must not be quoted.
#: Seeded from calibration.DRIFT_LIVE_N_FLOOR; it is deliberately local to
#: avoid a calibration import cycle.  The matching aggregate test pins it.
MIN_CELL_N = 20


def _to_berlin(iso_str: str | None) -> dt.datetime | None:
    if not iso_str:
        return None
    try:
        d = dt.datetime.fromisoformat(iso_str)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(_BERLIN_TZ)


def _dow_key(t: dict) -> str:
    d = _to_berlin(t.get("closed_at"))
    return _DOW_NAMES[d.weekday()] if d else "unknown"


def _month_key(t: dict) -> str:
    d = _to_berlin(t.get("closed_at"))
    return d.strftime("%Y-%m") if d else "unknown"


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
    total_r: float | None = None


def _row_for(key: str, trades: list[dict]) -> StatRow:
    wins = sum(1 for t in trades if t.get("status") == "win")
    losses = sum(1 for t in trades if t.get("status") == "loss")
    expectancy = metrics.expectancy_r(trades)
    total_pnl = sum(float(t.get("realized_pnl_amount") or 0.0) for t in trades)
    rs = metrics.r_multiples(trades)
    total_r = round(float(sum(rs)), 4) if rs else None
    return StatRow(
        key=key, n=len(trades), wins=wins, losses=losses,
        win_rate=metrics.win_rate(trades), expectancy_r=expectancy, avg_r=expectancy,
        profit_factor=metrics.profit_factor(trades), total_pnl=round(total_pnl, 2),
        total_r=total_r,
    )


def stats_by(closed: list[dict], dimension: str) -> list[StatRow]:
    """Group `closed` by `dimension` (see DIMENSIONS in Task A14 for the
    full set) and return one StatRow per group, sorted by trade count
    descending -- the busiest bucket first, matching how every table in
    this cockpit wants "most-traded strategy/ticker/etc. at the top"."""
    if dimension not in _EXTRACTORS:
        raise ValueError(f"Unknown aggregation dimension: {dimension!r}")
    groups: dict[str, list[dict]] = defaultdict(list)
    extractor = _EXTRACTORS[dimension]
    for t in closed:
        groups[extractor(t)].append(t)
    rows = [_row_for(key, trades) for key, trades in groups.items()]
    rows.sort(key=lambda r: r.n, reverse=True)
    return rows


# v32 Task 11: "tier" (A/B/C, quality.py's own 0-100 quality_score bands)
# retired -- "confidence" (1-5 confidence level, the number that actually
# gates whether an alert fires) already existed as a separate dimension and
# covers the same "group trades by a quality classification" role.
DIMENSIONS = ("strategy", "horizon", "badge", "confidence",
             "direction", "dow", "month", "ticker", "source")

# Replaces the Task A13 stub -- now a plain module global, not populated
# via any self-import.
_EXTRACTORS = {
    "strategy": lambda t: primary_strategy_label(t),
    "horizon": lambda t: t.get("horizon_key") or "unknown",
    "badge": lambda t: t.get("badge") or "unknown",
    "source": lambda t: t.get("source") or "unknown",
    "confidence": lambda t: str(t["confidence_level"]) if t.get("confidence_level") is not None else "unknown",
    "direction": lambda t: t.get("direction") or "unknown",
    "ticker": lambda t: t.get("ticker") or "unknown",
    "dow": _dow_key,
    "month": _month_key,
}
