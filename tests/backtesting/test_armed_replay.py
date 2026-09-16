import dataclasses

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting import armed_replay as ar
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market import levels, reaction as rx
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv

L, T1 = 98.5, 106.0
CELL = ar.Cell("M1", 5, 0.25, 0.10)


def _params(**kw):
    base = dict(min_reward_pct=3.0, min_stop_distance_pct=2.0, max_stop_loss_pct=7.0,
                min_target_confluence_count=2, min_risk_reward_ratio=1.5,
                max_risk_reward_ratio=2.5)
    base.update(kw)
    return dataclasses.replace(ScanParams.from_config(), **base)


def _scenario(direction="bullish", entry=100.0, stop=L, target=T1):
    return levels.Scenario(
        direction=direction, entry=entry, market_price=entry, stop_loss=stop,
        stop_sources=["Rolling S/R"], stop_distance_pct=abs(entry - stop) / entry * 100,
        tight_stop=False, atr_floor_pct=0.0, take_profit=target,
        target_distance_pct=abs(target - entry) / entry * 100,
        target_sources=["Fibonacci"], target2_price=None, target2_distance_pct=None,
        target2_sources=None)


def _cand(index=25, direction="bullish", level=L, target=T1):
    return ar.ArmCandidate(index, direction, level, target,
                           _scenario(direction, stop=level, target=target))


def _frame(overrides, n=30):
    """Flat 100 closes (high 101 / low 99, well clear of L=98.5 at k=0.25),
    with (open, high, low, close) overrides by bar index."""
    rows = [(100.0, 101.0, 99.0, 100.0)] * n
    for idx, row in overrides.items():
        rows[idx] = row
    return make_ohlcv(rows)


def _walk(df, cand=None, cell=CELL):
    return ar.walk_arm(rx.Bars.from_frame(df), np.full(len(df), 1.0), cand or _cand(), cell)


def test_cell_id_format():
    assert ar.Cell("M2", 10, 0.5, 0.25).cell_id == "M2-N10-k0.50-b0.25"


def test_walk_confirms_a_rejection_and_records_the_first_test():
    out = _walk(_frame({27: (99.0, 99.6, 97.6, 99.4)}))
    assert out == ar.ArmOutcome("confirmed", 27, rx.R1, 27)


def test_walk_expires_when_nothing_tests_the_level():
    # arm at 25 with N=5 expires at bar 30, which must exist: 31 bars
    assert _walk(_frame({}, n=31)) == ar.ArmOutcome("expired", 30)


def test_walk_cancels_when_the_target_trades_first():
    out = _walk(_frame({26: (100.0, 106.5, 99.5, 105.0), 27: (99.0, 99.6, 97.6, 99.4)}))
    assert out == ar.ArmOutcome("cancelled_target", 26)


def test_target_reached_on_the_arm_bar_itself_is_ignored():
    out = _walk(_frame({25: (100.0, 106.5, 99.5, 100.0), 27: (99.0, 99.6, 97.6, 99.4)}))
    assert out.status == "confirmed" and out.resolved_index == 27


def test_walk_cancels_a_close_through_that_is_not_reclaimed():
    out = _walk(_frame({26: (98.6, 98.7, 97.9, 98.0),
                        27: (98.0, 98.1, 97.4, 97.5),
                        28: (97.5, 97.6, 96.9, 97.0)}))
    assert out == ar.ArmOutcome("cancelled_closed_through", 28)


def test_walk_is_unresolved_when_the_window_runs_off_the_frame():
    assert _walk(_frame({}, n=28)) == ar.ArmOutcome("unresolved", None)


def test_walk_bearish_mirror_confirms():
    cand = _cand(direction="bearish", level=101.5, target=94.0)
    out = _walk(_frame({27: (101.0, 102.4, 100.4, 100.6)}), cand=cand)
    assert out == ar.ArmOutcome("confirmed", 27, rx.R1, 27)


def test_arm_candidates_widen_past_the_min_stop_gate(monkeypatch):
    """Spec §3.1's widening: a 1.5% stop is refused by today's replay and
    arms here."""
    supports, resistances = [levels.Level(L, ["Rolling S/R"])], [levels.Level(T1, ["Fibonacci"])]
    monkeypatch.setattr(ar, "levels_asof", lambda *a, **k: (supports, resistances))
    monkeypatch.setattr(bs, "levels_asof", lambda *a, **k: (supports, resistances))
    monkeypatch.setattr(levels, "count_confirming_strategies", lambda *a, **k: (3, ["x", "y", "z"]))
    df = make_ohlcv([100.0] * 60)
    params = _params()
    baseline = bs.replay_scenarios("AAPL", df, "4w", params=params)
    assert [p for _, p in baseline if p.direction == "bullish"] == []
    cands = ar.arm_candidates("AAPL", df, "4w", params=params)
    bullish = [c for bar in cands.values() for c in bar if c.direction == "bullish"]
    assert bullish and all(c.level == L and c.target == T1 for c in bullish)
    assert min(cands) == 45          # MIN_BARS["4w"]
