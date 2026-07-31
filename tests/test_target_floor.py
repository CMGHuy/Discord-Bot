"""Plan v8 Task V10: the minimum-target floor under TP1.

The live book's defect is structural, not statistical: `TP1 = entry ±
risk_distance × rr` with every rr override at 0.30-0.40 banked ~0.35R on a
win while a loss cost the full 1R, so the median designed target was 0.85%
against a 2.19% stop and the median winner could not arithmetically reach 2%.
The floor sets the win side. The stop side is V19's, deliberately untouched
here so the two effects stay attributable.
"""
import types

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.plan_engine import (
    apply_target_floor,
    build_confluence_plan,
    build_strategy_plan,
    target_floor_price,
)
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def floor_on(monkeypatch):
    """Pin the floor rather than trusting the shipped default, so these
    tests keep meaning the same thing if the default ever moves."""
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", True)
    monkeypatch.setattr(config, "MIN_TARGET_PCT", 2.5)


# -- the primitive ----------------------------------------------------------

def test_floor_pushes_a_too_close_target_out():
    # entry 100, rr-derived tp1 at +0.7% -> floored to +2.5%
    assert apply_target_floor(100.0, 100.7, "bullish") == pytest.approx(102.5)


def test_floor_mirrors_for_bearish():
    assert apply_target_floor(100.0, 99.3, "bearish") == pytest.approx(97.5)


def test_floor_never_pulls_a_larger_target_in():
    """A structurally larger target is left exactly where it is -- the floor
    is a minimum, not a setting."""
    assert apply_target_floor(100.0, 110.0, "bullish") == 110.0
    assert apply_target_floor(100.0, 90.0, "bearish") == 90.0


def test_floor_is_a_no_op_when_disabled(monkeypatch):
    """TARGET_FLOOR_ENABLED=false is V12 Step 2's log-only week: the floor is
    computable but nothing about the emitted plan changes."""
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", False)
    assert apply_target_floor(100.0, 100.7, "bullish") == 100.7
    # ...and the floor price is still available to log what it WOULD do.
    assert target_floor_price(100.0, "bullish") == pytest.approx(102.5)


def test_floor_reads_config_live_not_at_import(monkeypatch):
    """Both settings are hot-reloadable Fields (V9); a SIGHUP mid-session
    has to take effect on the next plan built, not the next restart."""
    monkeypatch.setattr(config, "MIN_TARGET_PCT", 5.0)
    assert apply_target_floor(100.0, 100.7, "bullish") == pytest.approx(105.0)


def test_floor_scales_with_entry_price():
    assert apply_target_floor(20.0, 20.1, "bullish") == pytest.approx(20.5)
    assert apply_target_floor(1000.0, 1005.0, "bullish") == pytest.approx(1025.0)


# -- every emitted plan satisfies it (Step 4) -------------------------------

def _ramp_df():
    return make_ohlcv([100 + i * 0.5 for i in range(80)])


STRATEGIES = ["MACD", "RSI", "EMA Crossover", "Fibonacci", "Support/Resistance",
              "VWAP", "MA Ribbon", "Break & Retest"]


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("horizon_key", ["2w", "4w", "3m", "9m"])
def test_every_strategy_plan_clears_the_floor(strategy, direction, horizon_key):
    plan = build_strategy_plan(_ramp_df(), 79, ticker="AAPL", strategy=strategy,
                               horizon_key=horizon_key, direction=direction)
    if plan is None:
        pytest.skip(f"{strategy} has no valid structure at this bar")
    entry = plan.trigger_price
    assert abs(plan.tp1 - entry) / entry >= config.MIN_TARGET_PCT / 100 - 1e-9


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_plan_direction_invariant_survives_the_floor(direction):
    """stop < entry < tp1 (mirrored for bearish). The floor only ever moves
    TP1 further from entry, so it cannot break this -- assert it anyway,
    because every downstream consumer assumes it."""
    plan = build_strategy_plan(_ramp_df(), 79, ticker="AAPL", strategy="MACD",
                               horizon_key="4w", direction=direction)
    if direction == "bullish":
        assert plan.stop_loss < plan.trigger_price < plan.tp1
    else:
        assert plan.stop_loss > plan.trigger_price > plan.tp1


def test_floor_breaks_the_rr_proportionality_of_stop_mult():
    """A consequence worth stating outright: E31's stop_mult was built so
    that scaling `risk_distance` scales the stop AND the rr-derived target
    together, leaving R:R untouched. The floor is an absolute % of entry, so
    once it binds, a wider stop no longer drags the target out with it --
    R:R falls instead. That is intended (the floor exists precisely to stop
    the target being a function of the stop), but it means "stop_mult
    preserves R:R" is now conditional, not universal.
    """
    from swingbot.core.plan_engine import _atr_plan
    base_stop, base_tp = _atr_plan(100.0, 2.0, "bullish", "4w", "RSI")
    wide_stop, wide_tp = _atr_plan(100.0, 2.0, "bullish", "4w", "RSI", stop_mult=1.2)

    assert (100.0 - wide_stop) == pytest.approx((100.0 - base_stop) * 1.2)
    assert base_tp == wide_tp == pytest.approx(102.5)     # both pinned at the floor
    base_rr = (base_tp - 100.0) / (100.0 - base_stop)
    wide_rr = (wide_tp - 100.0) / (100.0 - wide_stop)
    assert wide_rr < base_rr


def test_stop_is_untouched_by_the_floor(monkeypatch):
    """Step 2: the floor moves the target only. Stop retuning is V19, and
    keeping them separate is what makes the two effects attributable."""
    df = _ramp_df()
    plan_on = build_strategy_plan(df, 79, ticker="AAPL", strategy="MACD",
                                  horizon_key="4w", direction="bullish")
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", False)
    plan_off = build_strategy_plan(df, 79, ticker="AAPL", strategy="MACD",
                                   horizon_key="4w", direction="bullish")
    assert plan_on.stop_loss == plan_off.stop_loss
    assert plan_on.tp1 > plan_off.tp1        # the target, and only the target


# -- the confluence path (Step 3) -------------------------------------------

def _scenario(**overrides):
    base = dict(direction="bullish", entry=100.0, market_price=100.0,
                stop_loss=98.0, stop_sources=["Rolling S/R"],
                stop_distance_pct=2.0, tight_stop=False, atr_floor_pct=1.5,
                take_profit=110.0, target_distance_pct=10.0,
                target_sources=["Rolling S/R"], target2_price=None,
                target2_distance_pct=None, target2_sources=None, constraints={})
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _flat_df():
    n = 25
    highs = [100 + i * 0.1 for i in range(n)]
    return pd.DataFrame(
        {"Open": highs, "High": highs, "Low": [h - 1 for h in highs],
         "Close": highs, "Volume": [1_000_000] * n},
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


def test_confluence_tp1_is_floored():
    # rr 0.35 on a 2.00 risk -> 100.70, well inside the 102.50 floor.
    plan = build_confluence_plan(_scenario(), _flat_df(), ticker="XYZ",
                                 horizon_key="2w", primary_strategy="S/R Confluence")
    assert plan.tp1 == pytest.approx(102.5)


def test_confluence_scenario_target_survives_as_tp2_when_still_beyond():
    plan = build_confluence_plan(_scenario(take_profit=110.0), _flat_df(),
                                 ticker="XYZ", horizon_key="2w",
                                 primary_strategy="S/R Confluence")
    assert plan.tp1 == pytest.approx(102.5)
    assert plan.tp2 == 110.0


def test_confluence_tp2_dropped_when_the_floor_overtakes_it():
    """Step 3: a scenario target the floored TP1 has already passed must not
    survive as TP2 -- the runner would be through it the moment TP1 fills."""
    plan = build_confluence_plan(_scenario(take_profit=101.0), _flat_df(),
                                 ticker="XYZ", horizon_key="2w",
                                 primary_strategy="S/R Confluence")
    assert plan.tp1 == pytest.approx(102.5)
    assert plan.tp2 is None


def test_confluence_bearish_mirror():
    plan = build_confluence_plan(
        _scenario(direction="bearish", stop_loss=102.0, take_profit=90.0),
        _flat_df(), ticker="XYZ", horizon_key="2w",
        primary_strategy="S/R Confluence")
    assert plan.tp1 == pytest.approx(97.5)
    assert plan.tp2 == 90.0
    assert plan.stop_loss > plan.trigger_price > plan.tp1


def test_confluence_floor_off_leaves_the_old_geometry(monkeypatch):
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", False)
    plan = build_confluence_plan(_scenario(), _flat_df(), ticker="XYZ",
                                 horizon_key="2w", primary_strategy="S/R Confluence")
    assert plan.tp1 == pytest.approx(100.7)     # entry + 2.00 * 0.35
