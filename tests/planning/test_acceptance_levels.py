"""v129 arm transforms (spec § Definitions): disaster stop, close threshold,
eligibility, flag parsing -- and that the flag-off build is untouched."""
import types

import pytest

from swingbot import config
from swingbot.core.planning import acceptance_levels as al
from swingbot.core.planning.builders import build_confluence_plan
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.helpers import make_ohlcv


def _flags(monkeypatch, enabled=True, arms="Z,B", m=1.0, b=0.25):
    monkeypatch.setattr(config, "ACCEPTANCE_EXIT_ENABLED", enabled)
    monkeypatch.setattr(config, "ACCEPTANCE_EXIT_ARMS", arms)
    monkeypatch.setattr(config, "ACCEPTANCE_DISASTER_ATR_M", m)
    monkeypatch.setattr(config, "ACCEPTANCE_CLOSE_BUFFER_ATR", b)
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


def _confluence(direction, entry, stop, target, df=None):
    scenario = types.SimpleNamespace(
        direction=direction, entry=entry, stop_loss=stop, take_profit=target,
        target_sources=["Rolling S/R"], stop_sources=["Rolling S/R"])
    return build_confluence_plan(scenario, df if df is not None else make_ohlcv([entry] * 60),
                                 ticker="XYZ", horizon_key="4w",
                                 primary_strategy="S/R Confluence")


def _br_plan(**kw):
    base = dict(plan_id="p", ticker="DELL", created_at="2024-01-02", source="strategy",
                strategy="Break & Retest", horizon_key="2m", direction="bullish",
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=5,
                stop_loss=96.0, tp1=106.0, tp1_fraction=0.5, tp2=None,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.ACTIVE)
    base.update(kw)
    return TradePlanV2(**base)


# --- flag parsing ------------------------------------------------------------

def test_flag_off_means_no_arm_even_if_arms_listed(monkeypatch):
    _flags(monkeypatch, enabled=False, arms="Z,B")
    assert al.enabled_arms() == frozenset()


def test_enabled_arms_parses_case_and_drops_unknown(monkeypatch):
    _flags(monkeypatch, arms="x, z ,")
    assert al.enabled_arms() == frozenset({"Z"})
    _flags(monkeypatch, arms="b,Z")
    assert al.enabled_arms() == frozenset({"Z", "B"})
    _flags(monkeypatch, arms="")
    assert al.enabled_arms() == frozenset()


# --- pure geometry -----------------------------------------------------------

def test_disaster_stop_bullish_is_level_minus_m_atr():
    assert al.disaster_stop(100.0, 99.0, 1.0, 0.5, "bullish") == pytest.approx(98.5)


def test_disaster_stop_pulled_in_to_the_2pct_cap():
    assert al.disaster_stop(100.0, 98.5, 1.0, 1.5, "bullish") == pytest.approx(98.0)


def test_disaster_stop_bearish_mirror_and_cap():
    assert al.disaster_stop(100.0, 101.0, 1.0, 0.5, "bearish") == pytest.approx(101.5)
    assert al.disaster_stop(100.0, 101.5, 1.0, 1.5, "bearish") == pytest.approx(102.0)


def test_close_threshold_both_directions():
    assert al.close_threshold(99.0, 2.0, 0.25, "bullish") == pytest.approx(98.5)
    assert al.close_threshold(101.0, 2.0, 0.25, "bearish") == pytest.approx(101.5)
    assert al.close_threshold(99.0, 2.0, 0.0, "bullish") == pytest.approx(99.0)


def test_confluence_eligible_boundary_and_wrong_side():
    assert al.confluence_eligible(100.0, 98.0, "bullish")        # exactly 2%: eligible
    assert not al.confluence_eligible(100.0, 97.9, "bullish")    # beyond the cap
    assert not al.confluence_eligible(100.0, 100.5, "bullish")   # profit side
    assert al.confluence_eligible(100.0, 102.0, "bearish")
    assert not al.confluence_eligible(100.0, 99.5, "bearish")
    assert not al.confluence_eligible(100.0, None, "bullish")


ODD_ENTRIES = (123.45, 17.31, 987.65, 3.07, 456.789)


@pytest.mark.parametrize("entry", ODD_ENTRIES)
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_capped_disaster_stop_never_exceeds_the_hard_cap(entry, direction):
    """A far level is pulled to the cap; float noise must not leave the loss
    at 2.0000000000000004% (plan_manager's strict risk_cap would reject it)."""
    from swingbot.core.risk_limits import planned_loss_pct
    level = entry * (0.9 if direction == "bullish" else 1.1)
    stop = al.disaster_stop(entry, level, 1.0, 5.0, direction)
    assert planned_loss_pct(entry, stop) <= 2.0
    expected = entry * (0.98 if direction == "bullish" else 1.02)
    assert stop == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("entry", ODD_ENTRIES)
def test_confluence_eligible_boundary_survives_float_noise(entry):
    assert al.confluence_eligible(entry, entry * 0.98, "bullish")
    assert al.confluence_eligible(entry, entry * 1.02, "bearish")
    assert not al.confluence_eligible(entry, entry * 0.9795, "bullish")


def test_atr_at_falls_back_on_short_history():
    df = make_ohlcv([100.0] * 5)                 # < 14 bars: ATR14 is NaN
    assert al.atr_at(df, 4, 100.0) == pytest.approx(2.0)   # 2% of entry


# --- builder, flag on / off --------------------------------------------------

def test_flag_off_confluence_build_is_unchanged(monkeypatch):
    _flags(monkeypatch, enabled=False)
    plan = _confluence("bullish", 100.0, 99.0, 102.0)
    assert plan.stop_loss == pytest.approx(99.0)
    assert plan.acceptance_level == pytest.approx(99.0)
    assert plan.acceptance_close_below is None


def test_eligible_confluence_plan_gets_disaster_stop_and_threshold(monkeypatch):
    _flags(monkeypatch, enabled=False)
    off = _confluence("bullish", 100.0, 99.0, 102.0)
    _flags(monkeypatch, m=1.0, b=0.25)
    df = make_ohlcv([100.0] * 60)
    on = _confluence("bullish", 100.0, 99.0, 102.0, df)
    atr = al.atr_at(df, len(df) - 1, 100.0)
    assert on.stop_loss == pytest.approx(max(99.0 - atr, 98.0))
    assert on.acceptance_close_below == pytest.approx(99.0 - 0.25 * atr)
    assert on.tp1 == off.tp1 and on.tp2 == off.tp2          # targets unchanged
    assert on.entry_type == off.entry_type                  # entries unchanged


def test_bearish_confluence_mirror(monkeypatch):
    _flags(monkeypatch, m=0.5, b=0.25)
    df = make_ohlcv([100.0] * 60)
    plan = _confluence("bearish", 100.0, 101.0, 98.0, df)
    atr = al.atr_at(df, len(df) - 1, 100.0)
    assert plan.stop_loss == pytest.approx(min(101.0 + 0.5 * atr, 102.0))
    assert plan.acceptance_close_below == pytest.approx(101.0 + 0.25 * atr)


def test_not_eligible_clamped_plan_keeps_todays_stop_and_no_exit(monkeypatch):
    _flags(monkeypatch)
    plan = _confluence("bullish", 100.0, 96.0, 104.0)        # 4% level -> clamped
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.acceptance_level == pytest.approx(96.0)
    assert plan.acceptance_close_below is None


def test_arm_b_only_leaves_confluence_plans_alone(monkeypatch):
    _flags(monkeypatch, arms="B")
    plan = _confluence("bullish", 100.0, 99.0, 102.0)
    assert plan.stop_loss == pytest.approx(99.0)
    assert plan.acceptance_close_below is None


def test_arm_b_sets_threshold_and_keeps_the_stop(monkeypatch):
    _flags(monkeypatch, arms="B", b=0.25)
    monkeypatch.setattr("swingbot.core.market.entry_filters.break_retest_level_at",
                        lambda df, index, horizon_key, direction: 99.0)
    df = make_ohlcv([100.0] * 60)
    plan = _br_plan()
    al.stamp_strategy_acceptance(plan, df, 59)
    atr = al.atr_at(df, 59, 100.0)
    assert plan.acceptance_level == 99.0
    assert plan.acceptance_close_below == pytest.approx(99.0 - 0.25 * atr)
    assert plan.stop_loss == 96.0


def test_arm_b_not_eligible_without_a_level():
    plan = _br_plan(acceptance_level=None)
    assert al.apply_arm_b(plan, 2.0, 0.25) is False
    assert plan.acceptance_close_below is None


def test_other_strategies_get_no_level(monkeypatch):
    _flags(monkeypatch)
    plan = _br_plan(strategy="RSI")
    al.stamp_strategy_acceptance(plan, make_ohlcv([100.0] * 60), 59)
    assert plan.acceptance_level is None and plan.acceptance_close_below is None


def test_no_lookahead_stop_and_threshold(monkeypatch):
    """Spec § Testing: values for a plan created at bar t are identical when
    computed on df.iloc[:t+1]."""
    _flags(monkeypatch, m=1.0, b=0.25)
    df = load_ohlcv("DELL")
    t = 849
    entry = float(df["Close"].iloc[t])
    assert al.atr_at(df, t, entry) == al.atr_at(df.iloc[:t + 1], t, entry)
    level = entry * 0.99
    scenario_full = _confluence("bullish", entry, level, entry * 1.02, df.iloc[:t + 1])
    atr = al.atr_at(df, t, entry)
    assert scenario_full.stop_loss == pytest.approx(
        al.disaster_stop(entry, level, atr, 1.0, "bullish"))
    assert scenario_full.acceptance_close_below == pytest.approx(
        al.close_threshold(level, atr, 0.25, "bullish"))
