"""The v191 ATR stop band, using raw Wilder ATR14 of completed bars.

Pure arithmetic: no config reads or frame writes. The caller supplies the
creating bar's completed frame; ATR is never the horizon-scaled floor.
"""
import math
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import NamedTuple

from swingbot.core.market.indicators import atr
from swingbot.core.risk_limits import planned_loss_pct

ATR_PERIOD = 14
BAND_CEILING_ATR = 2.0
FLOOR_GRID = (0.75, 1.0, 1.5)
MOVED_FLOOR = "floor"
MOVED_CEILING = "ceiling"
MOVED_UNTOUCHED = "untouched"
REASON_NO_TARGET = "band_no_target"
REASON_RR_DROP = "band_rr_drop"
REASON_NO_ATR = "band_no_atr"
REASON_SIZE_ZERO = "band_size_zero"
_TOL = 1e-9  # A distance exactly on either boundary stays untouched.


class AtrBand(NamedTuple):
    k: float
    atr_pct: float | None


class BandStop(NamedTuple):
    stop: float
    moved_by: str
    lo_pct: float
    hi_pct: float
    distance_pct: float


def raw_atr14_pct(df, entry: float) -> float | None:
    """Raw Wilder ATR14 of the last supplied row, as a percent of entry."""
    if df is None or len(df) == 0 or entry is None or entry <= 0:
        return None
    try:
        value = float(atr(df, ATR_PERIOD).iloc[-1])
    except Exception:
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value / entry * 100.0


def tick_size(price: float) -> float:
    return 0.01 if price >= 1.0 else 0.0001


def round_away_from_entry(stop: float, entry: float, is_bull: bool) -> float:
    """Round on the entry's tick away from entry: longs floor, shorts ceil.

    Nine decimals first keep float noise from being taken for another tick.
    """
    tick = Decimal(str(tick_size(entry)))
    exact = Decimal(repr(round(float(stop), 9)))
    steps = (exact / tick).to_integral_value(rounding=ROUND_FLOOR if is_bull else ROUND_CEILING)
    return float(steps * tick)


def _on_stop_side(entry, level, is_bull) -> bool:
    return level < entry if is_bull else level > entry


def _usable(entry, level, is_bull, atr_pct, k) -> bool:
    if k is None or k <= 0 or atr_pct is None or not atr_pct > 0:
        return False
    if entry is None or entry <= 0 or level is None:
        return False
    return _on_stop_side(entry, level, is_bull)


def _offset_stop(entry: float, pct: float, is_bull: bool) -> float:
    raw = entry * (1 - pct / 100.0) if is_bull else entry * (1 + pct / 100.0)
    return round_away_from_entry(raw, entry, is_bull)


def band_stop(entry, level, is_bull, atr_pct, k) -> BandStop | None:
    """Keep an in-band level or move it to the ATR floor or ceiling."""
    if k is not None and k >= BAND_CEILING_ATR:
        raise ValueError(f"ATR floor k={k} must be below the {BAND_CEILING_ATR} x ATR ceiling")
    if not _usable(entry, level, is_bull, atr_pct, k):
        return None
    lo, hi = k * atr_pct, BAND_CEILING_ATR * atr_pct
    d = planned_loss_pct(entry, level)
    if d < lo - _TOL:
        stop, moved = _offset_stop(entry, lo, is_bull), MOVED_FLOOR
    elif d > hi + _TOL:
        stop, moved = _offset_stop(entry, hi, is_bull), MOVED_CEILING
    else:
        stop, moved = float(level), MOVED_UNTOUCHED
    return BandStop(stop, moved, lo, hi, planned_loss_pct(entry, stop))


def band_for(df, entry: float, k: float) -> AtrBand | None:
    """Describe an active band, preserving unavailable ATR for its caller."""
    if not k or k <= 0:
        return None
    return AtrBand(float(k), raw_atr14_pct(df, entry))
