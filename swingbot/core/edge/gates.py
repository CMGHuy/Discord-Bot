"""Entry gates driven by distributions, not vibes: overnight gap noise,
pullback volume dry-up (v122), and earnings blackout (E18). Each is a pure
function; wiring is always flag-gated and fold-validated before live behavior."""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.market import entry_filters
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
