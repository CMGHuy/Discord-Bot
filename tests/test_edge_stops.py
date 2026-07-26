"""Tasks E31/E32: MAE-informed stop sizing, MFE-informed TP2, time stops.

The pure distribution math is the briefs' own spec. The wiring blocks
exist because `_atr_plan` is the SHARED sizing source for both the live
plan builder and the backtest (`backtest._trade_plan_at`) -- so how these
overrides reach it decides whether backtests stay hermetic or start
silently reading the live journal. See test_backtest_sizing_path_is_untouched.
"""
import numpy as np
import pytest

from swingbot import config
from swingbot.core import plan_engine
from swingbot.core.edge.stops import MIN_SAMPLE, mae_informed_stop_mult
from swingbot.core.plan_engine import _atr_plan, build_strategy_plan
from swingbot.core.strategy_types import HORIZONS
from tests.helpers import make_ohlcv


def _winners(maes, strategy="RSI"):
    return [{"strategy": strategy, "outcome": "win", "mae_r": m} for m in maes]


# --- the distribution math ---------------------------------------------------

def test_p90_of_winner_mae_drives_the_mult():
    # 50 winners, MAE uniform 0.02..1.00 -> P90 ~ 0.90 -> 0.90+0.15 = 1.05
    entries = _winners([i / 50 for i in range(1, 51)])
    assert mae_informed_stop_mult(entries, "RSI") == pytest.approx(1.05, abs=0.03)


def test_tight_winners_tighten_the_stop():
    # winners never drew down past 0.4R -> P90 0.36 + 0.15 = 0.51 -> clamp 0.8
    entries = _winners([0.3 + 0.002 * i for i in range(50)])
    assert mae_informed_stop_mult(entries, "RSI") == 0.8


def test_clamped_at_1_3():
    entries = _winners([2.5] * 50)
    assert mae_informed_stop_mult(entries, "RSI") == 1.3


def test_small_sample_returns_none():
    entries = _winners([0.5] * (MIN_SAMPLE - 1))
    assert mae_informed_stop_mult(entries, "RSI") is None


def test_other_strategies_ignored():
    entries = _winners([0.5] * 60, strategy="MACD")
    assert mae_informed_stop_mult(entries, "RSI") is None


def test_losers_and_missing_mae_are_excluded():
    """Only WINNERS' excursions inform the stop -- a loser's MAE is by
    definition >= the stop it hit, which would just ratchet stops wider
    forever. Rows with mae_r=None (no bars available when journaled)
    must not be silently counted as 0.0 either."""
    losers = [{"strategy": "RSI", "outcome": "loss", "mae_r": 3.0} for _ in range(60)]
    assert mae_informed_stop_mult(losers, "RSI") is None

    blanks = [{"strategy": "RSI", "outcome": "win", "mae_r": None} for _ in range(60)]
    assert mae_informed_stop_mult(blanks, "RSI") is None

    mixed = _winners([0.9] * MIN_SAMPLE) + losers + blanks
    assert mae_informed_stop_mult(mixed, "RSI") == pytest.approx(1.05, abs=1e-9)


# --- wiring ------------------------------------------------------------------

@pytest.fixture(scope="module")
def df():
    return make_ohlcv([100 + i * 0.5 for i in range(80)])


def _plan(df, **kw):
    return build_strategy_plan(df, len(df) - 1, ticker="TEST", strategy="RSI",
                               horizon_key="4w", direction="bullish", **kw)


def test_atr_plan_default_is_bit_identical(df):
    """No stop_mult, flag off: today's numbers, exactly."""
    close, atr_val = 100.0, 2.0
    assert _atr_plan(close, atr_val, "bullish", "4w", "RSI") == \
           _atr_plan(close, atr_val, "bullish", "4w", "RSI", stop_mult=None)
    assert _atr_plan(close, atr_val, "bullish", "4w", "RSI", stop_mult=1.0) == \
           _atr_plan(close, atr_val, "bullish", "4w", "RSI")


def test_stop_mult_scales_risk_and_preserves_rr():
    """The multiplier scales `risk_distance`, which feeds BOTH the stop and
    the R:R-derived target -- so R:R survives untouched. That matters: the
    R:R override table and the 0.30 floor are frozen constants."""
    close, atr_val = 100.0, 2.0
    base_stop, base_tp = _atr_plan(close, atr_val, "bullish", "4w", "RSI")
    wide_stop, wide_tp = _atr_plan(close, atr_val, "bullish", "4w", "RSI", stop_mult=1.2)

    base_risk, wide_risk = close - base_stop, close - wide_stop
    assert wide_risk == pytest.approx(base_risk * 1.2)
    assert (wide_tp - close) / wide_risk == pytest.approx((base_tp - close) / base_risk)


def test_stop_mult_still_respects_the_max_risk_cap():
    """Widening may not punch through the horizon's own max_risk_pct cap."""
    close = 100.0
    huge_atr = close * HORIZONS["4w"]["max_risk_pct"] / 100  # already at the cap
    capped_stop, _ = _atr_plan(close, huge_atr, "bullish", "4w", "RSI", stop_mult=1.3)
    assert close - capped_stop == pytest.approx(close * HORIZONS["4w"]["max_risk_pct"] / 100)


def test_build_strategy_plan_threads_an_explicit_mult(df):
    base, wide = _plan(df), _plan(df, stop_mult=1.2)
    base_risk = base.trigger_price - base.stop_loss
    wide_risk = wide.trigger_price - wide.stop_loss
    assert wide_risk == pytest.approx(base_risk * 1.2)
    assert wide.stop_mult_applied == 1.2
    assert base.stop_mult_applied is None


def test_flag_off_never_reads_the_journal(df, monkeypatch):
    """Default-off means the journal is not even opened -- an unconditional
    read would make every plan build touch disk."""
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False)
    monkeypatch.setattr(plan_engine, "_journal_entries",
                        lambda: pytest.fail("journal must not be read while the flag is off"))
    assert _plan(df) is not None


def test_flag_on_resolves_the_mult_from_the_journal(df, monkeypatch):
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", True)
    monkeypatch.setattr(plan_engine, "_journal_entries",
                        lambda: _winners([2.5] * 60))          # -> clamped 1.3
    wide = _plan(df)
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False)
    base = _plan(df)
    assert (wide.trigger_price - wide.stop_loss) == \
           pytest.approx((base.trigger_price - base.stop_loss) * 1.3)
    assert wide.stop_mult_applied == 1.3 and base.stop_mult_applied is None


def test_flag_on_with_too_few_winners_changes_nothing(df, monkeypatch):
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", True)
    monkeypatch.setattr(plan_engine, "_journal_entries",
                        lambda: _winners([0.9] * (MIN_SAMPLE - 1)))
    plan = _plan(df)
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False)
    assert plan.stop_loss == _plan(df).stop_loss
    assert plan.stop_mult_applied is None


def test_a_broken_journal_never_breaks_plan_construction(df, monkeypatch):
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", True)

    def _boom():
        raise OSError("journal.json is corrupt")

    monkeypatch.setattr(plan_engine, "_journal_entries", _boom)
    plan = _plan(df)
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False)
    assert plan is not None and plan.stop_loss == _plan(df).stop_loss


def test_the_note_stays_out_of_quality_breakdown(df, monkeypatch):
    """The brief's snippet appended a STRING to plan.quality_breakdown. That
    list is strictly (name, points) tuples: embeds.py and views.py both
    render it as `{pts:+d}` and plan_to_dict flattens each row with
    list(row). A bare string there crashes both renderers and explodes into
    23 single characters in the persisted JSON -- so the applied factor
    lives in its own field, and quality scoring stays untouched."""
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", True)
    monkeypatch.setattr(plan_engine, "_journal_entries", lambda: _winners([2.5] * 60))
    quality_inputs = {"regime": "bull", "htf_bias": "bullish", "confluence_count": 3,
                      "volume_ratio": 1.2, "atr_pct": 2.0, "trigger_distance_pct": 1.0}
    plan = build_strategy_plan(df, len(df) - 1, ticker="TEST", strategy="RSI",
                               horizon_key="4w", direction="bullish",
                               quality_inputs=quality_inputs)
    assert plan.quality_breakdown, "quality scoring must have populated the breakdown"
    assert all(isinstance(row, tuple) and isinstance(row[1], int)
               for row in plan.quality_breakdown), "breakdown must stay (name, points) tuples"
    assert plan.stop_mult_applied == 1.3

    # And it survives the persistence round-trip the plan store uses.
    restored = plan_engine.plan_from_dict(plan_engine.plan_to_dict(plan))
    assert restored.stop_mult_applied == 1.3
    assert restored.stop_loss == plan.stop_loss


def test_plans_predating_the_field_still_load():
    """plan_from_dict drops unknown keys and defaults missing ones, so every
    plan already persisted in data/ loads with stop_mult_applied=None."""
    plan = plan_engine.plan_from_dict({
        "plan_id": "old", "ticker": "T", "created_at": "2026-01-01", "source": "strategy",
        "strategy": "RSI", "horizon_key": "4w", "direction": "bullish",
        "entry_type": "market", "trigger_price": 100.0, "entry_price": 100.0,
        "expiry_bars": 5, "stop_loss": 95.0, "tp1": 102.0, "tp1_fraction": 0.5,
        "tp2": None, "breakeven_trigger_fraction": 0.5, "trail_atr_mult": 2.5,
        "quality_score": 0, "quality_breakdown": [], "tier": "C", "badge": "WEAK",
        "badge_stats": {}, "status": "PENDING",
    })
    assert plan.stop_mult_applied is None


def test_structural_builders_are_untouched():
    """Fibonacci/Elliott/SR stops sit behind real structure, not an ATR
    multiple -- scaling them would move the stop off the swing it exists
    to hide behind, so the multiplier deliberately does not reach them."""
    import inspect
    for fn in (plan_engine._fibonacci_plan, plan_engine._elliott_plan, plan_engine._sr_plan):
        assert "stop_mult" not in inspect.signature(fn).parameters, (
            f"{fn.__name__} must stay structure-derived"
        )


def test_backtest_sizing_path_is_untouched(df):
    """backtest._trade_plan_at shares _atr_plan with the live builder. The
    multiplier is resolved at the build_strategy_plan BOUNDARY, never
    inside _atr_plan, so a backtest can never silently start pricing 2020
    trades off the live journal. stop_mult stays an injected parameter the
    E33 fold harness supplies explicitly."""
    import inspect
    from swingbot.core import backtest
    assert "stop_mult" not in inspect.signature(backtest._trade_plan_at).parameters
    assert inspect.signature(_atr_plan).parameters["stop_mult"].default is None

    from swingbot.core.indicators import atr
    atr_series = atr(df, 14)
    config_flag = config.DATA_DRIVEN_STOPS_ENABLED
    assert config_flag is False, "this factor must ship default-off"
    before = backtest._trade_plan_at(df, 79, "bullish", "RSI", "4w", atr_series)
    assert before == backtest._trade_plan_at(df, 79, "bullish", "RSI", "4w", atr_series)
    assert np.isfinite(before[1])


# --- E32: MFE-informed TP2 + time stops --------------------------------------

def _winners_with(key, values, strategy="RSI"):
    return [{"strategy": strategy, "outcome": "win", key: v} for v in values]


def test_mfe_tp2_is_p60_of_winner_mfe():
    from swingbot.core.edge.stops import mfe_informed_tp2_r
    entries = _winners_with("mfe_r", [i / 25 for i in range(1, 51)])  # 0.04..2.0
    # P60 of uniform(0.04..2.0) ~ 1.216
    assert mfe_informed_tp2_r(entries, "RSI") == pytest.approx(1.216, abs=0.06)


def test_mfe_tp2_floors_at_half_r():
    from swingbot.core.edge.stops import mfe_informed_tp2_r
    entries = _winners_with("mfe_r", [0.2] * 50)
    assert mfe_informed_tp2_r(entries, "RSI") == 0.5


def test_time_stop_day():
    from swingbot.core.edge.stops import optimal_time_stop_days
    # 40 winners hit 0.5R by day 3, 10 stragglers by day 12:
    # cumulative 80% is reached at day 3
    entries = (_winners_with("days_to_half_r", [3] * 40)
               + _winners_with("days_to_half_r", [12] * 10))
    assert optimal_time_stop_days(entries, "RSI") == 3


def test_time_stop_none_under_sample():
    from swingbot.core.edge.stops import optimal_time_stop_days
    assert optimal_time_stop_days(_winners_with("days_to_half_r", [3] * 10), "RSI") is None


def test_mfe_and_time_stop_ignore_losers_and_other_strategies():
    from swingbot.core.edge.stops import mfe_informed_tp2_r, optimal_time_stop_days
    losers = [{"strategy": "RSI", "outcome": "loss", "mfe_r": 5.0, "days_to_half_r": 1}
              for _ in range(60)]
    assert mfe_informed_tp2_r(losers, "RSI") is None
    assert optimal_time_stop_days(losers, "RSI") is None
    assert mfe_informed_tp2_r(_winners_with("mfe_r", [1.0] * 60, strategy="MACD"), "RSI") is None


# --- E32 wiring --------------------------------------------------------------

def _macd_plan(df, **kw):
    """MACD is the one strategy whose frozen exit params enable TP2 at all
    (plan_engine.STRATEGY_EXIT_PARAMS), so it's the only path where a TP2
    override is even reachable."""
    supports = [SimpleLevel(90.0), SimpleLevel(80.0)]
    resistances = [SimpleLevel(200.0), SimpleLevel(400.0)]
    return build_strategy_plan(df, len(df) - 1, ticker="TEST", strategy="MACD",
                               horizon_key="4w", direction="bullish",
                               level_map=(supports, resistances), **kw)


class SimpleLevel:
    def __init__(self, price):
        self.price = price


def test_tp2_r_override_converts_to_a_price_at_that_r_multiple(df):
    base = _macd_plan(df)
    over = _macd_plan(df, tp2_r=1.2)
    risk = over.trigger_price - over.stop_loss
    assert over.tp2 == pytest.approx(over.trigger_price + risk * 1.2)
    assert over.tp2_r_applied == 1.2
    assert base.tp2_r_applied is None
    assert base.tp2 != over.tp2


def test_tp2_r_override_respects_the_beyond_tp1_and_leg_cap_invariants(df):
    """The same two rules select_tp2 enforces. A TP2 that isn't strictly
    beyond TP1, or whose TP1->TP2 leg exceeds MAX_TARGET2_LEG_MULTIPLE of
    the entry->TP1 leg, is not a runner target -- the level-based TP2
    stands instead of being clobbered by a nonsense number."""
    from swingbot.core.levels import MAX_TARGET2_LEG_MULTIPLE
    base = _macd_plan(df)
    rr = (base.tp1 - base.trigger_price) / (base.trigger_price - base.stop_loss)

    inside = _macd_plan(df, tp2_r=rr * 0.5)          # lands short of TP1
    assert inside.tp2 == base.tp2 and inside.tp2_r_applied is None

    too_far = _macd_plan(df, tp2_r=rr * (MAX_TARGET2_LEG_MULTIPLE + 2))
    assert too_far.tp2 == base.tp2 and too_far.tp2_r_applied is None


def test_tp2_override_never_forces_tp2_onto_a_strategy_validated_without_it(df):
    """The per-strategy tp2 on/off table is a frozen TRAIN-grid result.
    This override changes the tp2 PRICE where tp2 is already enabled; it
    must not switch tp2 on for a strategy whose validated exit model has
    none, which would be a different exit model than E33 is set up to judge."""
    from swingbot.core.plan_engine import exit_params_for
    assert exit_params_for("RSI")["tp2"] is False
    plan = _plan(df, tp2_r=1.5)
    assert plan.tp2 is None and plan.tp2_r_applied is None


def test_time_stop_days_is_recorded_and_closes_nothing(df):
    plan = _plan(df, time_stop_days=4)
    assert plan.time_stop_days == 4
    # Advisory only (E48's recycler reads it) -- the lifecycle is untouched.
    assert plan.status == plan_engine.PlanStatus.ACTIVE
    assert plan.legs_realized == []
    assert _plan(df).time_stop_days is None


def test_flag_on_resolves_tp2_and_time_stop_from_the_journal(df, monkeypatch):
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", True)
    monkeypatch.setattr(plan_engine, "_journal_entries", lambda: [
        {"strategy": "MACD", "outcome": "win", "mae_r": 0.4,
         "mfe_r": 1.2, "days_to_half_r": 3} for _ in range(60)
    ])
    plan = _macd_plan(df)
    assert plan.tp2_r_applied == pytest.approx(1.2)
    assert plan.time_stop_days == 3
    assert plan.stop_mult_applied == pytest.approx(0.8)   # E31 still resolves too


def test_flag_off_resolves_neither(df, monkeypatch):
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False)
    monkeypatch.setattr(plan_engine, "_journal_entries",
                        lambda: pytest.fail("journal must not be read while the flag is off"))
    plan = _macd_plan(df)
    assert plan.tp2_r_applied is None and plan.time_stop_days is None


def test_e32_fields_round_trip_and_default_on_old_plans(df):
    plan = _macd_plan(df, tp2_r=1.2, time_stop_days=4)
    restored = plan_engine.plan_from_dict(plan_engine.plan_to_dict(plan))
    assert restored.tp2_r_applied == 1.2 and restored.time_stop_days == 4
    assert restored.tp2 == plan.tp2


def test_confluence_plans_are_untouched_by_both_overrides(df, monkeypatch):
    """build_confluence_plan prices off the scenario's own structural stop
    and target -- same reasoning that keeps E31 off the Fibonacci/Elliott
    builders. Left for E33 to judge separately, not silently changed here."""
    import inspect
    sig = inspect.signature(plan_engine.build_confluence_plan).parameters
    assert "tp2_r" not in sig and "time_stop_days" not in sig and "stop_mult" not in sig


def test_the_leg_cap_ceilings_any_mfe_tp2_at_four_times_rr(df):
    """Worth knowing before reading E33's folds: MAX_TARGET2_LEG_MULTIPLE
    (3.0, frozen) means a valid TP2 can sit at most 4x the plan's own R:R
    out -- 1.4R for MACD's rr=0.35. A P60 winner-MFE above that is simply
    not adoptable as a TP2 without moving a frozen constant, and the
    level-based TP2 stands instead."""
    from swingbot.core.levels import MAX_TARGET2_LEG_MULTIPLE
    from swingbot.core.plan_engine import _rr_for
    rr = _rr_for("MACD", "4w")
    ceiling = rr * (1 + MAX_TARGET2_LEG_MULTIPLE)
    assert ceiling == pytest.approx(1.4)

    base = _macd_plan(df)
    assert _macd_plan(df, tp2_r=ceiling - 0.01).tp2_r_applied == pytest.approx(ceiling - 0.01)
    over_ceiling = _macd_plan(df, tp2_r=ceiling + 0.01)
    assert over_ceiling.tp2_r_applied is None and over_ceiling.tp2 == base.tp2
