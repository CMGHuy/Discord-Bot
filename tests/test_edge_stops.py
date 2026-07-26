"""Task E31: MAE-informed stop sizing.

The pure distribution math (first block) is the brief's own spec. The
wiring block below it exists because `_atr_plan` is the SHARED sizing
source for both the live plan builder and the backtest
(`backtest._trade_plan_at`) -- so how the multiplier reaches it decides
whether backtests stay hermetic or start silently reading the live
journal. See test_backtest_sizing_path_is_untouched.
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
