"""v180: Turtle Soup plan levels. Every level is an absolute price known at the signal close,
so the alert can rest as orders before the open.

Stop: Low[t] - STRUCTURE_BUFFER_ATR x ATR14[t] through builders._bounded_stop. TURTLE_SOUP is in
strategy_types.STRUCTURAL_DROP_STRATEGIES, so a stop beyond the 2w max_risk_pct (3.0%) from the
signal close DROPS the plan (RISK_CAP); it is never squeezed to 2%.
Target: select_structural_target over the level map's resistances PRE-FILTERED to the frozen
min/max R:R band, measured from the signal close. Pre-filtering is the spec's "no plan when no
level falls in the band": unfiltered, the selector returns a synthetic entry + max_rr x R price
whenever the nearest qualifying level lies beyond the cap.
NO-LOOKAHEAD: reads bars <= index only. A level map built here comes from df.iloc[:index + 1]."""
from __future__ import annotations

from dataclasses import dataclass

from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS, TURTLE_SOUP
from .builders import _bounded_stop
from .params import STRUCTURE_BUFFER_ATR
from .targets import _safe_atr_value, select_structural_target

RISK_CAP = "risk_cap"
NO_LEVEL_IN_BAND = "no_level_in_band"
PLAN_OTHER = "plan_other"
_DIRECTION = "bullish"


@dataclass(frozen=True)
class TurtleSoupLevels:
    """stop/tp1 None with `reason` set when no plan exists at this bar."""

    stop: float | None
    tp1: float | None
    candidates: tuple[float, ...]
    reason: str | None


def in_band(entry: float, stop: float, prices, min_rr: float, max_rr: float) -> list[float]:
    """Prices above `entry` paying between min_rr and max_rr times the risk, nearest first.
    Same relative epsilon as select_structural_target, so a level exactly on either edge counts."""
    risk = entry - stop
    if risk <= 0:
        return []
    eps = 1e-9 * max(1.0, abs(entry))
    low, high = risk * min_rr - eps, risk * max_rr + eps
    return sorted(float(p) for p in prices if p and low <= float(p) - entry <= high)


def _scan_params(scan_params):
    if scan_params is not None:
        return scan_params
    from swingbot.scan_params import ScanParams
    return ScanParams.from_config()


def _resistance_prices(df, index, horizon_key, level_map) -> list[float]:
    """The level map's resistances; built from bars <= index when the caller passed none."""
    if level_map is None:
        level_map = levels.build_level_map(df.iloc[:index + 1], HORIZONS[horizon_key],
                                           float(df["Close"].iloc[index]))
    return [float(lv.price) for lv in level_map[1]]


def turtle_soup_levels(df, index, horizon_key, *, entry, atr_val, level_map=None,
                       scan_params=None) -> TurtleSoupLevels:
    """Stop, target and in-band candidates for a bullish Turtle Soup at bar `index`."""
    raw_stop = float(df["Low"].iloc[index]) - STRUCTURE_BUFFER_ATR * atr_val
    if raw_stop >= entry:
        return TurtleSoupLevels(None, None, (), PLAN_OTHER)
    stop = _bounded_stop(entry, raw_stop, True, TURTLE_SOUP, _DIRECTION, horizon_key)
    if stop is None:
        return TurtleSoupLevels(None, None, (), RISK_CAP)
    params = _scan_params(scan_params)
    min_rr, max_rr = params.min_risk_reward_ratio, params.max_risk_reward_ratio
    band = tuple(in_band(entry, stop, _resistance_prices(df, index, horizon_key, level_map),
                         min_rr, max_rr))
    if not band:
        return TurtleSoupLevels(stop, None, (), NO_LEVEL_IN_BAND)
    tp1 = select_structural_target(entry, stop, True, band, min_rr, max_rr)
    return TurtleSoupLevels(stop, tp1, band, None)


def turtle_soup_branch(inputs):
    """builders._STRUCTURAL_BRANCHES entry: (stop, tp1, candidates, None), or None."""
    if inputs.direction != _DIRECTION:
        return None
    picked = turtle_soup_levels(inputs.df, inputs.index, inputs.horizon_key, entry=inputs.close,
                                atr_val=inputs.atr_val, level_map=inputs.level_map,
                                scan_params=inputs.scan_params)
    if picked.reason is not None:
        return None
    return picked.stop, picked.tp1, list(picked.candidates), None


def turtle_soup_rejection_reason(df, index, horizon_key, scan_params=None, level_map=None) -> str:
    """Why build_strategy_plan returned None for a Turtle Soup signal at `index`: RISK_CAP,
    NO_LEVEL_IN_BAND, or PLAN_OTHER (the levels were fine, so a gate or the geometry check
    said no). Sized exactly as build_strategy_plan sizes it: signal close, safe ATR14."""
    from swingbot.core.market.indicators import atr as atr_indicator

    entry = float(df["Close"].iloc[index])
    atr_val = _safe_atr_value(entry, float(atr_indicator(df, 14).iloc[index]))
    picked = turtle_soup_levels(df, index, horizon_key, entry=entry, atr_val=atr_val,
                                level_map=level_map, scan_params=scan_params)
    return picked.reason or PLAN_OTHER
