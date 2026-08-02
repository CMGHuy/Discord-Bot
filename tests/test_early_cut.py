"""Plan v8 Task V51 Step 3: cut a loser before it reaches the full stop.

"If it's obvious this trade is going to lose, cut sooner" made testable, as
three independent predicates so V52 can grid them separately and attribute what
each is worth.

The two properties that matter most here are not the predicates themselves:

  1. **Flags off changes nothing.** All three default off, so every pre-V51
     exit path must be byte-identical until something turns one on.
  2. **An early cut is a LOSS, not a scratch.** `scratch`/`timeout` are excluded
     from the win-rate denominator, so classifying cuts as either would let
     "cut losers sooner" manufacture win rate by deleting losses from the
     denominator -- the exact move V6 Step 4 forbids, aimed at the exact number
     V52's 80% bar is trying to measure honestly.
"""
import pytest

from swingbot import config
from swingbot.core.plan_engine import (
    PlanStatus,
    TradePlanV2,
    early_cut_outcome,
    early_cut_reason,
    simulate_exit,
)
from tests.helpers import make_ohlcv


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="AAPL", created_at="2024-01-02", source="strategy",
        strategy="Fibonacci", horizon_key="2w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=0.5, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[], tier="C",
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


@pytest.fixture(autouse=True)
def _all_flags_off(monkeypatch):
    """Pin the shipped defaults rather than trusting them, so these tests keep
    meaning the same thing if a default ever moves. Individual tests opt in."""
    monkeypatch.setattr(config, "EARLY_CUT_THESIS_ENABLED", False)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_ENABLED", False)
    monkeypatch.setattr(config, "EARLY_CUT_MAE_ENABLED", False)


# -- property 1: off is inert ------------------------------------------------

def _drifting_df():
    """Entry 100 (stop 95, tp1 110), then five bars that go nowhere: never
    within reach of stop or target, MFE stays under 0.5R, MAE under 0.75R."""
    return make_ohlcv([
        100.0,
        (100.0, 101.0, 99.0, 99.5),
        (99.5, 100.5, 98.5, 99.0),
        (99.0, 100.0, 98.0, 98.5),
        (98.5, 99.5, 97.5, 98.0),
        (98.0, 99.0, 97.0, 98.0),
    ])


@pytest.mark.parametrize("scale_out", [False, True])
def test_all_flags_off_is_a_timeout_exactly_as_before(scale_out):
    res = simulate_exit(_drifting_df(), 0, _plan(), scale_out=scale_out,
                        max_holding_days=5)
    assert res.outcome == "timeout"
    assert res.legs[-1]["reason"] == "timeout"


def test_predicate_returns_none_with_everything_off():
    assert early_cut_reason(_plan(), bars_held=99, mfe_r=0.0, mae_r=0.99,
                            bar_close=1.0) is None


# -- property 2: the denominator boundary ------------------------------------

def test_a_losing_cut_is_a_loss_not_a_scratch():
    """The correctness boundary. scratch/timeout are excluded from the win-rate
    denominator; if cuts landed there, cutting losers would raise win rate by
    deleting losses. V6 Step 4 forbids exactly that."""
    assert early_cut_outcome(-0.4) == "loss"
    assert early_cut_outcome(-0.001) == "loss"


def test_a_non_losing_cut_is_a_scratch():
    """Mirrors the existing breakeven_stop semantics -- a trade cut while not
    down is not a loss, and calling it one would be its own dishonesty."""
    assert early_cut_outcome(0.0) == "scratch"
    assert early_cut_outcome(0.2) == "scratch"


@pytest.mark.parametrize("scale_out", [False, True])
def test_cut_trade_lands_in_the_denominator_end_to_end(monkeypatch, scale_out):
    monkeypatch.setattr(config, "EARLY_CUT_TIME_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_BARS", 3)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_MIN_R", 0.5)
    res = simulate_exit(_drifting_df(), 0, _plan(), scale_out=scale_out,
                        max_holding_days=5)
    assert res.outcome == "loss"               # NOT scratch, NOT timeout
    assert res.legs[-1]["reason"] == "time_stop"


# -- (a) thesis invalidation -------------------------------------------------

def test_thesis_cut_fires_on_a_close_back_through_the_trigger(monkeypatch):
    monkeypatch.setattr(config, "EARLY_CUT_THESIS_ENABLED", True)
    df = make_ohlcv([
        100.0,
        (100.0, 102.0, 99.5, 101.0),   # 1: holds above trigger 100
        (101.0, 101.5, 98.0, 99.0),    # 2: CLOSES at 99 < 100 -- invalidated
        (99.0, 100.0, 98.0, 99.5),
    ])
    res = simulate_exit(df, 0, _plan(trigger_price=100.0), max_holding_days=5)
    assert res.legs[-1]["reason"] == "thesis_invalidated"
    assert res.exit_index == 2
    assert res.legs[-1]["exit_price"] == pytest.approx(99.0)   # that bar's CLOSE


def test_thesis_cut_ignores_a_wick_through_the_level(monkeypatch):
    """Close, never an intrabar touch: one wick below the level should not
    eject a trade the level still supports."""
    monkeypatch.setattr(config, "EARLY_CUT_THESIS_ENABLED", True)
    df = make_ohlcv([
        100.0,
        (100.0, 102.0, 97.0, 101.0),   # 1: LOW 97 pierces 100, close 101 holds
        (101.0, 103.0, 100.5, 102.0),
        (102.0, 111.0, 101.0, 110.5),  # 3: reaches tp1
    ])
    res = simulate_exit(df, 0, _plan(trigger_price=100.0), max_holding_days=5)
    assert res.outcome == "win"


def test_thesis_cut_mirrors_for_bearish(monkeypatch):
    monkeypatch.setattr(config, "EARLY_CUT_THESIS_ENABLED", True)
    df = make_ohlcv([
        100.0,
        (100.0, 100.5, 98.0, 99.0),    # 1: holds below trigger
        (99.0, 102.0, 98.5, 101.0),    # 2: CLOSES 101 > 100 -- invalidated
        (101.0, 102.0, 100.0, 101.0),
    ])
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0, trigger_price=100.0)
    res = simulate_exit(df, 0, plan, max_holding_days=5)
    assert res.legs[-1]["reason"] == "thesis_invalidated"


# -- (b) time stop -----------------------------------------------------------

def test_time_stop_fires_only_after_the_configured_bars(monkeypatch):
    monkeypatch.setattr(config, "EARLY_CUT_TIME_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_BARS", 4)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_MIN_R", 0.5)
    res = simulate_exit(_drifting_df(), 0, _plan(), max_holding_days=5)
    assert res.legs[-1]["reason"] == "time_stop"
    assert res.exit_index == 4          # not 3, not 5


def test_time_stop_spares_a_trade_that_did_move(monkeypatch):
    """Judged on MFE, not the last close: a trade that ran to +0.6R and gave it
    back has not 'gone nowhere', so the time stop must not claim it."""
    monkeypatch.setattr(config, "EARLY_CUT_TIME_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_BARS", 3)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_MIN_R", 0.5)
    df = make_ohlcv([
        100.0,
        (100.0, 103.5, 99.5, 100.5),   # 1: high 103.5 -> MFE 0.7R (risk 5)
        (100.5, 101.0, 99.0, 99.5),
        (99.5, 100.5, 98.5, 99.0),     # 3: bars_held 3, but MFE 0.7 >= 0.5
        (99.0, 100.0, 98.0, 98.5),
    ])
    res = simulate_exit(df, 0, _plan(), max_holding_days=4)
    assert res.outcome == "timeout"


# -- (c) adverse excursion ---------------------------------------------------

def test_mae_cut_fires_when_drawdown_nears_the_stop(monkeypatch):
    monkeypatch.setattr(config, "EARLY_CUT_MAE_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_MAE_FRACTION", 0.75)
    monkeypatch.setattr(config, "EARLY_CUT_MAE_MAX_MFE_R", 0.25)
    df = make_ohlcv([
        100.0,
        (100.0, 100.5, 99.0, 99.5),
        (99.5, 100.0, 96.0, 96.5),     # 2: low 96 -> MAE 0.8R, MFE ~0.1R
        (96.5, 97.0, 95.5, 96.0),
    ])
    res = simulate_exit(df, 0, _plan(), max_holding_days=5)
    assert res.legs[-1]["reason"] == "adverse_excursion"
    assert res.exit_index == 2
    assert res.outcome == "loss"


def test_mae_cut_spares_a_trade_that_had_worked_first(monkeypatch):
    """MFE gate: a trade that genuinely ran before turning is not the 'never
    worked' case this predicate is for."""
    monkeypatch.setattr(config, "EARLY_CUT_MAE_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_MAE_FRACTION", 0.75)
    monkeypatch.setattr(config, "EARLY_CUT_MAE_MAX_MFE_R", 0.25)
    df = make_ohlcv([
        100.0,
        (100.0, 104.0, 99.5, 103.0),   # 1: MFE 0.8R -- it worked
        (103.0, 103.5, 96.0, 96.5),    # 2: MAE 0.8R but MFE already 0.8R
        (96.5, 97.0, 95.5, 96.0),
    ])
    res = simulate_exit(df, 0, _plan(), max_holding_days=5)
    assert res.legs[-1]["reason"] != "adverse_excursion"


def test_mae_fraction_at_or_above_one_is_inert(monkeypatch):
    """1.0 is the stop itself, which the walk checks first -- so the flag can
    never fire and the help text says so."""
    monkeypatch.setattr(config, "EARLY_CUT_MAE_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_MAE_FRACTION", 1.0)
    monkeypatch.setattr(config, "EARLY_CUT_MAE_MAX_MFE_R", 0.25)
    df = make_ohlcv([
        100.0,
        (100.0, 100.5, 99.0, 99.5),
        (99.5, 100.0, 96.0, 96.5),     # MAE 0.8R -- under 1.0, no fire
        (96.5, 97.0, 94.0, 94.5),      # low 94 <= stop 95 -- the real stop wins
    ])
    res = simulate_exit(df, 0, _plan(), max_holding_days=5)
    assert res.legs[-1]["reason"] == "stop"
    assert res.r_total == pytest.approx(-1.0)


# -- ordering and interaction ------------------------------------------------

def test_the_real_stop_and_target_still_win_the_bar(monkeypatch):
    """Predicates are checked after stop and target, so a bar that resolves
    normally is untouched however many flags are on."""
    monkeypatch.setattr(config, "EARLY_CUT_THESIS_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_BARS", 1)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_MIN_R", 5.0)   # would fire at once
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),   # 1: reaches tp1 on the very first bar
    ])
    res = simulate_exit(df, 0, _plan(), max_holding_days=5)
    assert res.outcome == "win"


def test_thesis_takes_precedence_over_the_other_two(monkeypatch):
    """Fixed order (a, b, c): a bar satisfying several reports the most
    defensible reason, so V52's attribution is stable."""
    monkeypatch.setattr(config, "EARLY_CUT_THESIS_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_BARS", 1)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_MIN_R", 5.0)
    assert early_cut_reason(_plan(trigger_price=100.0), bars_held=9, mfe_r=0.0,
                            mae_r=0.0, bar_close=99.0) == "thesis_invalidated"


def test_runner_past_tp1_is_never_cut(monkeypatch):
    """Phase 1 only. Past TP1 the runner's stop is already at breakeven, so
    there is no loss left to cut -- and a time stop firing on a profitable
    runner would be a bug, not a feature."""
    monkeypatch.setattr(config, "EARLY_CUT_TIME_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_BARS", 1)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_MIN_R", 99.0)   # always true
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),   # 1: TP1 touched -> runner starts
        (110.5, 112.0, 109.0, 111.0),
        (111.0, 113.0, 110.0, 112.0),
        (112.0, 114.0, 111.0, 113.0),
    ])
    res = simulate_exit(df, 0, _plan(), scale_out=True, max_holding_days=4)
    assert res.outcome == "win"
    assert res.legs[0]["reason"] == "tp1"
    assert res.legs[-1]["reason"].startswith("runner_")


def test_cut_is_priced_at_the_bar_close_not_minus_one_r(monkeypatch):
    """The whole point: the stop was never reached, so R must reflect where the
    trade actually exited."""
    monkeypatch.setattr(config, "EARLY_CUT_TIME_ENABLED", True)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_BARS", 4)
    monkeypatch.setattr(config, "EARLY_CUT_TIME_MIN_R", 0.5)
    res = simulate_exit(_drifting_df(), 0, _plan(), max_holding_days=5)
    # bar 4 closes at 98.0; entry 100, risk 5 -> -0.4R, nowhere near -1R
    assert res.r_total == pytest.approx(-0.4)
    assert res.legs[-1]["exit_price"] == pytest.approx(98.0)
