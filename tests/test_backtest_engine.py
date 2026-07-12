import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv


def _run_with_forced_entry(monkeypatch, df, entry_bar, direction="bullish",
                           strategy="EMA Crossover", horizon="2w"):
    import swingbot.core.backtest as bt
    bull = pd.Series(False, index=df.index)
    bear = pd.Series(False, index=df.index)
    (bull if direction == "bullish" else bear).iloc[entry_bar] = True
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *a, **k: (bull, bear))
    return bt.run_backtest("TEST", df, strategy, horizon)


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
    df = pd.read_csv(CACHE / "TSLA.csv", index_col="Date", parse_dates=True)
    v1 = run_backtest("TSLA", df, "Elliott Wave", "4w")
    v2 = run_backtest("TSLA", df, "Elliott Wave", "4w", exit_model="v2", scale_out=True)
    # TP1 unchanged => identical win/loss/scratch classification
    assert (v1.wins, v1.losses, v1.scratches) == (v2.wins, v2.losses, v2.scratches)
    # runner sub-outcomes partition the wins
    assert v2.runner_tp2 + v2.runner_trail + v2.runner_be + v2.runner_timeout == v2.wins
    # runner floor is BE => expectancy can only drop by rounding noise
    assert v2.expectancy_r >= v1.expectancy_r - 0.02
