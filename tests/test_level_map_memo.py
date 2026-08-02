"""The opt-in level-map memo (plan v8 V17).

What is actually at risk here is a *silent* change to backtest results: the
memo short-circuits `build_level_map`, which prices TP2 on every exit-v2
trade. So the tests that matter are (a) it is off unless asked for, and (b)
when on, the trades it produces are identical to the ones the same run
produces without it -- not "close", identical.
"""
import numpy as np
import pandas as pd
import pytest

import swingbot.core.backtest as bt
from tests.conftest import make_ohlcv


@pytest.fixture(autouse=True)
def _memo_off_after_each():
    yield
    bt.disable_level_map_memo()


def _trending_df(n=320):
    # A rising series with pullbacks, so the trendline scanner finds real
    # volume-confirmed pivots and build_level_map returns non-empty levels --
    # a flat series would make the memo trivially correct on empty results.
    x = np.arange(n)
    closes = 100 + x * 0.25 + 6 * np.sin(x / 9.0)
    return make_ohlcv(closes, spread_pct=1.5)


def _run(df, entry_bar, monkeypatch):
    bull = pd.Series(False, index=df.index)
    bear = pd.Series(False, index=df.index)
    bull.iloc[entry_bar] = True
    bull.iloc[entry_bar + 40] = True
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *a, **k: (bull, bear))
    return bt.run_backtest("TEST", df, "MACD", "2w", exit_model="v2",
                           scale_out=True, tp2_mode="levels")


def _fingerprint(summary):
    return [(t.entry_date, t.entry, t.exit_price, t.outcome, t.r_multiple)
            for t in summary.trades]


def test_memo_is_off_by_default():
    assert bt.level_map_memo_stats() == {"enabled": False, "size": 0}


def test_enabling_is_idempotent_and_disable_releases():
    bt.enable_level_map_memo()
    bt.enable_level_map_memo()
    assert bt.level_map_memo_stats()["enabled"] is True
    bt.disable_level_map_memo()
    bt.disable_level_map_memo()          # must not raise when already off
    assert bt.level_map_memo_stats()["enabled"] is False


def test_clear_is_safe_when_disabled():
    bt.clear_level_map_memo()            # no-op, must not raise
    assert bt.level_map_memo_stats()["size"] == 0


def test_memoized_run_is_identical_to_unmemoized(monkeypatch):
    df = _trending_df()
    cold = _fingerprint(_run(df, 200, monkeypatch))
    assert cold, "fixture produced no trades -- the memo would be untested"

    bt.enable_level_map_memo()
    first = _fingerprint(_run(df, 200, monkeypatch))
    assert bt.level_map_memo_stats()["size"] > 0, "nothing was memoized"
    warm = _fingerprint(_run(df, 200, monkeypatch))

    assert first == cold
    assert warm == cold


def test_memo_does_not_grow_across_repeat_runs(monkeypatch):
    """A second identical run must hit, not re-store under a new key --
    otherwise a 108-config grid holds 108 copies of the same level map."""
    df = _trending_df()
    bt.enable_level_map_memo()
    _run(df, 200, monkeypatch)
    size_after_first = bt.level_map_memo_stats()["size"]
    _run(df, 200, monkeypatch)
    assert bt.level_map_memo_stats()["size"] == size_after_first


def test_clear_leaves_the_memo_enabled(monkeypatch):
    df = _trending_df()
    bt.enable_level_map_memo()
    _run(df, 200, monkeypatch)
    assert bt.level_map_memo_stats()["size"] > 0
    bt.clear_level_map_memo()
    stats = bt.level_map_memo_stats()
    assert stats["enabled"] is True and stats["size"] == 0
