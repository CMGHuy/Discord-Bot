import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv


def _run_with_forced_entry(monkeypatch, df, entry_bar, direction="bullish",
                           strategy="EMA Crossover", horizon="2w", **kwargs):
    import swingbot.core.backtest as bt
    bull = pd.Series(False, index=df.index)
    bear = pd.Series(False, index=df.index)
    (bull if direction == "bullish" else bear).iloc[entry_bar] = True
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *a, **k: (bull, bear))
    return bt.run_backtest("TEST", df, strategy, horizon, **kwargs)


def test_scratch_when_trigger_reached_then_returns_to_entry(monkeypatch):
    # Constant 100 with 1% spread: every bar's high=100.5 >= trigger 100.35,
    # and every bar's low=99.5 <= entry 100. Bar e+1 arms the break-even move
    # (original stop 98 not hit, target 100.7 not hit), bar e+2 hits the moved
    # stop at entry -> scratch at ~0R.
    df = make_ohlcv(np.full(60, 100.0), spread_pct=1.0)
    s = _run_with_forced_entry(monkeypatch, df, entry_bar=40)
    assert s.scratches == 1 and s.wins == 0 and s.losses == 0
    t = s.trades[0]
    assert t.outcome == "scratch"
    assert t.exit_price == pytest.approx(100.0)
    assert t.r_multiple == pytest.approx(0.0, abs=1e-9)
    assert s.win_rate is None            # no wins+losses -> undefined, not 100%
    assert s.expectancy_r == pytest.approx(0.0, abs=1e-9)


def test_win_when_target_hit_before_stop(monkeypatch):
    closes = np.full(60, 100.0)
    closes[41:] = 101.0                  # bar e+1 jumps: high 101.5 >= target 100.7
    df = make_ohlcv(closes, spread_pct=1.0)
    s = _run_with_forced_entry(monkeypatch, df, entry_bar=40)
    assert s.wins == 1 and s.losses == 0 and s.scratches == 0
    assert s.win_rate == pytest.approx(100.0)


def test_loss_when_original_stop_hit_before_trigger(monkeypatch):
    closes = np.full(60, 100.0)
    closes[41:] = 97.0                   # bar e+1 collapses: low 96.5 <= stop 98
    df = make_ohlcv(closes, spread_pct=1.0)
    s = _run_with_forced_entry(monkeypatch, df, entry_bar=40)
    assert s.losses == 1 and s.wins == 0 and s.scratches == 0
    assert s.trades[0].r_multiple == pytest.approx(-1.0, abs=0.01)


def test_timeout_is_marked_to_market_and_in_expectancy(monkeypatch):
    # Entry at 100 (bar 40), then price steps down to 99.8 and stays there.
    # Post-entry highs are 99.8+0.5=100.3 < trigger 100.35, lows 99.3 > stop 98,
    # target never reached -> 2w horizon times out after 14 bars, marked to
    # market at 99.8 (a -0.2% / -0.1R "invisible" trade the old engine dropped).
    closes = np.concatenate([np.full(41, 100.0), np.full(19, 99.8)])
    df = make_ohlcv(closes, spread_pct=1.0)
    s = _run_with_forced_entry(monkeypatch, df, entry_bar=40)
    assert s.timeouts == 1 and s.wins == 0 and s.losses == 0
    t = s.trades[0]
    assert t.outcome == "timeout"
    assert t.exit_price is not None and t.return_pct is not None
    assert t.r_multiple < 0              # drifted down -> negative
    assert s.expectancy_r is not None and s.expectancy_r < 0
    assert s.win_rate is None


def test_v2_stop_entry_that_never_triggers_is_silently_dropped(monkeypatch):
    """Task 30 prereq regression: backtest.py's v2 branch must call
    plan_engine.entry_type_for(strategy, "strategy") instead of hardcoding
    entry_type="market" (Task 30's TRAIN grid monkeypatches
    STRATEGY_ENTRY_TYPE for breakout-class strategies and expects this to
    actually route through stop_entry fill logic). Once entry_type can be
    "stop_entry", simulate_exit can return outcome="not_triggered"
    (exit_index=None, legs=[]) for a signal whose trigger never touches
    within the expiry window -- backtest.py must not crash on that (no
    exit_index to subtract, no legs[-1] to index) and must not count it as
    a trade; it simply never happened.

    Flat at 100 through the signal bar (entry=100, 2w ATR-stop ~98 via the
    same flat/spread-1% setup as the sibling tests above); then bars
    entry_bar+1..+5 (the stop_entry's expiry_bars=5 window, hardcoded in
    backtest.py's v2 branch) drop to 99 -- high=99.495 stays below the
    bullish trigger_price of 100 (never triggers) and close=99 stays above
    the 98 stop (never invalidates either) -- so the plan expires pending,
    genuinely never entering a trade.
    """
    import swingbot.core.plan_engine as plan_engine
    closes = np.full(60, 100.0)
    closes[41:46] = 99.0
    df = make_ohlcv(closes, spread_pct=1.0)
    monkeypatch.setitem(plan_engine.STRATEGY_ENTRY_TYPE, "EMA Crossover", "stop_entry")
    s = _run_with_forced_entry(monkeypatch, df, entry_bar=40, exit_model="v2", scale_out=False)
    assert s.trades == []
    assert s.wins == s.losses == s.scratches == s.timeouts == 0


def test_vectorized_entries_delegates_to_entry_filters(market_df):
    """backtest must produce byte-identical entries to entry_filters for
    every strategy -- no drift, that is the whole point of the redesign."""
    from swingbot.core.backtest import _vectorized_entries, ALL_STRATEGIES
    from swingbot.core.entry_filters import entries_for
    for strat in ALL_STRATEGIES:
        b1, s1 = _vectorized_entries(market_df, strat, "4w")
        b2, s2 = entries_for(strat, market_df, "4w")
        assert b1.equals(b2) and s1.equals(s2), strat


# tests/test_backtest_engine.py (append)
import pytest
from pathlib import Path
import pandas as pd
from swingbot.core.backtest import run_backtest
import swingbot.core.entry_filters as ef

CACHE = Path(__file__).resolve().parent.parent / "data" / "backtest_cache"

# NOTE: MACD/4w produces zero raw entry signals on every cached ticker checked
# on this branch (AAPL, MSFT, TSLA, NVDA, AMD, AMZN) -- a pre-existing
# entry-filter gating condition unrelated to this task -- so these golden
# fixtures use TSLA/Elliott Wave/4w, which produces a real win/loss/scratch mix.
@pytest.mark.skipif(not CACHE.is_dir(), reason="no OHLCV cache")
def test_v2_single_leg_reproduces_v1_exactly():
    df = pd.read_csv(CACHE / "TSLA.csv", index_col="Date", parse_dates=True)
    v1 = run_backtest("TSLA", df, "Elliott Wave", "4w")
    v2 = run_backtest("TSLA", df, "Elliott Wave", "4w", exit_model="v2", scale_out=False)
    assert (v1.wins, v1.losses, v1.scratches, v1.timeouts) == \
           (v2.wins, v2.losses, v2.scratches, v2.timeouts)
    assert v2.expectancy_r == pytest.approx(v1.expectancy_r, abs=1e-9)

@pytest.mark.skipif(not CACHE.is_dir(), reason="no OHLCV cache")
def test_v2_scale_out_keeps_classification_and_expectancy():
    # Pinned to the window these golden fixtures were authored against
    # (the original 2018-06..2025-12 cache span). The classification-parity
    # invariant below assumes a runner's longer hold never shifts which later
    # signals get taken; that holds here, but over deep history a v2 scale-out
    # runner can occupy the one_at_a_time slot and legitimately drop one later
    # entry v1 took (the "composition, not divergence" effect documented in
    # docs/superpowers/results/2026-07-exit-v2-validation.md). Slicing keeps
    # the test deterministic regardless of how far the cache now extends.
    df = pd.read_csv(CACHE / "TSLA.csv", index_col="Date", parse_dates=True)
    df = df.loc["2018-06-01":"2025-12-31"]
    v1 = run_backtest("TSLA", df, "Elliott Wave", "4w")
    v2 = run_backtest("TSLA", df, "Elliott Wave", "4w", exit_model="v2", scale_out=True)
    # TP1 unchanged => identical win/loss/scratch classification
    assert (v1.wins, v1.losses, v1.scratches) == (v2.wins, v2.losses, v2.scratches)
    # runner sub-outcomes partition the wins
    assert v2.runner_tp2 + v2.runner_trail + v2.runner_be + v2.runner_timeout == v2.wins
    # runner floor is BE => expectancy can only drop by rounding noise
    assert v2.expectancy_r >= v1.expectancy_r - 0.02

@pytest.mark.skipif(not CACHE.is_dir(), reason="no OHLCV cache")
def test_v2_scale_out_return_pct_matches_r_multiple_not_just_runner_leg():
    # Regression pin (code review finding): return_pct must be derived from
    # the blended r_multiple, not from legs[-1]'s exit price alone -- a
    # multi-leg scale-out win's return spans both legs, and computing it
    # from only the runner leg's price silently drops the TP1 leg entirely
    # (e.g. a runner_be win, where the runner leg's exit price equals the
    # entry price, was reported as a flat 0.0% return despite a real,
    # positive-R win).
    #
    # This pin needs a specific fixture shape (a runner_be win on TSLA under
    # "Elliott Wave"/4w) that predates the rescue's strict wave-2 gate
    # (2026-07 rescue plan, Task 105); that gate's TRAIN-adopted defaults
    # suppress the exact trade this regression relies on. The gate's
    # correctness is covered by tests/test_rescue_elliott.py -- this test is
    # about return_pct arithmetic, not Elliott Wave signal quality -- so the
    # gate is pinned off here to keep exercising the original known-good
    # fixture regardless of future strategy tuning.
    baseline = dict(ef.DEFAULT_PARAMS["Elliott Wave"])
    ef.DEFAULT_PARAMS["Elliott Wave"].update(
        {"w2_min_retrace": None, "w2_max_retrace": None, "w2_max_duration_ratio": None})
    try:
        df = pd.read_csv(CACHE / "TSLA.csv", index_col="Date", parse_dates=True)
        v2 = run_backtest("TSLA", df, "Elliott Wave", "4w", exit_model="v2", scale_out=True)
    finally:
        ef.DEFAULT_PARAMS["Elliott Wave"] = baseline
    for t in v2.trades:
        if t.outcome != "win":
            continue
        risk_per_share = abs(t.entry - t.stop_loss)
        implied_return_pct = round(t.r_multiple * (risk_per_share / t.entry) * 100, 3)
        assert t.return_pct == pytest.approx(implied_return_pct)
    # At least one runner_be win must exist in this fixture and must show a
    # nonzero return_pct (the exact case the bug reported as 0.0%).
    be_wins = [t for t in v2.trades if t.outcome == "win" and t.r_multiple < 0.5]
    assert be_wins and all(t.return_pct != 0.0 for t in be_wins)

@pytest.mark.skipif(not CACHE.is_dir(), reason="no OHLCV cache")
def test_v2_scale_out_stamps_per_trade_runner_outcome():
    # Regression pin: scripts/run_backtest_range.py's runner_by_strategy
    # table must be built from a per-trade field so it can be filtered to
    # the --from/--to date window (via window_trades()), unlike the
    # unfiltered run-level BacktestSummary.runner_tp2/trail/be/timeout
    # aggregates it used to read. That per-trade field is
    # BacktestTrade.runner_outcome, stamped on the v2/scale-out branch of
    # run_backtest from res.runner_outcome. Before this fix, BacktestTrade
    # had no such field at all, so this attribute wouldn't have existed --
    # any harness code trying to sum it per-window would have failed
    # (or, pre-fix, the harness read s.runner_tp2 etc. straight off the
    # unfiltered summary and could never have been scoped to a window no
    # matter what it did to `tr`).
    df = pd.read_csv(CACHE / "TSLA.csv", index_col="Date", parse_dates=True)
    v2 = run_backtest("TSLA", df, "Elliott Wave", "4w", exit_model="v2", scale_out=True)
    assert v2.wins > 0  # otherwise this test can't exercise anything
    for t in v2.trades:
        if t.outcome == "win":
            assert t.runner_outcome in (
                "runner_tp2", "runner_trail", "runner_be", "runner_timeout"
            ), t
        else:
            assert t.runner_outcome is None, t
    # Cross-check: the per-trade partition of wins must reproduce the exact
    # same counts as the run-level aggregate (they describe the same run,
    # just at different granularity) -- this is the invariant the harness
    # fix depends on being true.
    per_trade_counts = {
        "runner_tp2": 0, "runner_trail": 0, "runner_be": 0, "runner_timeout": 0,
    }
    for t in v2.trades:
        if t.runner_outcome:
            per_trade_counts[t.runner_outcome] += 1
    assert per_trade_counts == {
        "runner_tp2": v2.runner_tp2,
        "runner_trail": v2.runner_trail,
        "runner_be": v2.runner_be,
        "runner_timeout": v2.runner_timeout,
    }
