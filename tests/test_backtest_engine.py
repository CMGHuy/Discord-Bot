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
