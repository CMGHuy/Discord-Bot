"""Transparent 0-100 plan-quality score (spec §6). Pure functions only --
no I/O, no config reads, no ML. Component weights may be re-weighted ONLY
on TRAIN evidence (Tasks 52-53); the breakdown is rendered verbatim in
embeds, so every point a plan gets is explainable in one line."""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

_ALIGNED, _NEUTRAL, _OPPOSED = 15, 8, 0

# scanning.regime.get_market_regime().trend is binary ("bullish"|"bearish" --
# no "neutral" state exists); None (feed unavailable/off) is the only
# neutral case here.


def component_regime(direction: str, regime: str | None) -> int:
    if regime not in ("bullish", "bearish"):
        return _NEUTRAL
    return _ALIGNED if regime == direction else _OPPOSED


def component_htf(direction: str, htf_bias: str | None) -> int:
    if htf_bias not in ("bullish", "bearish"):
        return _NEUTRAL
    return _ALIGNED if htf_bias == direction else _OPPOSED


def component_confluence(count: int) -> int:
    if count >= 4:
        return 20
    return {0: 0, 1: 7, 2: 12, 3: 16}[max(0, int(count))]


def component_volume(volume_ratio: float | None) -> int:
    if volume_ratio is None or not math.isfinite(volume_ratio):
        return 0
    if volume_ratio >= 2.0:
        return 10
    if volume_ratio >= 1.2:
        return 8
    if volume_ratio >= 0.8:
        return 4
    return 0


def atr_percentile(df: pd.DataFrame, period: int = 14,
                   window: int = 252) -> float | None:
    """Rank of the current normalized ATR (ATR14/Close) within its trailing
    `window` bars, 0..1. None when there isn't at least window/2 of usable
    history (early frames shouldn't pretend to know their vol regime)."""
    from swingbot.core.indicators import atr
    if len(df) < period + window // 2:
        return None
    norm = (atr(df, period) / df["Close"]).dropna()
    if len(norm) < window // 2:
        return None
    tail = norm.iloc[-window:]
    current = float(tail.iloc[-1])
    return float((tail <= current).mean())


def component_atr_percentile(pct: float | None) -> int:
    if pct is None:
        return 5            # unknown vol regime: middle score, never crash
    if pct >= 0.9:
        return 0            # top-decile volatility: statistically hostile
    if pct >= 0.7:
        return 5
    return 10


def component_distance(trigger_distance_pct: float) -> int:
    if trigger_distance_pct <= 0.5:
        return 10
    if trigger_distance_pct <= 1.5:
        return 6
    if trigger_distance_pct <= 3.0:
        return 3
    return 0


def component_badge(badge_status: str) -> int:
    return 20 if badge_status == "VALIDATED" else 0


def _tier(score: int) -> str:
    if score >= 75:
        return "A"
    if score >= 50:
        return "B"
    return "C"


@dataclass
class QualityResult:
    score: int
    tier: str
    breakdown: list   # [(component_name, points)] -- rendered verbatim in embeds


def score_plan(*, direction, regime, htf_bias, confluence_count, volume_ratio,
               atr_pct, trigger_distance_pct, badge_status) -> QualityResult:
    breakdown = [
        ("regime", component_regime(direction, regime)),
        ("htf", component_htf(direction, htf_bias)),
        ("confluence", component_confluence(confluence_count)),
        ("volume", component_volume(volume_ratio)),
        ("atr_percentile", component_atr_percentile(atr_pct)),
        ("trigger_distance", component_distance(trigger_distance_pct)),
        ("badge", component_badge(badge_status)),
    ]
    score = max(0, min(100, sum(pts for _, pts in breakdown)))
    return QualityResult(score=score, tier=_tier(score), breakdown=breakdown)
