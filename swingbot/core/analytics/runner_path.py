"""v142: the runner's post-TP1 price path, stamped onto a plan at runner close.

`compute_runner_path` is pure. R is measured against the plan's initial risk
(`entry_price - stop_loss`), the basis of `metrics.r_multiple`. A daily bar
cannot order intrabar events, so:

- on the TP1 session only the bar's favourable extreme counts (it can only
  have printed after TP1 was crossed); its adverse extreme may predate TP1;
- on the exit session of a stop / floor / trail exit the bar counts for
  nothing -- the exit is assumed to have come first;
- the runner's own fills (TP1 leg, runner leg) are prices that certainly
  traded, so each is a point on its session.

`cached_daily_bars` reads the live scan's own disk cache (market_data/daily)
and never fetches. `stamp_runner_path` never raises: a close is never blocked
by its stamp.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import NamedTuple

import pandas as pd

from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar

log = logging.getLogger(__name__)

#: R levels of the TP2 ladder, keyed in the stamp as "1.5", "2.0", ...
LADDER_R = (1.5, 2.0, 2.5, 3.0, 4.0)
#: Runner closes where a resting stop took the position out (floor, trail).
STOP_EXIT_REASONS = frozenset({"tp1_runner_be", "tp1_runner_trail"})
_TOUCH_TOL = 1e-9


class RunnerContext(NamedTuple):
    entry: float
    risk: float
    sign: int
    r_tp1: float
    exit_r: float | None      # None: no runner leg on the plan (a manual close)
    stop_exit: bool
    tp1_day: dt.date
    exit_day: dt.date


def et_day(stamp) -> dt.date | None:
    """The US/Eastern date of an ISO timestamp; None when absent or unparseable."""
    if not stamp:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(US_MARKET_TZ).date()


def transition_day(plan, status: str) -> dt.date | None:
    """ET date of the first `status_history` entry with `status`."""
    for entry in plan.status_history or []:
        if entry.get("status") == status:
            return et_day(entry.get("at"))
    return None


def close_reason(plan) -> str | None:
    """The reason recorded on the plan's CLOSED transition."""
    return next((entry.get("reason") for entry in plan.status_history or []
                 if entry.get("status") == "CLOSED"), None)


def tp1_leg(plan) -> dict | None:
    return next((leg for leg in plan.legs_realized or [] if leg.get("reason") == "tp1"), None)


def runner_leg(plan) -> dict | None:
    """The realised leg that closed the runner; None while open, and for a
    manual close (the admin close records no leg on the plan)."""
    return next((leg for leg in plan.legs_realized or [] if leg.get("reason") != "tp1"), None)


def session_span(start: dt.date, end: dt.date) -> int:
    """NYSE sessions from `start` to `end`, not counting `start`; 0 for one session."""
    return max(0, len(nyse_calendar().sessions(start, end)) - 1)


def _leg_r(leg: dict | None, entry: float, risk: float, sign: int) -> float | None:
    if leg is None:
        return None
    if leg.get("r") is not None:
        return float(leg["r"])
    price = leg.get("exit_price")
    return None if price is None else (float(price) - entry) * sign / risk


def runner_context(plan) -> RunnerContext | None:
    """Everything the path needs from the plan, or None for a record that
    cannot carry one (no fill, zero risk, no TP1 leg, no dated transitions)."""
    entry, stop = plan.entry_price, plan.stop_loss
    if entry is None or stop is None or entry == stop:
        return None
    risk, sign = abs(entry - stop), (1 if plan.direction == "bullish" else -1)
    r_tp1 = _leg_r(tp1_leg(plan), entry, risk, sign)
    tp1_day, exit_day = transition_day(plan, "PARTIAL"), transition_day(plan, "CLOSED")
    if r_tp1 is None or tp1_day is None or exit_day is None or exit_day < tp1_day:
        return None
    return RunnerContext(entry, risk, sign, r_tp1, _leg_r(runner_leg(plan), entry, risk, sign),
                         close_reason(plan) in STOP_EXIT_REASONS, tp1_day, exit_day)


def _bar_extremes(bars, ctx: RunnerContext) -> dict[dt.date, tuple[float, float]]:
    """{session: (favourable R, adverse R)} for every usable bar in the window."""
    if bars is None or len(bars) == 0 or not {"High", "Low"} <= set(bars.columns):
        return {}
    out: dict[dt.date, tuple[float, float]] = {}
    for stamp, high, low in zip(bars.index, bars["High"], bars["Low"]):
        day = pd.Timestamp(stamp).date()
        if not (ctx.tp1_day <= day <= ctx.exit_day) or pd.isna(high) or pd.isna(low):
            continue
        fav, adv = (high, low) if ctx.sign > 0 else (low, high)
        out[day] = ((float(fav) - ctx.entry) * ctx.sign / ctx.risk,
                    (float(adv) - ctx.entry) * ctx.sign / ctx.risk)
    return out


def _window(ctx: RunnerContext) -> tuple[list[dt.date], list[dt.date]]:
    """(every day the path walks, the days whose bar must exist). The exit
    session's bar is optional: live, it is usually still forming."""
    calendar = nyse_calendar()
    days = sorted(set(calendar.sessions(ctx.tp1_day, ctx.exit_day)) | {ctx.tp1_day, ctx.exit_day})
    required = [day for day in days if day != ctx.exit_day and calendar.is_session(day)]
    return days, required


def _day_points(ctx: RunnerContext, day: dt.date, bar) -> tuple[list[float], list[float]]:
    """(favourable, adverse) R points one session contributes."""
    fav: list[float] = []
    adv: list[float] = []
    is_tp1, is_exit = day == ctx.tp1_day, day == ctx.exit_day
    if is_tp1:
        fav.append(ctx.r_tp1)
        adv.append(ctx.r_tp1)
    if is_exit and ctx.exit_r is not None:
        fav.append(ctx.exit_r)
        adv.append(ctx.exit_r)
    if bar is not None and not (is_exit and ctx.stop_exit):
        fav.append(bar[0])
        if not is_tp1:
            adv.append(bar[1])
    return fav, adv


def _first_touch(best_by_day: dict[dt.date, float], level: float) -> str | None:
    return next((day.isoformat() for day in sorted(best_by_day)
                 if best_by_day[day] >= level - _TOUCH_TOL), None)


def _summarise(ctx: RunnerContext, days, extremes, source: str) -> dict:
    best_by_day: dict[dt.date, float] = {}
    adverse: list[float] = []
    for day in days:
        fav, adv = _day_points(ctx, day, extremes.get(day))
        if fav:
            best_by_day[day] = max(fav)
        adverse.extend(adv)
    return {
        "mfe_r": round(max([ctx.r_tp1, *best_by_day.values()]), 4),
        "mae_r": round(min(adverse), 4),
        "ladder": {f"{level:.1f}": _first_touch(best_by_day, level) for level in LADDER_R},
        "sessions_after_tp1": session_span(ctx.tp1_day, ctx.exit_day),
        "source": source,
    }


def compute_runner_path(plan, bars, *, source: str = "live") -> dict | None:
    """The `runner_path` stamp for a closed partial plan, or None when the
    plan cannot carry one or `bars` do not cover TP1 session .. exit session."""
    ctx = runner_context(plan)
    if ctx is None:
        return None
    days, required = _window(ctx)
    extremes = _bar_extremes(bars, ctx)
    if any(day not in extremes for day in required):
        return None
    return _summarise(ctx, days, extremes, source)


def cached_daily_bars(ticker: str):
    """The live scan's daily cache (`market_data/daily`), from disk. Never a fetch."""
    from swingbot.core.marketdata import data_store
    return data_store.load_normalized(ticker, "daily")


def stamp_runner_path(plan, bars_fn, *, source: str = "live") -> dict | None:
    """Set `plan.runner_path` from `bars_fn(ticker)`; None plus one log line
    when the bars do not cover the window. Never raises."""
    path = None
    try:
        bars = bars_fn(plan.ticker) if bars_fn is not None else None
        path = compute_runner_path(plan, bars, source=source)
    except Exception as exc:
        log.warning("runner_path: stamp failed for %s (%s): %s", plan.plan_id, plan.ticker, exc,
                    exc_info=True)
    if path is None:
        log.info("runner_path: no stamp for %s (%s) -- bars do not cover the runner window",
                 plan.plan_id[:8], plan.ticker)
    plan.runner_path = path
    return path
