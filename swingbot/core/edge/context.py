"""No-lookahead entry-context snapshots for v93 trade records."""
from __future__ import annotations

import math

from swingbot.core.edge.gates import gap_stats, stop_beyond_gap_noise
from swingbot.core.market.indicators import adx, atr, ema, rsi
from swingbot.core.scanning.regime import _HTF_EMA_PERIOD

HTF_EMA_PERIOD = _HTF_EMA_PERIOD
FEATURE_KEYS = ("stop_atr", "stop_pct", "planned_rr", "swing_high_atr", "swing_low_atr", "horizon_key", "direction",
                "atr_pctile_250", "vol_ratio_20", "rsi_14", "adx_14", "bb_width_pctile_250", "htf_aligned",
                "gap_p90_pct", "gap_fragile", "dow", "regime2_state", "rs_pctile", "sector_pctile", "rs_combined")


def _number(value):
    try:
        value = float(value)
        return None if not math.isfinite(value) else round(value, 6)
    except (TypeError, ValueError):
        return None


def _pctile(series):
    series = series.iloc[-250:].dropna()
    return _number((series <= series.iloc[-1]).mean() * 100) if len(series) >= 60 else None


def entry_context(df, *, direction: str, horizon_key: str, stop: float, target: float, asof=None) -> dict:
    """Return only values knowable from ``df``'s final entry bar or before."""
    out = {key: None for key in FEATURE_KEYS}
    out.update(direction=direction, horizon_key=horizon_key)
    if df is None or len(df) < 20:
        return out
    close = float(df["Close"].iloc[-1]); risk = abs(close - stop); reward = abs(target - close)
    atr_series = atr(df, 14); atr_value = _number(atr_series.iloc[-1])
    out.update(stop_pct=_number(risk / close * 100) if close else None,
               planned_rr=_number(reward / risk) if risk else None,
               stop_atr=_number(risk / atr_value) if atr_value else None,
               atr_pctile_250=_pctile(atr_series), rsi_14=_number(rsi(df["Close"], 14).iloc[-1]),
               adx_14=_number(adx(df, 14).iloc[-1]), dow=int(df.index[-1].dayofweek))
    volume_mean = df["Volume"].rolling(20).mean().iloc[-1]
    out["vol_ratio_20"] = _number(df["Volume"].iloc[-1] / volume_mean) if volume_mean else None
    period = HTF_EMA_PERIOD.get(horizon_key)
    if period and len(df) >= period + 10:
        base = _number(ema(df["Close"], period).iloc[-1])
        out["htf_aligned"] = (close >= base) if direction == "bullish" else (close <= base)
    gaps = gap_stats(df)
    out["gap_p90_pct"] = _number(gaps.get("p90_gap_pct"))
    out["gap_fragile"] = (not stop_beyond_gap_noise(out["stop_pct"], out["gap_p90_pct"])) if out["stop_pct"] is not None and out["gap_p90_pct"] is not None else None
    for key in ("regime2_state", "rs_pctile", "sector_pctile", "rs_combined"):
        out[key] = _number(asof.get(key)) if key != "regime2_state" and asof else (asof.get(key) if asof else None)
    return out
