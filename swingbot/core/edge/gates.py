"""Entry gates driven by distributions, not vibes: overnight gap noise,
pullback volume dry-up (v122), headroom veto (v135), and earnings blackout (E18). Each is a pure
function; wiring is always flag-gated and fold-validated before live behavior."""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.market import entry_filters
from swingbot.core.market.levels import strategy_family
from swingbot.core.market.strategy_types import SHORT_STRATEGIES
from swingbot.core.market.structure import pullback_vol_ratio


def gap_stats(df: pd.DataFrame, lookback: int = 250) -> dict:
    """Distribution of overnight gaps |Open / prev Close - 1| in percent."""
    tail = df.tail(lookback + 1)
    gaps = (tail["Open"] / tail["Close"].shift(1) - 1.0).abs().dropna() * 100.0
    if gaps.empty:
        return {"p90_gap_pct": 0.0, "p99_gap_pct": 0.0, "n": 0}
    return {"p90_gap_pct": float(np.percentile(gaps, 90)),
            "p99_gap_pct": float(np.percentile(gaps, 99)),
            "n": int(len(gaps))}


def stop_beyond_gap_noise(stop_distance_pct: float, gap_p90_pct: float,
                          cushion: float = 1.0) -> bool:
    """A stop inside the ticker's routine overnight gap is decided by the
    open print, not by the setup. True = the stop clears the noise."""
    return stop_distance_pct >= cushion * gap_p90_pct


def _live_sessions_to_reaction(symbol: str, now) -> int | None:
    from swingbot.core.market import earnings_calendar
    from swingbot.core.market.session import now_et
    return earnings_calendar.sessions_to_reaction(symbol, now_et(now).date(), source=earnings_calendar.LiveSource())


def in_earnings_blackout(symbol: str, now=None, sessions: int | None = None,
                         sessions_to_reaction_fn=None) -> bool:
    from swingbot.core.market.earnings_calendar import is_exposed
    window = sessions if sessions is not None else getattr(config, "EARNINGS_BLACKOUT_SESSIONS", 0)
    if window <= 0:
        return False
    return is_exposed((sessions_to_reaction_fn or _live_sessions_to_reaction)(symbol, now), window)


#: v122 frozen pullback list. Adding a name is a new pre-registration.
PULLBACK_DRYUP_STRATEGIES = frozenset({
    "Fibonacci", "EMA Crossover", "Break & Retest", "RSI", "RSI Divergence",
    "MA Ribbon", "VWAP",
})
PULLBACK_VOLUME_REASON = "pullback_volume"
_EMA_CROSSOVER = "EMA Crossover"


def ratio_exceeds(ratio: float | None, max_ratio: float) -> bool:
    """The comparison alone: known, and strictly above a positive `max_ratio`.
    None passes, and so does NaN (a comparison with NaN is False)."""
    return max_ratio > 0 and ratio is not None and ratio > max_ratio


def pullback_dryup_rejects(df: pd.DataFrame, direction: str, max_ratio: float) -> bool:
    """v122 predicate on completed daily bars; reject iff the pullback/impulse
    volume ratio exceeds `max_ratio`. `max_ratio <= 0` is off and never computes.

    The caller owns slicing off any still-forming bar before calling this gate.
    """
    if max_ratio <= 0:
        return False
    return ratio_exceeds(pullback_vol_ratio(df, direction), max_ratio)


def _ema_crossover_pullback_mode() -> bool:
    return entry_filters.DEFAULT_PARAMS.get(_EMA_CROSSOVER, {}).get("entry_mode") == "pullback"


def strategy_in_dryup_scope(strategy: str | None) -> bool:
    """The frozen list. EMA Crossover counts only while its entry mode is pullback."""
    if strategy not in PULLBACK_DRYUP_STRATEGIES:
        return False
    return strategy != _EMA_CROSSOVER or _ema_crossover_pullback_mode()


def pullback_dryup_scoped(source: str, strategy: str | None = None) -> bool:
    """Whether this entry source (and strategy) is gated under today's config."""
    if getattr(config, "PULLBACK_DRYUP_SCOPE", "off") != source:
        return False
    return source == "confluence" or strategy_in_dryup_scope(strategy)


def _max_ratio() -> float:
    return float(getattr(config, "PULLBACK_DRYUP_MAX_RATIO", 0.0) or 0.0)


def pullback_dryup_blocks(df, direction: str, *, source: str,
                          strategy: str | None = None) -> bool:
    """The one call every strategy call site makes (live and replay)."""
    if not pullback_dryup_scoped(source, strategy):
        return False
    return pullback_dryup_rejects(df, direction, _max_ratio())


def filter_pullback_dryup(scenarios, df) -> tuple[list, list]:
    """Split confluence scenarios into (kept, rejected). It is a no-op, and
    computes nothing, unless the confluence scope is active."""
    if not pullback_dryup_scoped("confluence"):
        return list(scenarios), []
    max_ratio = _max_ratio()
    if max_ratio <= 0:
        return list(scenarios), []
    kept, rejected = [], []
    for scenario in scenarios:
        bucket = (rejected if pullback_dryup_rejects(df, scenario.direction, max_ratio)
                  else kept)
        bucket.append(scenario)
    return kept, rejected


#: v135 frozen constant -- not a knob, not a grid axis. Two is the smallest family count
#: that excludes a lone Bollinger band or floor pivot. Changing it is a new pre-registration.
HEADROOM_MIN_FAMILIES = 2
#: v135 frozen list: backtest.ALL_STRATEGIES minus the two VALIDATED badges. Adding a name
#: is a new pre-registration, and no strategy_types.SHORT_STRATEGIES name may ever join it.
HEADROOM_STRATEGIES = frozenset({
    "EMA Crossover", "VWAP", "Fibonacci", "Support/Resistance", "RSI",
    "Elliott Wave", "MA Ribbon", "Break & Retest", "RSI Divergence",
})
HEADROOM_REASON = "headroom"
HEADROOM_SCOPES = ("strategy", "confluence")


def _confirmed(level) -> bool:
    """A level at least HEADROOM_MIN_FAMILIES independent detector families agree on."""
    return len({strategy_family(source) for source in level.sources}) >= HEADROOM_MIN_FAMILIES


def nearest_blocker(entry: float, stop: float, direction: str, levels) -> tuple[float, float] | None:
    """(distance, risk) to the nearest confirmed level strictly beyond `entry` on the target
    side (above for bullish, below for bearish). None when risk is not positive, there are
    no levels, or no confirmed level lies ahead. A NaN price never qualifies."""
    risk = abs(entry - stop)
    if risk <= 0 or not levels:
        return None
    sign = 1.0 if direction == "bullish" else -1.0
    ahead = [sign * (level.price - entry) for level in levels if _confirmed(level)]
    ahead = [distance for distance in ahead if distance > 0]
    return (min(ahead), risk) if ahead else None


def blocker_inside(reading, min_r: float) -> bool:
    """The comparison alone, shared by the gate and the clause-6 baseline flags: a confirmed
    level exists and sits strictly nearer than `min_r` x risk. A level exactly at the bound
    does not block."""
    if min_r <= 0 or reading is None:
        return False
    distance, risk = reading
    return bool(distance < min_r * risk)


def headroom_rejects(entry: float, stop: float, direction: str, levels, min_r: float) -> bool:
    """v135 predicate: reject iff a confirmed opposing level sits strictly beyond `entry` and
    strictly nearer than `min_r` x |entry - stop|. `min_r <= 0` is off and never computes.

    Pure: it reads only the prices and levels the caller hands it. The caller owns handing
    it levels built from bars at or before the decision bar."""
    if min_r <= 0:
        return False
    return blocker_inside(nearest_blocker(entry, stop, direction, levels), min_r)


def strategy_in_headroom_scope(strategy: str | None) -> bool:
    """The frozen list. A SHORT_STRATEGIES name is never gated, whatever the list says."""
    return strategy in HEADROOM_STRATEGIES and strategy not in SHORT_STRATEGIES


def _headroom_min_r() -> float:
    return float(getattr(config, "HEADROOM_MIN_R", 0.0) or 0.0)


def headroom_active(source: str, strategy: str | None = None) -> bool:
    """Whether the veto gates this entry source (and strategy) under today's config. It is
    inert unless the scope matches AND HEADROOM_MIN_R > 0, so an inactive call site builds
    no level map."""
    if getattr(config, "HEADROOM_SCOPE", "off") != source or _headroom_min_r() <= 0:
        return False
    return source == "confluence" or strategy_in_headroom_scope(strategy)


def planned_entry(plan) -> float:
    """The plan's planned entry: its filled price when it has one, else its trigger."""
    entry = getattr(plan, "entry_price", None)
    return plan.trigger_price if entry is None else entry


def level_map_levels(level_map) -> list:
    """Flatten a build_level_map (supports, resistances) pair; None means no map."""
    if not level_map:
        return []
    supports, resistances = level_map
    return [*supports, *resistances]


def headroom_blocks_plan(plan, level_map, *, strategy: str | None) -> bool:
    """The one call every strategy call site makes (live and replay), after the plan is
    built. An inactive gate returns before touching the plan or the map."""
    if plan is None or not headroom_active("strategy", strategy):
        return False
    return headroom_rejects(planned_entry(plan), plan.stop_loss, plan.direction,
                            level_map_levels(level_map), _headroom_min_r())


def filter_headroom(scenarios, supports, resistances) -> tuple[list, list]:
    """Split confluence scenarios into (kept, rejected) against the very lists they were
    built from. A no-op that computes nothing unless the confluence scope is active."""
    if not headroom_active("confluence"):
        return list(scenarios), []
    min_r, levels = _headroom_min_r(), [*supports, *resistances]
    kept, rejected = [], []
    for scenario in scenarios:
        blocked = headroom_rejects(scenario.entry, scenario.stop_loss, scenario.direction,
                                   levels, min_r)
        (rejected if blocked else kept).append(scenario)
    return kept, rejected
