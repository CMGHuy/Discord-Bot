"""G91: backtest hook -- checklist per simulated signal.

NOTE on adapting the plan's illustrative test: the plan's own pseudocode used
uptrend_daily() with strategy="Break & Retest" and horizon_key="swing" and
expected trades to fall out "naturally." Neither holds against the real
code: "swing" is not a HORIZONS key (real keys are 2w/4w/2m/.../9m per
strategy_types.HORIZONS), and Break & Retest requires an actual volume
breakout + retest pattern that a pure exponential uptrend never produces
(confirmed empirically). This file instead reuses this repo's own
established idiom for deterministic backtest tests
(tests/test_backtest_engine.py's `_run_with_forced_entry`): monkeypatch
`backtest._vectorized_entries` to force exactly one signal bar. It also
accesses trade fields as dataclass attributes (`t.gate_score`) rather than
dict subscription, since BacktestTrade is a dataclass, not a dict --
`result.trades` returns the real dataclass instances; `result.to_dict()`
(added by this task) is what serializes them to dicts for the
byte-identical comparison.
"""
import json

import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv


def _run_with_forced_entry(monkeypatch, df, entry_bar, direction="bullish",
                           strategy="Break & Retest", horizon="2w", **kwargs):
    import swingbot.core.backtest as bt
    bull = pd.Series(False, index=df.index)
    bear = pd.Series(False, index=df.index)
    (bull if direction == "bullish" else bear).iloc[entry_bar] = True
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *a, **k: (bull, bear))
    return bt.run_backtest("TEST", df, strategy, horizon, **kwargs)


def _fixture_df():
    closes = np.full(60, 100.0)
    closes[41:] = 101.0                  # bar e+1 jumps: a clean win, one trade
    return make_ohlcv(closes, spread_pct=1.0)


def test_gate_eval_annotates_trades(monkeypatch):
    import swingbot.core.gate.backtest_ctx as bctx
    monkeypatch.setattr(bctx, "historical_macro_snap",
                        lambda as_of: {"built_at": f"{as_of}T21:00:00+00:00",
                                       "stale": False, "events": {
                                           "next_high_impact": None,
                                           "within_24h": [], "today": []}})
    df = _fixture_df()
    summary = _run_with_forced_entry(monkeypatch, df, entry_bar=40, gate_eval=True)
    trades = summary.trades
    assert trades, "fixture must produce at least one simulated trade"
    for t in trades:
        assert t.gate_score is not None
        assert t.gate_tier is not None
        assert isinstance(t.fired_flags, list)


def test_gate_eval_off_is_byte_identical(monkeypatch):
    df = _fixture_df()
    baseline = _run_with_forced_entry(monkeypatch, df, entry_bar=40)
    again = _run_with_forced_entry(monkeypatch, df, entry_bar=40, gate_eval=False)
    baseline_json = json.dumps(baseline.to_dict(), sort_keys=True, default=str)
    again_json = json.dumps(again.to_dict(), sort_keys=True, default=str)
    assert baseline_json == again_json
