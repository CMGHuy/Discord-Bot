"""v239: the daily bear-regime classifier, run in shadow.

Pure: completed daily SPY and ^VIX frames in, one ``RegimeDay`` out. The label
is FOR trading session ``session_date`` (D) and reads only bars dated on or
before ``last_session`` (s), the last completed session before D. ``classify``
truncates its frames to s itself, so a caller that forgot the cut cannot leak
a later bar (docs/claude/architecture.md NO-LOOKAHEAD).

Rules (spec section "The classifier"), all indexed from s:
  BEAR        C < SMA200 and (SMA200 < SMA200[s-20] or SMA50 < SMA200)
  CORRECTION  not BEAR, C < SMA50, SMA50 < SMA50[s-5] and SMA200 > SMA200[s-20]
  NORMAL      neither
  UNKNOWN     SPY's last bar is not s (stale), fewer than MIN_BARS bars, or a
              non-finite close feeding SMA200[s-20..s] or a non-finite H[s-1]
  stress      V[s] >= STRESS_VIX; None when no ^VIX bar is dated exactly s
  pullback    CORRECTION, V[s] <= PULLBACK_VIX_RATIO * max(V[s-4..s]) and
              C[s] > H[s-1]; False with reason "vix_gap" on a window hole
The day label is raw (no hysteresis): the B7-B9 screens use exactly these
rules; smoothing for people lives in regime_episodes. The constants are
frozen: changing one is a new idea under the slate rows, never a knob.
"""
from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Final

import numpy as np
import pandas as pd

MIN_BARS: Final = 220
SMA_FAST: Final = 50
SMA_SLOW: Final = 200
SLOW_SLOPE_LAG: Final = 20
FAST_SLOPE_LAG: Final = 5
STRESS_VIX: Final = 25.0
PULLBACK_VIX_RATIO: Final = 0.85
PULLBACK_VIX_WINDOW: Final = 5

SPY: Final = "SPY"
VIX: Final = "^VIX"

BEAR: Final = "BEAR"
CORRECTION: Final = "CORRECTION"
NORMAL: Final = "NORMAL"
UNKNOWN: Final = "UNKNOWN"
STATES: Final = (BEAR, CORRECTION, NORMAL, UNKNOWN)

WOULD_VETO: Final = "would_veto"
CAUTION: Final = "caution"
PULLBACK_WATCH: Final = "pullback_watch"
ALIGNED: Final = "aligned"
NONE: Final = "none"

VIX_GAP: Final = "vix_gap"
REASON_STALE: Final = "stale"
REASON_SHORT: Final = "short_history"
REASON_NAN: Final = "nan"

_DATE_FIELDS = ("session_date", "last_bar_date")
_FLOAT_FIELDS = ("spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20",
                 "spy_high_prev", "vix_close", "vix_max5")


_LONG_BY_STATE = {BEAR: WOULD_VETO, CORRECTION: CAUTION}

@dataclass(frozen=True)
class RegimeDay:
    """One labelled session. ``session_date`` is D; ``last_bar_date`` is the
    date of SPY's last bar the label read (s, unless the frame was stale)."""

    session_date: dt.date
    last_bar_date: dt.date | None
    state: str
    stress: bool | None = None
    pullback_trigger: bool = False
    pullback_reason: str | None = None
    spy_close: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    sma50_lag5: float | None = None
    sma200_lag20: float | None = None
    spy_high_prev: float | None = None
    vix_close: float | None = None
    vix_max5: float | None = None
    spy_provider: str | None = None
    vix_provider: str | None = None
    unknown_reason: str | None = None

    def to_row(self) -> dict:
        """The ``market_regime_days`` columns plus ``doc``; no ``computed_at``."""
        row = {name: getattr(self, name) for name in ROW_COLUMNS}
        row["doc"] = {"unknown_reason": self.unknown_reason}
        return row

    @classmethod
    def from_row(cls, row: Mapping) -> "RegimeDay":
        values = {name: row.get(name) for name in ROW_COLUMNS}
        for name in _DATE_FIELDS:
            values[name] = _as_date(values[name])
        for name in _FLOAT_FIELDS:
            values[name] = None if values[name] is None else float(values[name])
        values["pullback_trigger"] = bool(values["pullback_trigger"])
        doc = row.get("doc") or {}
        return cls(**values, unknown_reason=doc.get("unknown_reason"))


ROW_COLUMNS: Final[tuple[str, ...]] = tuple(f.name for f in fields(RegimeDay) if f.name != "unknown_reason")


def _as_date(value) -> dt.date | None:
    if value is None or (isinstance(value, dt.date) and not isinstance(value, dt.datetime)):
        return value
    if isinstance(value, dt.datetime):
        return value.date()
    return dt.date.fromisoformat(str(value)[:10])


def _dates(df: pd.DataFrame) -> np.ndarray:
    """Each bar's wall date (a tz-aware index keeps its own calendar day)."""
    return pd.DatetimeIndex(df.index).date


def _upto(df: pd.DataFrame | None, last_session: dt.date) -> pd.DataFrame | None:
    if df is None or len(df) == 0:
        return None
    return df.loc[_dates(df) <= last_session]


def _last_date(frame: pd.DataFrame | None) -> dt.date | None:
    if frame is None or len(frame) == 0:
        return None
    return pd.Timestamp(frame.index[-1]).date()


def _column(frame: pd.DataFrame, name: str) -> np.ndarray:
    return pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=float)


def _finite_inputs(frame: pd.DataFrame) -> bool:
    closes = _column(frame, "Close")[-(SMA_SLOW + SLOW_SLOPE_LAG):]
    return bool(np.isfinite(closes).all()) and math.isfinite(_column(frame, "High")[-2])


def _unknown_reason(frame: pd.DataFrame | None, last_session: dt.date) -> str | None:
    if _last_date(frame) != last_session:
        return REASON_STALE
    if len(frame) < MIN_BARS:
        return REASON_SHORT
    if not _finite_inputs(frame):
        return REASON_NAN
    return None


def _sma(closes: np.ndarray, n: int, lag: int = 0) -> float:
    end = len(closes) - lag
    return float(closes[end - n:end].mean())


def _measures(frame: pd.DataFrame) -> dict:
    closes = _column(frame, "Close")
    return {"spy_close": float(closes[-1]),
            "sma50": _sma(closes, SMA_FAST),
            "sma200": _sma(closes, SMA_SLOW),
            "sma50_lag5": _sma(closes, SMA_FAST, FAST_SLOPE_LAG),
            "sma200_lag20": _sma(closes, SMA_SLOW, SLOW_SLOPE_LAG),
            "spy_high_prev": float(_column(frame, "High")[-2])}


def _state(m: dict) -> str:
    close, fast, slow = m["spy_close"], m["sma50"], m["sma200"]
    if close < slow and (slow < m["sma200_lag20"] or fast < slow):
        return BEAR
    if close < fast and fast < m["sma50_lag5"] and slow > m["sma200_lag20"]:
        return CORRECTION
    return NORMAL


def _finite_or_none(value) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _vix_window(vix: pd.DataFrame | None,
                window: list[dt.date]) -> tuple[float | None, float | None]:
    """(V[s], max(V[s-4..s])) matched by exact date, never filled; the max is
    None when any of the window's bars is missing or NaN."""
    frame = _upto(vix, window[-1])
    if frame is None or len(frame) == 0:
        return None, None
    series = pd.Series(_column(frame, "Close"), index=_dates(frame))
    series = series[~series.index.duplicated(keep="last")]
    values = [_finite_or_none(series.get(d)) for d in window]
    if any(v is None for v in values):
        return values[-1], None
    return values[-1], max(values)


def _pullback(state: str, m: dict, vix_close: float | None,
              vix_max5: float | None) -> tuple[bool, str | None]:
    if state != CORRECTION:
        return False, None
    if vix_close is None or vix_max5 is None:
        return False, VIX_GAP
    eased = vix_close <= PULLBACK_VIX_RATIO * vix_max5
    return bool(eased and m["spy_close"] > m["spy_high_prev"]), None


def classify(spy: pd.DataFrame, vix: pd.DataFrame | None, *, last_session: dt.date,
             session_date: dt.date, spy_provider: str | None = None,
             vix_provider: str | None = None) -> RegimeDay:
    """Label session ``session_date`` from bars dated on or before ``last_session``."""
    frame = _upto(spy, last_session)
    base = {"session_date": session_date, "last_bar_date": _last_date(frame),
            "spy_provider": spy_provider, "vix_provider": vix_provider}
    reason = _unknown_reason(frame, last_session)
    if reason is not None:
        return RegimeDay(state=UNKNOWN, unknown_reason=reason, **base)
    measures = _measures(frame)
    state = _state(measures)
    vix_close, vix_max5 = _vix_window(vix, list(_dates(frame)[-PULLBACK_VIX_WINDOW:]))
    trigger, why = _pullback(state, measures, vix_close, vix_max5)
    return RegimeDay(state=state, stress=None if vix_close is None else vix_close >= STRESS_VIX,
                     pullback_trigger=trigger, pullback_reason=why, vix_close=vix_close,
                     vix_max5=vix_max5, **measures, **base)


def shadow_action(state: str, stress: bool | None, pullback_trigger: bool, direction: str) -> str:
    """What the engine WOULD do with a plan of ``direction`` (spec table).

    A pullback day wins over would_veto: it is the panic easing inside a
    correction, so "would skip" and "pullback watch" never show together.
    """
    if direction == "bearish":
        return ALIGNED if state in (BEAR, CORRECTION) else NONE
    if direction != "bullish":
        return NONE
    if state == CORRECTION and pullback_trigger:
        return PULLBACK_WATCH
    if state == CORRECTION and stress is True:
        return WOULD_VETO
    return _LONG_BY_STATE.get(state, NONE)
