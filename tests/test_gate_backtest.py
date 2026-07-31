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


# ---------------------------------------------------------------------------
# G92: gate-filtered replay mode.
#
# NOTE on adapting the plan's illustrative test: the plan's version drove the
# tier split off a single `_run(gate_eval=True)` call's REAL gate scores and
# asserted keep/skip via dict-subscript trade["gate_tier"]/trade["entry_date"].
# BacktestTrade is a dataclass (see the G91 note above), so this uses
# attribute access. More importantly, this repo has no simple synthetic
# fixture that reliably produces signals landing across all four tiers (A+
# through C) from the real checklist -- that would require reverse-engineering
# which checks pass/warn/fail against a hand-built OHLCV frame, which is a
# calibration exercise, not what G92 is testing. G92's own deliverable is the
# *filtering plumbing* (kept iff tier clears the bar, hard-blocks always
# excluded) -- so this monkeypatches backtest._gate_annotation directly to
# return a controlled, per-signal tier and asserts the plumbing routes each
# signal to `trades` or `skipped_by_gate` correctly. G91's own test already
# covers that real gate scores flow into the annotation.
# ---------------------------------------------------------------------------

from swingbot.core.backtest import assert_train_only


def test_filtered_run_drops_exactly_subtier(monkeypatch):
    import swingbot.core.backtest as bt

    df = _fixture_df()
    entry_bars = (20, 25, 30, 35)
    tier_by_bar = {20: "A+", 25: "A", 30: "B", 35: "C"}
    bull = pd.Series(False, index=df.index)
    for b in entry_bars:
        bull.iloc[b] = True
    bear = pd.Series(False, index=df.index)
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *a, **k: (bull, bear))

    def _fake_annotation(gate_eval, ticker, strategy, horizon_key, df, i, direction,
                         entry, stop_loss, take_profit, spy_df=None):
        if not gate_eval:
            return None, None, [], False
        return 80.0, tier_by_bar[i], [], False
    monkeypatch.setattr(bt, "_gate_annotation", _fake_annotation)

    summary = bt.run_backtest("TEST", df, "Break & Retest", "2w",
                              one_at_a_time=False, gate_eval=True, gate_min_tier="A")

    assert len(summary.trades) + len(summary.skipped_by_gate) == len(entry_bars)
    for t in summary.trades:
        assert t.gate_tier in ("A+", "A")
        assert t.skipped_by_gate is False
    for t in summary.skipped_by_gate:
        assert t.gate_tier in ("B", "C")
        assert t.skipped_by_gate is True


def test_gate_min_tier_requires_gate_eval():
    import swingbot.core.backtest as bt
    df = _fixture_df()
    with pytest.raises(ValueError, match="gate_eval"):
        bt.run_backtest("TEST", df, "Break & Retest", "2w", gate_min_tier="A")


def test_validation_window_raises():
    df_2024 = make_ohlcv(np.full(60, 100.0), start="2024-03-01")
    with pytest.raises(ValueError, match="validation"):
        assert_train_only(df_2024)
    assert_train_only(make_ohlcv(np.full(60, 100.0), start="2022-01-03"))  # no raise
