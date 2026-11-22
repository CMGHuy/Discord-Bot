"""v238 rungs 3-4: the bot's stop and target on each event bar (v230 spec Part B).

Every level reads only ``df.iloc[: signal_pos + 1]``. The stand-ins the spec
leaves to the builder are recorded in BOT_SHAPE and printed in every rung 3/4
results doc (plan v238 index ruling 7)."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import race
from swingbot.core.backtesting.screen.ladder import LadderEvent
from swingbot.core.market import levels as market_levels
from swingbot.core.market.indicators import atr as atr_indicator
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.builders import strategy_entry_reference
from swingbot.core.planning.targets import _safe_atr_value, select_structural_target
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct

BOT_SHAPE = {
    "stop_entry_point": (
        "swingbot/core/planning/builders.py _atr_plan stop geometry (the _atr_branch "
        "every strategy without a structural branch sizes through): "
        "HORIZONS[horizon_key]['atr_stop_multiple'] x ATR14 "
        "(market.indicators.atr, targets._safe_atr_value) from "
        "builders.strategy_entry_reference (the signal close), taken before "
        "_bounded_stop: a wide stop is sized down, never capped or dropped"),
    "target_entry_point": (
        "swingbot/core/planning/targets.py select_structural_target over "
        "market.levels.target_candidates(*build_level_map(frame, HORIZONS[horizon_key], "
        "close), direction), band ScanParams.from_config() min/max_risk_reward_ratio"),
    "strategy": "RSI",
    "horizon_key": "2w",
    "why": (
        "an idea has no strategy or horizon of its own: RSI sizes through the generic "
        "ATR branch and 2w (14 holding days) is the horizon nearest the screen's caps; "
        "the confluence level map is the bot's nearest-real-level source, so rung 4's "
        "no-level attrition is real (the ATR-ladder candidates always qualify)"),
}
_PLAN_SIDE = {"long": "bullish", "short": "bearish"}


def plan_direction(direction: str) -> str:
    """The screen's long/short as the planning layer's bullish/bearish."""
    if direction not in _PLAN_SIDE:
        raise ValueError(f"unknown direction {direction!r}; expected 'long' or 'short'")
    return _PLAN_SIDE[direction]


def signal_frame(df: pd.DataFrame, signal_pos: int) -> pd.DataFrame:
    """The frame as it stood at the signal bar's close."""
    if not 0 <= signal_pos < len(df):
        raise IndexError(f"signal_pos {signal_pos} outside a {len(df)}-bar frame")
    return df.iloc[: signal_pos + 1]


def _close_and_atr(frame: pd.DataFrame, pos: int) -> tuple[float, float]:
    close = strategy_entry_reference(frame, pos, BOT_SHAPE["strategy"])
    return close, _safe_atr_value(close, float(atr_indicator(frame, 14).iloc[pos]))


def bot_stop(df: pd.DataFrame, signal_pos: int, *, direction: str) -> float | None:
    """The bot's ATR-branch stop from the signal close; None on an unusable close."""
    side = plan_direction(direction)
    close, atr_val = _close_and_atr(signal_frame(df, signal_pos), signal_pos)
    if not (np.isfinite(close) and close > 0):
        return None
    risk = HORIZONS[BOT_SHAPE["horizon_key"]]["atr_stop_multiple"] * atr_val
    return close - risk if side == "bullish" else close + risk


def clamp_would_drop(entry: float, stop: float, *, direction: str) -> bool:
    """True when the 2% price-distance cap would have refused this stop."""
    plan_direction(direction)
    return planned_loss_pct(entry, stop) > HARD_MAX_PLANNED_LOSS_PCT


def rung3_levels(df: pd.DataFrame, signal_pos: int, *,
                 direction: str) -> tuple[float | None, float | None]:
    """(bot stop, target at race.REWARD_RISK x the bot stop's risk), from the close."""
    stop = bot_stop(df, signal_pos, direction=direction)
    if stop is None:
        return None, None
    close = float(df["Close"].iloc[signal_pos])
    sign = 1.0 if direction == "long" else -1.0
    return stop, close + sign * race.REWARD_RISK * abs(close - stop)


ATTRITION = ("no_level_in_band", "risk_cap")


def _scan_params():
    """The live reward:risk band (a seam the tests replace)."""
    from swingbot.scan_params import ScanParams
    return ScanParams.from_config()


def _target_candidates(frame: pd.DataFrame, close: float, side: str) -> list[float]:
    """The confluence level map's trade-side prices, nearest first."""
    supports, resistances = market_levels.build_level_map(
        frame, HORIZONS[BOT_SHAPE["horizon_key"]], close)
    return market_levels.target_candidates(supports, resistances, side)


def rung4_levels(df: pd.DataFrame, signal_pos: int, *,
                 direction: str) -> tuple[float | None, float | None, str | None]:
    """(rung 3's stop, the bot's band target, attrition reason or None)."""
    side = plan_direction(direction)
    stop = bot_stop(df, signal_pos, direction=direction)
    close = float(df["Close"].iloc[signal_pos])
    if stop is None or clamp_would_drop(close, stop, direction=direction):
        return stop, None, "risk_cap"
    params = _scan_params()
    target = select_structural_target(
        close, stop, side == "bullish",
        _target_candidates(signal_frame(df, signal_pos), close, side),
        params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    if target is None:
        return stop, None, "no_level_in_band"
    return stop, float(target), None


def _one_per_ticker(events: list[LadderEvent]) -> list[LadderEvent]:
    kept, busy = [], {}
    for event in sorted(events, key=lambda e: (e.signal_date, e.ticker)):
        if event.signal_date >= busy.get(event.ticker, ""):
            kept.append(event)
            busy[event.ticker] = event.exit_date
    return kept


def _concurrent(events: list[LadderEvent], max_open: int) -> list[LadderEvent]:
    kept, open_exits = [], []
    for event in sorted(events, key=lambda e: (e.entry_date, e.ticker)):
        open_exits = [x for x in open_exits if x >= event.entry_date]
        if len(open_exits) < max_open:
            kept.append(event)
            open_exits.append(event.exit_date)
    return kept


def book_survival(events: Iterable[LadderEvent], *, max_open: int) -> dict:
    """Shares of all events that survive one position per ticker, and that
    plus the concurrent-position limit; signals per day. Never gating."""
    if max_open < 1:
        raise ValueError("max_open must be at least 1")
    events = list(events)
    if not events:
        return {"one_per_ticker_share": None, "concurrent_share": None,
                "signals_per_day_p95": None, "signals_per_day_max": 0}
    single = _one_per_ticker(events)
    both = _concurrent(single, max_open)
    per_day = np.array(list(Counter(e.signal_date for e in events).values()), dtype=float)
    return {"one_per_ticker_share": len(single) / len(events),
            "concurrent_share": len(both) / len(events),
            "signals_per_day_p95": float(np.percentile(per_day, 95)),
            "signals_per_day_max": int(per_day.max())}
