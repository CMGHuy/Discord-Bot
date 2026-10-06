"""No-lookahead entry-context snapshots for v93 trade records."""
from __future__ import annotations

import math

from swingbot import config
from swingbot.core.edge.gates import gap_stats, stop_beyond_gap_noise
from swingbot.core.market.indicators import adx, atr, ema, rsi
from swingbot.core.market.location import location_features
from swingbot.core.market.structure import structure_features
from swingbot.core.planning.builders import CLAMP_HEADROOM_PCT
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from swingbot.core.scanning.regime import _HTF_EMA_PERIOD

HTF_EMA_PERIOD = _HTF_EMA_PERIOD
FEATURE_KEYS = ("stop_atr", "stop_pct", "planned_rr", "swing_high_atr", "swing_low_atr", "horizon_key", "direction",
                "atr_pctile_250", "vol_ratio_20", "rsi_14", "adx_14", "bb_width_pctile_250", "htf_aligned",
                "gap_p90_pct", "gap_fragile", "dow", "regime2_state", "rs_pctile", "sector_pctile", "rs_combined",
                # v121: causal structure / volume-in-context (market/structure.py); swing_*_atr above are now filled
                "structure_state", "structure_aligned", "last_pivot_held", "hh_failed", "vol_trend_10_50",
                "range_trend_10_50", "progress_atr_10", "absorption_bar", "absorption_count_10",
                "pullback_vol_ratio", "pullback_depth_frac", "pullback_bars_ratio", "impulse_atr_per_bar",
                "impulse_range_decay",
                # v125: plan provenance (plan_provenance) and location / leg / zone (market/location.py)
                "target_capped", "stop_clamped", "zone_dist_atr", "room_atr", "range_pos", "leg_phase",
                "zone_state", "zone_touches", "zone_departure_atr")
PROVENANCE_KEYS = ("target_capped", "stop_clamped")
CAP_TOLERANCE = 1e-6       # frozen: relative price tolerance for the synthetic-target identity
CLAMP_TOLERANCE = 1e-6     # frozen: absolute tolerance, in percentage points, for the clamp identity


def _number(value):
    try:
        value = float(value)
        return None if not math.isfinite(value) else round(value, 6)
    except (TypeError, ValueError):
        return None


def _pctile(series):
    series = series.iloc[-250:].dropna()
    return _number((series <= series.iloc[-1]).mean() * 100) if len(series) >= 60 else None


def _finite(*values) -> bool:
    try:
        return all(value is not None and math.isfinite(float(value)) for value in values)
    except (TypeError, ValueError):
        return False


def _target_capped(entry: float, stop: float, tp1: float, max_rr) -> bool | None:
    """tp1 sits exactly where select_structural_target puts its SYNTHETIC cap price."""
    if not _finite(max_rr):
        return None
    synthetic = entry + (entry - stop) * float(max_rr)
    return abs(tp1 - synthetic) <= CAP_TOLERANCE * max(1.0, abs(entry))


def _stop_clamped(entry: float, stop: float) -> bool:
    """stop sits exactly where _clamp_stop_to_hard_cap moves a wide confluence stop."""
    landing = HARD_MAX_PLANNED_LOSS_PCT - CLAMP_HEADROOM_PCT
    return bool(config.CLAMP_STOP_TO_HARD_CAP) and abs(planned_loss_pct(entry, stop) - landing) <= CLAMP_TOLERANCE


def plan_provenance(entry, stop, tp1, max_rr) -> dict:
    """Whether a plan's tp1 is the synthetic max_rr cap and its stop the v115
    clamp, derived from the PLANNED entry. Both None without a usable entry,
    stop and tp1 -- never guessed. Pure; reads no bars."""
    if not _finite(entry, stop, tp1) or float(entry) <= 0 or float(entry) == float(stop):
        return dict.fromkeys(PROVENANCE_KEYS)
    entry, stop, tp1 = float(entry), float(stop), float(tp1)
    return {"target_capped": _target_capped(entry, stop, tp1, max_rr),
            "stop_clamped": _stop_clamped(entry, stop)}


def entry_context(df, *, direction: str, horizon_key: str, stop: float, target: float, asof=None,
                  entry=None) -> dict:
    """Return only values knowable from ``df``'s final entry bar or before.

    ``entry`` is the PLANNED entry (trigger), never a slipped fill; without it
    the two plan-provenance flags are None."""
    out = {key: None for key in FEATURE_KEYS}
    out.update(direction=direction, horizon_key=horizon_key)
    out.update(plan_provenance(entry, stop, target, config.MAX_RISK_REWARD_RATIO))   # v125; reads no bars
    if df is None or len(df) < 20:
        return out
    close = float(df["Close"].iloc[-1]); risk = abs(close - stop); reward = abs(target - close)
    atr_series = atr(df, 14); atr_value = _number(atr_series.iloc[-1])
    out.update(stop_pct=_number(risk / close * 100) if close else None,
               planned_rr=_number(reward / risk) if risk else None,
               stop_atr=_number(risk / atr_value) if atr_value else None,
               atr_pctile_250=_pctile(atr_series), rsi_14=_number(rsi(df["Close"], 14).iloc[-1]),
               adx_14=_number(adx(df, 14).iloc[-1]), dow=int(df.index[-1].dayofweek))
    out.update(structure_features(df, direction))   # v121; all None below 60 bars
    out.update(location_features(df, direction, horizon_key))   # v125; all None below 60 bars
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
