"""v188: replay a withdrawn plan's price path after its cancel (pure).

Spec: docs/superpowers/specs/2026-10-23-v188-cancelled-plan-precision-design.md.
Reference walk: scripts/reports/autopsy/bars.py (`bisect_right` strictly past
the exit day, SPLIT_GUARD). Core may not import scripts/, so the walk is
re-implemented here, and this module is the one place its rules live.

NO-LOOKAHEAD: bars are walked strictly AFTER the cancel's NYSE trading date and
no later than `until`. Frames are `daily_delta.read_daily` output: a tz-naive
exchange-date DatetimeIndex with Open/High/Low/Close, the forming bar never
persisted. A same-bar stop + TP1 touch counts as the stop (the simulators'
conservative convention) and is flagged as a tie.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.market.strategy_types import HORIZONS

OUTCOMES = ("right", "wrong", "unresolved", "untriggered_after_cancel")
SPLIT_GUARD = 0.25   # mirrors scripts/reports/autopsy/bars.py


@dataclass(frozen=True)
class Replay:
    outcome: str            # one of OUTCOMES
    r: float | None         # right -1.0; wrong full target R; unresolved MTM or None
    tie: bool               # decided by a same-bar stop+TP1 touch
    touch_day: date | None
    exit_day: date | None
    until: date
    elapsed: bool


def trading_date(at: str) -> date:
    """The NYSE date of an ISO timestamp; a naive one is read as UTC."""
    text = str(at).strip()
    if len(text) == 10:
        return date.fromisoformat(text)
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(US_MARKET_TZ).date()


def window_end(start: date, horizon_key: str) -> date | None:
    """`start` plus the horizon's max holding days (calendar); None if unknown."""
    spec = HORIZONS.get(horizon_key)
    if not spec:
        return None
    return start + timedelta(days=int(spec["max_holding_days"]))


def last_bar_day(frame: pd.DataFrame | None) -> date | None:
    if frame is None or frame.empty:
        return None
    return frame.index[-1].date()


def split_guard_ok(frame: pd.DataFrame, day: date, level: float) -> bool:
    """The last close on or before `day` lies within SPLIT_GUARD of `level`."""
    upto = frame[frame.index.normalize() <= pd.Timestamp(day)]
    if upto.empty or level <= 0:
        return False
    close = float(upto["Close"].iloc[-1])
    return abs(close - level) / level <= SPLIT_GUARD


def _walked(frame: pd.DataFrame, after: date, until: date) -> pd.DataFrame:
    days = frame.index.normalize()
    return frame[(days > pd.Timestamp(after)) & (days <= pd.Timestamp(until))]


def _touch_at(bars: pd.DataFrame, bullish: bool, entry: float) -> int | None:
    for i, (high, low) in enumerate(zip(bars["High"], bars["Low"])):
        if (high >= entry) if bullish else (low <= entry):
            return i
    return None


def _first_exit(bars: pd.DataFrame, bullish: bool, stop: float, tp1: float):
    """(outcome, tie, day) of the first stop or TP1 bar, stop checked first."""
    for ts, high, low in zip(bars.index, bars["High"], bars["Low"]):
        stop_hit = low <= stop if bullish else high >= stop
        tp1_hit = high >= tp1 if bullish else low <= tp1
        if stop_hit:
            return "right", bool(tp1_hit), ts.date()
        if tp1_hit:
            return "wrong", False, ts.date()
    return None


def _mark(bars: pd.DataFrame, bullish: bool, entry: float, stop: float) -> float | None:
    if bars.empty:
        return None
    close = float(bars["Close"].iloc[-1])
    move = close - entry if bullish else entry - close
    return move / abs(entry - stop)


def replay(frame: pd.DataFrame, *, bullish: bool, entry: float, stop: float, tp1: float,
           after: date, until: date, require_touch: bool = True) -> Replay:
    """Walk bars in `(after, until]`; assumes valid levels (risk > 0, TP1 beyond entry)."""
    bars = _walked(frame, after, until)
    last = last_bar_day(frame)
    elapsed = last is not None and last >= until
    start = _touch_at(bars, bullish, entry) if require_touch else (0 if len(bars) else None)
    if start is None:
        outcome = "untriggered_after_cancel" if elapsed and require_touch else "unresolved"
        return Replay(outcome, None, False, None, None, until, elapsed)
    live = bars.iloc[start:]
    touch_day = live.index[0].date()
    hit = _first_exit(live, bullish, stop, tp1)
    if hit is None:
        return Replay("unresolved", _mark(live, bullish, entry, stop), False,
                      touch_day, None, until, elapsed)
    outcome, tie, day = hit
    r = -1.0 if outcome == "right" else abs(tp1 - entry) / abs(entry - stop)
    return Replay(outcome, r, tie, touch_day, day, until, elapsed)
