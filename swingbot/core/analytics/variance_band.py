"""v175 Normal bad luck: the range of losing runs this book's past produces.

Pure functions, no I/O: no store, no TradeLog, no config, no network. The
input is the closed book as trade dicts (``status`` in win/loss/closed,
every ledger, ``scope.select`` never applied: the band is whole-book).

The unit is the **close day**: every trade's R (``metrics.r_multiple``) is
summed per America/New_York close date, so five stop-outs on one gap day
are one loss day. A day is a loss below ``-SCRATCH_R``, a win above
``+SCRATCH_R``, a scratch otherwise. A losing run counts consecutive loss
days; a scratch day neither extends nor breaks it; a win day ends it. The
same rule is used for the bootstrap paths and for the current state.

The close date is the UTC ``closed_at`` converted to ET, deliberately
unlike ``pnl_calendar.day_of``'s UTC slice: an after-hours close belongs
to its NYSE session.

Spec: docs/superpowers/specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from swingbot.core.analytics import metrics
from swingbot.core.backtesting.instrument import stats
from swingbot.core.market.session import US_MARKET_TZ

# Frozen constants (v175 Global Constraints): changing one is a new spec.
MIN_DAYS = 100
MIN_WEEKS = 20
HORIZONS = (20, 50)
WINDOW = 50                       # current-drawdown window, == HORIZONS[-1]
PATHS = 10_000
SEED = stats.WEEK_BOOTSTRAP_SEED
SCRATCH_R = 0.05
ROUGH_PCT = 80
OUTSIDE_PCT = 95
OUTER_RESAMPLES = 200
OUTER_PATHS = 1_000               # inner paths per outer resample (plan choice)
CI_PCT = (10, 90)
EXPR_RESAMPLES = 10_000
EXPR_CI_PCT = (2.5, 97.5)
ZONES = ("normal", "rough", "outside")
CAVEAT = ("This book's past results are not positive. "
          "A run within their range is still a losing run.")


@dataclass(frozen=True)
class CloseDay:
    """One NYSE close date: the net R of every trade closed on it."""

    day: dt.date
    r: float
    kind: str


def et_close_date(closed_at: str) -> dt.date:
    """The America/New_York date of a ``closed_at`` stamp (naive = UTC)."""
    stamp = dt.datetime.fromisoformat(closed_at)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(US_MARKET_TZ).date()


def day_kind(r: float) -> str:
    """``loss`` below -SCRATCH_R, ``win`` above +SCRATCH_R, else ``scratch``."""
    if r < -SCRATCH_R:
        return "loss"
    if r > SCRATCH_R:
        return "win"
    return "scratch"


def _dated_r(trades: list[dict]):
    """(ET close date, R) for every trade with a computable R and a close."""
    for trade in trades:
        closed_at = trade.get("closed_at")
        r = metrics.r_multiple(trade)
        if r is None or not closed_at:
            continue
        yield et_close_date(closed_at), r


def close_days(trades: list[dict]) -> list[CloseDay]:
    """Net R per ET close date, in date order (R rounded to 4 dp)."""
    sums: dict[dt.date, float] = defaultdict(float)
    for day, r in _dated_r(trades):
        sums[day] += r
    out = []
    for day in sorted(sums):
        net = round(sums[day], 4)
        out.append(CloseDay(day, net, day_kind(net)))
    return out


def current_run(days: list[CloseDay]) -> tuple[int, dt.date | None]:
    """Loss days in the run in progress at the last close day, and its first day.

    Walks back from the latest day: a loss day counts, a scratch day is
    passed over, a win day ends the walk. ``(0, None)`` when no run is on."""
    length, first = 0, None
    for close_day in reversed(days):
        if close_day.kind == "win":
            break
        if close_day.kind == "loss":
            length, first = length + 1, close_day.day
    return length, first


def window_drawdown(days: list[CloseDay],
                    window: int = WINDOW) -> tuple[float, dt.date | None]:
    """Peak-to-now drawdown in R inside the last ``window`` close days.

    Cumulative R starts from a 0 baseline at the window's start; the peak is
    the latest highest point (the baseline counts, and is dated to the
    window's first day). Returns ``(drawdown rounded to 2 dp, peak day)``,
    ``(0.0, None)`` when the book is at its window peak."""
    tail = days[-window:]
    if not tail:
        return 0.0, None
    cum, peak, peak_day = 0.0, 0.0, tail[0].day
    for close_day in tail:
        cum += close_day.r
        if cum >= peak:
            peak, peak_day = cum, close_day.day
    drawdown = round(peak - cum, 2)
    if drawdown <= 0:
        return 0.0, None
    return drawdown, peak_day


def zone_of(value: float, p80: float, p95: float) -> str:
    """``normal`` at or below p80, ``rough`` up to p95, ``outside`` beyond.

    With ``p80 == p95`` the rough zone is empty."""
    if value <= p80:
        return "normal"
    if value <= p95:
        return "rough"
    return "outside"


def worse_zone(a: str, b: str) -> str:
    """The later of two zones in ``ZONES`` order."""
    return max(a, b, key=ZONES.index)
