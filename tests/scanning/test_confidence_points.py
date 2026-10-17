"""v146 I1: ConfidenceResult carries the integer each scored factor added.

Unified path (V146-1) and legacy path (V146-2, appended below). The
breakdown text is never parsed here: every expected integer comes from the
scorer's own rule table, so a test fails if `points` and the scorer disagree.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from swingbot import config
from swingbot.core.market.levels import Scenario
from swingbot.core.scanning import confidence
from swingbot.core.scanning.confidence import LEGACY_POINT_KEYS, ConfidenceResult, score_confidence
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


# --- legacy path (V146-2) ---------------------------------------------
#
# Every indicator the legacy scorer reads is stubbed, so each case drives
# exactly one branch and the expected integer is the rule table's, not a
# re-reading of the line. `_DF` is any non-None object: with every
# indicator stubbed, the scorer only ever tests `df is not None`.

_DF = object()

# The "evaluated, scores zero" reading of every indicator; a case overrides
# the one it is about.
_BASE_READINGS = {
    "adx_trend_strength": {"adx": 18.0, "strong": False, "trending": False, "label": "ranging"},
    "macd_momentum_aligned": {"strength": "opposed", "macd_val": -0.1, "histogram": -0.05},
    "rsi_trend_aligned": {"rsi_val": 40.0, "strength": "opposed"},
    "squeeze_breakout_confirmation": {"confirmed": False, "is_squeeze": False, "width_pct": 3.0},
    "detect_confirming_pattern": {"confirmed": False, "bars_ago": None, "pattern": None},
}

_NON_FACTOR_KEYS = {
    "Strategies confirmed (base level)", "Quality score", "Track record (expectancy)",
    "Level adjustment", "Confirming methods",
}


def _case(label, key, points, unevaluated=False, *, readings=None, scenario=None,
          regime="bullish", df=_DF):
    return SimpleNamespace(label=label, key=key, points=points, unevaluated=unevaluated,
                           readings=readings or {}, scenario=scenario or {},
                           regime=regime, df=df)


_CASES = [
    _case("distance 1.2x", "Target distance quality", 12, scenario={"target_distance_pct": 6.0}),
    _case("distance capped", "Target distance quality", 20, scenario={"target_distance_pct": 15.0}),
    _case("stop two methods", "Stop level confluence", 10, scenario={"stop_sources": ["EMA", "VWAP"]}),
    _case("stop capped", "Stop level confluence", 15,
          scenario={"stop_sources": ["EMA", "VWAP", "Fibonacci", "Donchian"]}),
    _case("regime aligned", "Market regime alignment", 15, regime="bullish"),
    _case("regime counter", "Market regime alignment", 0, regime="bearish"),
    _case("regime unavailable", "Market regime alignment", 7, True, regime=None),
    _case("adx strong", "ADX trend strength", 15, readings={"adx_trend_strength": {
        "adx": 31.0, "strong": True, "trending": True, "label": "strong trend"}}),
    _case("adx trending", "ADX trend strength", 8, readings={"adx_trend_strength": {
        "adx": 22.0, "strong": False, "trending": True, "label": "emerging trend"}}),
    _case("adx ranging", "ADX trend strength", 0),
    _case("adx short history", "ADX trend strength", 7, True, readings={"adx_trend_strength": {
        "adx": None, "strong": False, "trending": False, "label": "n/a"}}),
    _case("adx no df", "ADX trend strength", 7, True, df=None),
    _case("macd strong", "MACD momentum", 15, readings={"macd_momentum_aligned": {
        "strength": "strong", "macd_val": 0.5, "histogram": 0.1}}),
    _case("macd moderate", "MACD momentum", 10, readings={"macd_momentum_aligned": {
        "strength": "moderate", "macd_val": 0.3, "histogram": 0.05}}),
    _case("macd weak", "MACD momentum", 5, readings={"macd_momentum_aligned": {
        "strength": "weak", "macd_val": 0.1, "histogram": -0.01}}),
    _case("macd opposed", "MACD momentum", 0),
    _case("macd no df", "MACD momentum", 7, True, df=None),
    _case("rsi strong", "RSI trend alignment", 10, readings={"rsi_trend_aligned": {
        "rsi_val": 62.0, "strength": "strong"}}),
    _case("rsi moderate", "RSI trend alignment", 6, readings={"rsi_trend_aligned": {
        "rsi_val": 56.0, "strength": "moderate"}}),
    _case("rsi weak", "RSI trend alignment", 3, readings={"rsi_trend_aligned": {
        "rsi_val": 51.0, "strength": "weak"}}),
    _case("rsi opposed", "RSI trend alignment", 0),
    _case("rsi short history", "RSI trend alignment", 5, True, readings={"rsi_trend_aligned": {
        "rsi_val": None, "strength": None}}),
    _case("rsi no df", "RSI trend alignment", 5, True, df=None),
    _case("squeeze fired", "TTM Squeeze + volume breakout", 10, readings={
        "squeeze_breakout_confirmation": {"confirmed": True, "is_squeeze": False, "width_pct": 4.0}}),
    _case("squeeze on", "TTM Squeeze + volume breakout", 5, readings={
        "squeeze_breakout_confirmation": {"confirmed": False, "is_squeeze": True, "width_pct": 2.0}}),
    _case("squeeze none", "TTM Squeeze + volume breakout", 0),
    _case("squeeze no df", "TTM Squeeze + volume breakout", 0, True, df=None),
    _case("candle today", "Candlestick pattern", 10, readings={"detect_confirming_pattern": {
        "confirmed": True, "bars_ago": 0, "pattern": "Bullish Engulfing"}}),
    _case("candle yesterday", "Candlestick pattern", 6, readings={"detect_confirming_pattern": {
        "confirmed": True, "bars_ago": 1, "pattern": "Hammer"}}),
    _case("candle none", "Candlestick pattern", 0),
    _case("candle no df", "Candlestick pattern", 0, True, df=None),
    _case("tight stop", "Tight stop penalty", -11, scenario={
        "tight_stop": True, "atr_floor_pct": 4.0, "stop_distance_pct": 1.0}),
    _case("tight stop capped", "Tight stop penalty", -15, scenario={
        "tight_stop": True, "atr_floor_pct": 2.0, "stop_distance_pct": 0.0}),
]


def _stub(value):
    return lambda *args, **kwargs: value


def _run(case) -> ConfidenceResult:
    readings = {**_BASE_READINGS, **case.readings}
    stubs = {name: _stub(value) for name, value in readings.items()}
    with mock.patch.multiple(confidence, **stubs), \
            mock.patch.object(config, "MIN_REWARD_PCT", 5.0), \
            mock.patch.object(config, "UNIFIED_CONFIDENCE", False):
        return score_confidence(_scenario(**case.scenario), regime_trend=case.regime, df=case.df)


def scenario_matrix() -> list[tuple[str, ConfidenceResult]]:
    """One legacy ConfidenceResult per rule-table case. V146-3's parser test
    imports this so the backfill parser is proven against every line form
    the legacy scorer can emit -- fallbacks and the negative penalty included."""
    return [(case.label, _run(case)) for case in _CASES]


@pytest.mark.parametrize("case", _CASES, ids=[c.label for c in _CASES])
def test_legacy_points_equal_the_rule_table(case):
    result = _run(case)
    assert result.points[case.key] == case.points
    assert (case.key in result.unevaluated) is case.unevaluated


@pytest.mark.parametrize("case", _CASES, ids=[c.label for c in _CASES])
def test_legacy_points_cover_exactly_the_scored_breakdown_lines(case):
    result = _run(case)
    assert set(result.points) == set(result.breakdown) - _NON_FACTOR_KEYS
    assert set(result.points) <= set(LEGACY_POINT_KEYS)
    assert set(result.unevaluated) <= set(result.points)


@pytest.mark.parametrize("case", _CASES, ids=[c.label for c in _CASES])
def test_legacy_points_reconcile_with_the_quality_score(case):
    result = _run(case)
    quality = int(result.breakdown["Quality score"].split("/", 1)[0])
    positive = sum(v for k, v in result.points.items() if k != "Tight stop penalty")
    penalty = result.points.get("Tight stop penalty", 0)
    assert quality == max(0, min(100, positive) + penalty)


def test_every_legacy_point_key_is_exercised():
    assert {case.key for case in _CASES} == set(LEGACY_POINT_KEYS)


def test_no_tight_stop_line_means_no_penalty_key():
    result = _run(_case("plain", "Target distance quality", 12))
    assert "Tight stop penalty" not in result.points


def test_no_price_history_marks_every_df_factor_unevaluated_in_scoring_order():
    result = _run(_case("no df", "ADX trend strength", 7, True, df=None))
    assert result.unevaluated == [
        "ADX trend strength", "MACD momentum", "RSI trend alignment",
        "TTM Squeeze + volume breakout", "Candlestick pattern",
    ]


def test_regime_and_df_missing_together_lists_regime_first():
    result = _run(_case("bare", "Market regime alignment", 7, True, regime=None, df=None))
    assert result.unevaluated[0] == "Market regime alignment"
    assert len(result.unevaluated) == 6


def test_scenario_matrix_returns_one_result_per_case():
    matrix = scenario_matrix()
    assert [label for label, _ in matrix] == [case.label for case in _CASES]
    assert all(isinstance(result, ConfidenceResult) for _, result in matrix)
