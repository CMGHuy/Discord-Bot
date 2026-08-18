from types import SimpleNamespace

import pytest
from swingbot.core.scanning.factors import (
    FactorResult, FactorContext, run_factors,
)


def _ctx(**kw):
    """Minimal context; every field defaults to None so a factor under test
    only has to supply what it reads."""
    return FactorContext(**kw)


def test_factor_result_carries_points_and_line():
    r = FactorResult(name="demo", points=7, line="demo scored (+7)")
    assert (r.name, r.points, r.line) == ("demo", 7, "demo scored (+7)")


def test_run_factors_sums_points_and_collects_breakdown():
    def f_a(ctx):
        return FactorResult("a", 5, "a (+5)")

    def f_b(ctx):
        return FactorResult("b", 3, "b (+3)")

    total, breakdown = run_factors([f_a, f_b], _ctx())
    assert total == 8
    assert breakdown == {"a": "a (+5)", "b": "b (+3)"}


def test_run_factors_skips_factors_returning_none():
    """A factor whose input is absent returns None and must not appear in the
    breakdown at all -- an absent reading must never render as a real one that
    happened to score zero."""
    def f_present(ctx):
        return FactorResult("present", 4, "present (+4)")

    def f_absent(ctx):
        return None

    total, breakdown = run_factors([f_present, f_absent], _ctx())
    assert total == 4
    assert "absent" not in breakdown


def test_run_factors_propagates_negative_points():
    def f_penalty(ctx):
        return FactorResult("penalty", -10, "penalty (-10)")

    total, _ = run_factors([f_penalty], _ctx())
    assert total == -10


# --- Task 3: confidence.py factors -----------------------------------

from swingbot.core.scanning.factors import (  # noqa: E402
    factor_target_distance, factor_stop_confluence, factor_regime,
    factor_adx, factor_macd, factor_rsi, factor_squeeze, factor_candlestick,
    factor_tight_stop,
)


def test_target_distance_scales_with_multiples_of_minimum():
    """20 pts max, 10 pts per 1x of MIN_REWARD_PCT (default 5%)."""
    ctx = _ctx(scenario=SimpleNamespace(target_distance_pct=10.0))
    r = factor_target_distance(ctx)
    assert r.points == 20
    assert "10.0%" in r.line


def test_target_distance_caps_at_twenty():
    ctx = _ctx(scenario=SimpleNamespace(target_distance_pct=99.0))
    assert factor_target_distance(ctx).points == 20


def test_target_distance_absent_scenario_returns_none():
    assert factor_target_distance(_ctx()) is None


def test_stop_confluence_five_points_per_method_capped_at_fifteen():
    assert factor_stop_confluence(_ctx(stop_count=1)).points == 5
    assert factor_stop_confluence(_ctx(stop_count=3)).points == 15
    assert factor_stop_confluence(_ctx(stop_count=9)).points == 15


def test_stop_confluence_names_the_methods():
    r = factor_stop_confluence(_ctx(stop_count=2, stop_families=["EMA", "VWAP"]))
    assert "EMA, VWAP" in r.line


def _scenario(direction="bullish", target_sources=None):
    return SimpleNamespace(direction=direction,
                           target_sources=target_sources if target_sources is not None else [])


def test_regime_aligned_scores_fifteen():
    ctx = _ctx(scenario=_scenario("bullish"), regime_trend="bullish")
    r = factor_regime(ctx)
    assert r.points == 15
    assert "aligned" in r.line


def test_regime_counter_scores_zero():
    ctx = _ctx(scenario=_scenario("bullish"), regime_trend="bearish")
    r = factor_regime(ctx)
    assert r.points == 0
    assert "counter" in r.line


def test_regime_absent_returns_none():
    """No regime reading and no scenario are both genuinely-absent inputs,
    not a 'neutral' score to fabricate."""
    assert factor_regime(_ctx(scenario=_scenario())) is None
    assert factor_regime(_ctx(regime_trend="bullish")) is None


def test_adx_strong_scores_fifteen(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.adx_trend_strength",
        lambda df: {"adx": 30.0, "trending": True, "strong": True, "label": "strong trend"})
    r = factor_adx(_ctx(df=object()))
    assert r.points == 15
    assert "30.0" in r.line


def test_adx_trending_not_strong_scores_eight(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.adx_trend_strength",
        lambda df: {"adx": 22.0, "trending": True, "strong": False, "label": "weak trend emerging"})
    assert factor_adx(_ctx(df=object())).points == 8


def test_adx_ranging_scores_zero(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.adx_trend_strength",
        lambda df: {"adx": 12.0, "trending": False, "strong": False, "label": "ranging / no clear trend"})
    assert factor_adx(_ctx(df=object())).points == 0


def test_adx_no_df_returns_none():
    assert factor_adx(_ctx()) is None


def test_adx_insufficient_history_returns_none(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.adx_trend_strength",
        lambda df: {"adx": None, "trending": False, "strong": False, "label": "unavailable"})
    assert factor_adx(_ctx(df=object())) is None


def test_macd_strong_scores_fifteen(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.macd_momentum_aligned",
        lambda df, direction: {"aligned": True, "strength": "strong",
                               "macd_val": 1.234, "signal_val": 0.5, "histogram": 0.6})
    r = factor_macd(_ctx(df=object(), scenario=_scenario("bullish")))
    assert r.points == 15
    assert "1.2340" in r.line


def test_macd_opposing_scores_zero(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.macd_momentum_aligned",
        lambda df, direction: {"aligned": False, "strength": "none",
                               "macd_val": -0.1, "signal_val": 0.2, "histogram": -0.05})
    r = factor_macd(_ctx(df=object(), scenario=_scenario("bullish")))
    assert r.points == 0
    assert "opposes" in r.line


def test_macd_no_df_or_scenario_returns_none():
    assert factor_macd(_ctx(scenario=_scenario())) is None
    assert factor_macd(_ctx(df=object())) is None


def test_macd_insufficient_history_returns_none(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.macd_momentum_aligned",
        lambda df, direction: {"aligned": False, "strength": "none",
                               "macd_val": None, "signal_val": None, "histogram": None})
    assert factor_macd(_ctx(df=object(), scenario=_scenario("bullish"))) is None


def test_rsi_strong_scores_ten(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.rsi_trend_aligned",
        lambda df, direction: {"aligned": True, "strength": "strong", "rsi_val": 62.0})
    r = factor_rsi(_ctx(df=object(), scenario=_scenario("bullish")))
    assert r.points == 10
    assert "62.0" in r.line


def test_rsi_opposing_scores_zero(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.rsi_trend_aligned",
        lambda df, direction: {"aligned": False, "strength": "none", "rsi_val": 58.0})
    r = factor_rsi(_ctx(df=object(), scenario=_scenario("bullish")))
    assert r.points == 0
    assert "opposes" in r.line


def test_rsi_insufficient_history_returns_none(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.rsi_trend_aligned",
        lambda df, direction: {"aligned": False, "strength": "none", "rsi_val": None})
    assert factor_rsi(_ctx(df=object(), scenario=_scenario("bullish"))) is None


def test_rsi_no_df_or_scenario_returns_none():
    assert factor_rsi(_ctx(scenario=_scenario())) is None
    assert factor_rsi(_ctx(df=object())) is None


def test_squeeze_confirmed_scores_ten_and_appends_source(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.squeeze_breakout_confirmation",
        lambda df, direction: {"confirmed": True, "is_squeeze": False,
                               "squeeze_off": True, "width_pct": 3.2,
                               "volume_confirmed": True, "breakout_confirmed": True})
    scenario = _scenario("bullish")
    r = factor_squeeze(_ctx(df=object(), scenario=scenario))
    assert r.points == 10
    assert "Bollinger Squeeze Breakout" in scenario.target_sources


def test_squeeze_on_but_not_confirmed_scores_five(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.squeeze_breakout_confirmation",
        lambda df, direction: {"confirmed": False, "is_squeeze": True,
                               "squeeze_off": False, "width_pct": 1.1,
                               "volume_confirmed": False, "breakout_confirmed": False})
    assert factor_squeeze(_ctx(df=object(), scenario=_scenario())).points == 5


def test_squeeze_none_scores_zero(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.squeeze_breakout_confirmation",
        lambda df, direction: {"confirmed": False, "is_squeeze": False,
                               "squeeze_off": False, "width_pct": 8.0,
                               "volume_confirmed": False, "breakout_confirmed": False})
    assert factor_squeeze(_ctx(df=object(), scenario=_scenario())).points == 0


def test_squeeze_no_df_or_scenario_returns_none():
    assert factor_squeeze(_ctx(scenario=_scenario())) is None
    assert factor_squeeze(_ctx(df=object())) is None


def test_candlestick_today_scores_ten_and_appends_source(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.detect_confirming_pattern",
        lambda df, direction: {"confirmed": True, "pattern": "Engulfing", "bars_ago": 0})
    scenario = _scenario("bullish")
    r = factor_candlestick(_ctx(df=object(), scenario=scenario))
    assert r.points == 10
    assert "Candlestick: Engulfing" in scenario.target_sources


def test_candlestick_yesterday_scores_six(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.detect_confirming_pattern",
        lambda df, direction: {"confirmed": True, "pattern": "Morning Star", "bars_ago": 1})
    assert factor_candlestick(_ctx(df=object(), scenario=_scenario())).points == 6


def test_candlestick_no_pattern_scores_zero(monkeypatch):
    monkeypatch.setattr(
        "swingbot.core.scanning.factors.detect_confirming_pattern",
        lambda df, direction: {"confirmed": False, "pattern": None, "bars_ago": None})
    assert factor_candlestick(_ctx(df=object(), scenario=_scenario())).points == 0


def test_candlestick_no_df_or_scenario_returns_none():
    assert factor_candlestick(_ctx(scenario=_scenario())) is None
    assert factor_candlestick(_ctx(df=object())) is None


def _tight_scenario(tight_stop=True, atr_floor_pct=2.0, stop_distance_pct=1.0):
    return SimpleNamespace(tight_stop=tight_stop, atr_floor_pct=atr_floor_pct,
                           stop_distance_pct=stop_distance_pct)


def test_tight_stop_penalizes_proportionally_to_shortfall():
    r = factor_tight_stop(_ctx(scenario=_tight_scenario(atr_floor_pct=2.0, stop_distance_pct=1.0)))
    assert r.points == -8   # shortfall 50% of 15 = 7.5 -> round to 8


def test_tight_stop_caps_penalty_at_fifteen():
    r = factor_tight_stop(_ctx(scenario=_tight_scenario(atr_floor_pct=10.0, stop_distance_pct=0.0)))
    assert r.points == -15


def test_tight_stop_absent_when_not_tight():
    assert factor_tight_stop(_ctx(scenario=_tight_scenario(tight_stop=False))) is None


def test_tight_stop_absent_when_no_atr_floor():
    assert factor_tight_stop(_ctx(scenario=_tight_scenario(atr_floor_pct=0.0))) is None


def test_tight_stop_absent_scenario_returns_none():
    assert factor_tight_stop(_ctx()) is None


# --- Task 4: quality.py components, including RS/MTF/breadth ----------

from swingbot.core.scanning.factors import (  # noqa: E402
    factor_rs, factor_breadth, factor_htf, factor_volume,
    factor_atr_percentile, factor_trigger_distance, factor_badge,
    factor_gap, factor_target_confluence_quality,
)


def test_rs_scores_zero_at_or_below_median():
    assert factor_rs(_ctx(rs_percentile=50.0)).points == 0
    assert factor_rs(_ctx(rs_percentile=10.0)).points == 0


def test_rs_scales_above_median_and_caps():
    assert factor_rs(_ctx(rs_percentile=75.0)).points == 5
    assert factor_rs(_ctx(rs_percentile=100.0)).points == 10


def test_rs_absent_returns_none_not_zero():
    """None means the RS benchmark fetch failed. It must be omitted from the
    breakdown, not rendered as a real reading of zero."""
    assert factor_rs(_ctx()) is None


def test_breadth_scores_above_forty_percent_and_caps_at_sixty():
    assert factor_breadth(_ctx(breadth=40.0)).points == 0
    assert factor_breadth(_ctx(breadth=60.0)).points == 5
    assert factor_breadth(_ctx(breadth=95.0)).points == 5


def test_breadth_absent_returns_none():
    assert factor_breadth(_ctx()) is None


def test_htf_aligned_scores_fifteen():
    ctx = _ctx(scenario=_scenario("bullish"), htf_bias="bullish")
    assert factor_htf(ctx).points == 15


def test_htf_counter_scores_zero():
    ctx = _ctx(scenario=_scenario("bullish"), htf_bias="bearish")
    r = factor_htf(ctx)
    assert r.points == 0


def test_htf_absent_returns_none():
    assert factor_htf(_ctx(scenario=_scenario())) is None
    assert factor_htf(_ctx(htf_bias="bullish")) is None
    assert factor_htf(_ctx(scenario=_scenario(), htf_bias="sideways")) is None


def test_volume_ratio_bands():
    assert factor_volume(_ctx(volume_ratio=2.5)).points == 10
    assert factor_volume(_ctx(volume_ratio=1.5)).points == 8
    assert factor_volume(_ctx(volume_ratio=1.0)).points == 4
    assert factor_volume(_ctx(volume_ratio=0.5)).points == 0


def test_volume_absent_returns_none():
    assert factor_volume(_ctx()) is None
    assert factor_volume(_ctx(volume_ratio=float("nan"))) is None


def test_atr_percentile_bands():
    assert factor_atr_percentile(_ctx(atr_pct=0.95)).points == 0
    assert factor_atr_percentile(_ctx(atr_pct=0.75)).points == 5
    assert factor_atr_percentile(_ctx(atr_pct=0.3)).points == 10


def test_atr_percentile_absent_returns_none():
    """Unknown vol regime is genuinely absent -- distinct from a KNOWN
    reading in the 0.7-0.9 band that also happens to score 5."""
    assert factor_atr_percentile(_ctx()) is None


def test_trigger_distance_bands():
    assert factor_trigger_distance(_ctx(trigger_distance_pct=0.3)).points == 10
    assert factor_trigger_distance(_ctx(trigger_distance_pct=1.0)).points == 6
    assert factor_trigger_distance(_ctx(trigger_distance_pct=2.0)).points == 3
    assert factor_trigger_distance(_ctx(trigger_distance_pct=5.0)).points == 0


def test_trigger_distance_absent_returns_none():
    assert factor_trigger_distance(_ctx()) is None


def test_badge_validated_scores_twenty():
    assert factor_badge(_ctx(badge_status="VALIDATED")).points == 20


def test_badge_other_status_scores_zero():
    assert factor_badge(_ctx(badge_status="WEAK")).points == 0


def test_badge_absent_returns_none():
    assert factor_badge(_ctx()) is None


def test_gap_penalty_only_when_fragile():
    r = factor_gap(_ctx(gap_fragile=True))
    assert r.points == -10


def test_gap_penalty_absent_when_not_fragile():
    assert factor_gap(_ctx(gap_fragile=False)) is None


def test_target_confluence_quality_bands():
    assert factor_target_confluence_quality(_ctx(target_count=0)).points == 0
    assert factor_target_confluence_quality(_ctx(target_count=1)).points == 7
    assert factor_target_confluence_quality(_ctx(target_count=2)).points == 12
    assert factor_target_confluence_quality(_ctx(target_count=3)).points == 16
    assert factor_target_confluence_quality(_ctx(target_count=4)).points == 20
    assert factor_target_confluence_quality(_ctx(target_count=9)).points == 20


def test_factors_registry_has_exactly_the_kept_factors():
    """Task 2/3/4 ported and registered 19 factors; Task 9's TRAIN
    measurement found none with real, positively-signed lift (see
    factors.py's own comment above FACTORS for the full breakdown), so only
    factor_gap -- inert today, never fires -- remains in the active
    registry. The other 18 stay defined and tested, just not registered.

    v33 Task 5 adds factor_macro_alignment to the registry too, but as a
    provisional, not-yet-TRAIN-supported entry (see the comment beside its
    registration) -- re-derived or possibly zeroed out by v33 Task 7."""
    from swingbot.core.scanning.factors import FACTORS, factor_gap, factor_macro_alignment
    assert FACTORS == [factor_gap, factor_macro_alignment]


# --- v33 Task 5: 6m macro-anchor alignment factor ---------------------

from swingbot.core.scanning.factors import factor_macro_alignment  # noqa: E402


def test_macro_alignment_scores_full_when_aligned():
    ctx = _ctx(macro_verdict={"status": "aligned", "reason": "bullish trend agrees",
                              "trend": "bullish"})
    assert factor_macro_alignment(ctx).points == 10


def test_macro_alignment_scores_zero_when_opposed():
    ctx = _ctx(macro_verdict={"status": "opposed", "reason": "bearish trend opposes",
                              "trend": "bearish"})
    r = factor_macro_alignment(ctx)
    assert r.points == 0
    assert "⚠️" in r.line


def test_macro_alignment_exempt_returns_none_not_zero():
    """An exempt horizon has no macro reading. Scoring it 0 would penalise
    every 6m-9m scenario for a check that cannot apply to it."""
    ctx = _ctx(macro_verdict={"status": "exempt", "reason": "6m is at the anchor",
                              "trend": None})
    assert factor_macro_alignment(ctx) is None


def test_macro_alignment_absent_returns_none():
    assert factor_macro_alignment(_ctx()) is None
