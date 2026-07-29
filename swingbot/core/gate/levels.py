"""Swing S/R extraction + round numbers (G48) + level_map check (G49)."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult
from swingbot.core.indicators import atr


@dataclass(frozen=True)
class SwingLevel:
    price: float
    kind: str          # "support" | "resistance"
    touches: int
    last_touch: str    # ISO date


def _safe_atr(df: pd.DataFrame, fallback_price: float) -> float:
    val = float(atr(df).iloc[-1])
    return val if val == val and val > 0 else fallback_price * 0.02


def swing_levels(df_daily: pd.DataFrame, lookback: int = 250,
                 pivot_span: int = 5) -> list[SwingLevel]:
    """Pivots = UNIQUE local extrema over +/-pivot_span bars (ties are not
    pivots — a flat series yields nothing), clustered within 0.5*ATR,
    touch-counted, sorted by touches desc."""
    df = df_daily.iloc[-lookback:]
    if len(df) < 2 * pivot_span + 1:
        return []
    highs, lows, idx = df["High"].values, df["Low"].values, df.index
    atr_val = _safe_atr(df, float(df["Close"].iloc[-1]))
    raw = []   # (price, kind, date)
    for i in range(pivot_span, len(df) - pivot_span):
        hi_win = highs[i - pivot_span:i + pivot_span + 1]
        lo_win = lows[i - pivot_span:i + pivot_span + 1]
        if highs[i] == hi_win.max() and (hi_win == highs[i]).sum() == 1:
            raw.append((float(highs[i]), "resistance", str(idx[i].date())))
        if lows[i] == lo_win.min() and (lo_win == lows[i]).sum() == 1:
            raw.append((float(lows[i]), "support", str(idx[i].date())))
    levels: list[SwingLevel] = []
    for kind in ("support", "resistance"):
        bucket: list[tuple[float, str]] = []
        for price, _, date in sorted((r for r in raw if r[1] == kind),
                                     key=lambda r: r[0]):
            if bucket and price - bucket[0][0] > 0.5 * atr_val:
                levels.append(_close_bucket(bucket, kind))
                bucket = []
            bucket.append((price, date))
        if bucket:
            levels.append(_close_bucket(bucket, kind))
    return sorted(levels, key=lambda l: l.touches, reverse=True)


def _close_bucket(bucket: list[tuple[float, str]], kind: str) -> SwingLevel:
    prices = [p for p, _ in bucket]
    return SwingLevel(round(sum(prices) / len(prices), 4), kind,
                      len(bucket), max(d for _, d in bucket))


_STEPS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0)


def _step_for(price: float) -> float:
    target = price / 50.0
    for step in _STEPS:
        if step >= target:
            return step
    return _STEPS[-1]


def round_levels(price: float) -> list[float]:
    """The minor psychological grid near price (5 multiples of the
    magnitude-appropriate step) plus the majors around it."""
    step = _step_for(price)
    center = round(price / step) * step
    grid = {round(center + k * step, 2) for k in range(-2, 3)}
    grid |= set(major_levels(price))
    return sorted(p for p in grid if p > 0)


def major_levels(price: float) -> list[float]:
    """Only these count as 'walls' — a 10x-step grid (e.g. 150/200 for a
    $187 stock). The minor grid is context, not obstruction."""
    major = _step_for(price) * 10
    center = round(price / major) * major
    return sorted({round(center + k * major, 2) for k in (-1, 0, 1)} - {0.0})


def nearest_round(price: float, *, atr: float) -> tuple[float, float]:
    level = min(round_levels(price), key=lambda l: abs(l - price))
    dist = abs(level - price) / atr if atr > 0 else float("inf")
    return level, round(dist, 3)


def check_level_map(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["level_map"]
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    atr_val = _safe_atr(df_daily, entry)
    swings = swing_levels(df_daily)
    all_prices = sorted({l.price for l in swings} | set(round_levels(entry)))
    below = [p for p in all_prices if p < entry][-3:]
    above = [p for p in all_prices if p > entry][:3]
    bullish = plan.direction == "bullish"
    lo, hi = (entry, plan.tp1) if bullish else (plan.tp1, entry)
    opposing = "resistance" if bullish else "support"
    walls = [l.price for l in swings if l.kind == opposing and lo < l.price < hi]
    walls += [m for m in major_levels(entry) if lo < m < hi]
    nearest = min(walls, key=lambda w: abs(w - entry)) if walls else None
    dist_atr = round(abs(nearest - entry) / atr_val, 2) if nearest is not None else None
    if dist_atr is not None and dist_atr < spec.threshold("wall_atr_fail"):
        status = "fail"
        detail = f"{opposing} wall {nearest:.2f} only {dist_atr} ATR into the path to TP1"
    elif dist_atr is not None and dist_atr < spec.threshold("wall_atr_warn"):
        status = "warn"
        detail = f"{opposing} {nearest:.2f} sits {dist_atr} ATR into the path to TP1"
    else:
        status, detail = "pass", "no significant wall before TP1"
    return CheckResult("level_map", "context", status, 8.0, detail,
                       {"below": below, "above": above, "walls": sorted(walls)[:5],
                        "nearest_wall": nearest, "dist_atr": dist_atr,
                        "atr": round(atr_val, 4)})


register(check_id="level_map", section="context", weight=8.0, func=check_level_map,
         thresholds={
             "wall_atr_fail": ThresholdSpec(
                 "wall_atr_fail", 1.0, 0.25, 3.0, 0.25,
                 "lower to tolerate closer walls before TP1",
                 presets={"strict": 1.5, "balanced": 1.0, "relaxed": 0.5}),
             "wall_atr_warn": ThresholdSpec(
                 "wall_atr_warn", 2.0, 0.5, 4.0, 0.25,
                 "lower to warn about fewer walls",
                 presets={"strict": 2.5, "balanced": 2.0, "relaxed": 1.0}),
         })
