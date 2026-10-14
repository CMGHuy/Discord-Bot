"""v146 I1: ConfidenceResult carries the integer each scored factor added.

Unified path (V146-1) and legacy path (V146-2, appended below). The
breakdown text is never parsed here: every expected integer comes from the
scorer's own rule table, so a test fails if `points` and the scorer disagree.
"""
from __future__ import annotations

from swingbot import config
from swingbot.core.market.levels import Scenario
from swingbot.core.scanning import confidence
from swingbot.core.scanning.confidence import ConfidenceResult, score_confidence
from swingbot.core.scanning.factors import FactorResult


def _scenario(**over) -> Scenario:
    base = dict(
        direction="bullish", entry=100.0, market_price=100.0, stop_loss=98.0,
        stop_sources=["EMA", "VWAP"], stop_distance_pct=2.0, tight_stop=False,
        atr_floor_pct=1.5, take_profit=106.0, target_distance_pct=6.0,
        target_sources=["EMA", "VWAP", "Fibonacci"], target2_price=None,
        target2_distance_pct=None, target2_sources=None,
    )
    base.update(over)
    return Scenario(**base)


# --- unified path (V146-1) --------------------------------------------

def test_confidence_result_points_and_unevaluated_default_empty_and_unshared():
    first = ConfidenceResult(level=3, label="Medium", score=50)
    assert first.points == {} and first.unevaluated == []
    first.points["x"] = 1
    first.unevaluated.append("x")
    second = ConfidenceResult(level=3, label="Medium", score=50)
    assert second.points == {} and second.unevaluated == []


def test_unified_points_are_each_factor_results_integer(monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)

    def f_trend(ctx):
        return FactorResult("Trend", 12, "trend agrees (+12)")

    def f_absent(ctx):
        return None

    def f_gap(ctx):
        return FactorResult("Gap penalty", -10, "⚠️ fragile gap risk (-10)")

    monkeypatch.setattr(confidence, "FACTORS", [f_trend, f_absent, f_gap])
    result = score_confidence(_scenario(), regime_trend="bullish", df=None)
    assert result.points == {"Trend": 12, "Gap penalty": -10}
    assert result.unevaluated == []
    assert "Confirming methods" in result.breakdown
    assert "Confirming methods" not in result.points


def test_unified_points_sum_to_the_unclamped_score(monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)

    def f_a(ctx):
        return FactorResult("A", 30, "a (+30)")

    def f_b(ctx):
        return FactorResult("B", 25, "b (+25)")

    monkeypatch.setattr(confidence, "FACTORS", [f_a, f_b])
    result = score_confidence(_scenario(), regime_trend="bullish", df=None)
    assert sum(result.points.values()) == result.score == 55


def test_unified_real_registry_records_its_zero_and_penalty_factors(monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)
    result = score_confidence(
        _scenario(), regime_trend="bullish", df=None, gap_fragile=True,
        macro_verdict={"status": "aligned", "reason": "agrees", "trend": "bullish"})
    assert result.points == {"Gap penalty": -10, "Macro trend (6m)": 0}
