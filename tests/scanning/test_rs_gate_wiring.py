"""v34 Task 6: applying the RS gate (rs_verdict, Task 4) as a pre-scenario
filter in the scan loop, behind config.RS_GATE (default off).

Driven through the real _sync_run_scan pipeline -- same recipe as
test_mtf_gate.py (itself borrowed from test_engine_v2_plans.py /
test_engine_quality_inputs.py): monkeypatch load_watchlist/get_current_price/
trade_log/is_stop_requested plus dedup_scan_items to capture the real
ScanItems pre-alert-build (chart rendering etc. is irrelevant to the gate
under test and would make this slow and non-hermetic).

engine._apply_sector_rs is monkeypatched (rather than driving the real
sector-ETF-fetch plumbing already covered by test_sector_rs.py) to set
item.rs_percentile/item.rs_combined directly from the `rs`/`sector_rs`
params under test -- this proves the gate reads item.rs_combined (falling
back to the bare ticker RS only when no sector reading exists), not a
reimplementation of the sector-combine math itself.
"""
import json
import os

import numpy as np
import pytest

import swingbot.config as config
from swingbot.core.edge.factors import rs_score
from swingbot.core.scanning import engine
from swingbot.core.scanning.engine import ScanProgress
from swingbot.core.tracking.performance import TradeLog
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path, monkeypatch):
    """Same isolation as test_mtf_gate.py's fixture of the same name --
    _sync_run_scan reads account config and writes scan telemetry, both of
    which must not touch the real data/."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    (tmp_path / "trades.json").write_text("[]", encoding="utf-8")
    (tmp_path / "plans.json").write_text("[]", encoding="utf-8")
    (tmp_path / "account.json").write_text(json.dumps({
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    }), encoding="utf-8")


def _structured_df(trend_len=120, box_len=60, seed=7):
    """Trend then consolidation box -- same recipe as test_mtf_gate.py's
    _structured_df(), verified empirically to produce a real bullish AND
    bearish scenario at trend_len=120/box_len=60."""
    rng = np.random.RandomState(seed)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, trend_len)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(box_len)]
    return make_ohlcv(trend + box)


def _scan_with_funnel(ticker, direction, rs, sector_rs=None, horizon="4w"):
    """Run one real _sync_run_scan pass for a single ticker/horizon.

    Returns (items, funnel): `items` are the captured ScanItems (pre-
    alert-build) whose scenario direction matches `direction`; `funnel` is
    the scan's progress.funnel dict.

    `rs`/`sector_rs` control what the (monkeypatched) _apply_sector_rs sets
    on every item: item.rs_percentile = rs, and item.rs_combined is the real
    rs_score(rs, sector_rs) blend when sector_rs is given, else falls back
    to rs alone -- exactly the "no sector reading" contract Task 5 defined.
    """
    df = _structured_df()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "MIN_REWARD_PCT", 0.5)
        mp.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
        mp.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
        # NOT 0.0 -- see test_engine_v2_plans.py's identical comment:
        # select_structural_target treats min_rr<=0 as "reject everything".
        mp.setattr(config, "MIN_RISK_REWARD_RATIO", 0.01)
        mp.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 1)
        mp.setattr(config, "PLAN_ENGINE_V2", "shadow")
        mp.setitem(engine.HORIZONS[horizon], "sr_target_min_pct", 1.0)

        mp.setattr(engine, "load_watchlist", lambda: [ticker])
        mp.setattr(
            engine, "get_daily_data",
            lambda t, period=None: df.copy() if t == ticker else None,
        )
        mp.setattr(engine, "get_current_price", lambda t: None)
        mp.setattr(engine, "trade_log",
                   TradeLog(path=os.path.join(config.DATA_DIR, "trades.json")))
        mp.setattr(engine, "is_stop_requested", lambda: False)

        def _fake_apply_sector_rs(item, tk, sector_of_ticker,
                                   etf_symbol_of_sector, sector_etf_frames,
                                   spy_df):
            item.rs_percentile = rs
            if sector_rs is not None:
                item.sector_rs_percentile = sector_rs
                item.rs_combined = rs_score(rs, sector_rs)
            else:
                item.sector_rs_percentile = None
                item.rs_combined = rs

        mp.setattr(engine, "_apply_sector_rs", _fake_apply_sector_rs)

        captured = {}

        def _capture_and_shortcircuit(items):
            captured["items"] = list(items)
            return []   # skip the alert-building loop -- irrelevant to the gate

        mp.setattr(engine, "dedup_scan_items", _capture_and_shortcircuit)

        progress = ScanProgress()
        engine._sync_run_scan(horizon, require_confirmation=False,
                               progress=progress, min_confluence=0)

    items = [item for item in captured.get("items", [])
             if item.result.trend == direction]
    return items, progress.funnel


def _scan_with(ticker, direction, rs, sector_rs=None, horizon="4w"):
    items, _funnel = _scan_with_funnel(ticker, direction, rs, sector_rs, horizon)
    return items


def test_gate_off_by_default(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", False)
    assert len(_scan_with(ticker="AAPL", direction="bullish", rs=10.0)) == 1


def test_gate_on_blocks_a_bullish_laggard(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", True)
    assert _scan_with(ticker="AAPL", direction="bullish", rs=10.0) == []


def test_gate_on_never_blocks_an_exempt_symbol(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", True)
    assert len(_scan_with(ticker="GC=F", direction="bullish", rs=10.0)) == 1


def test_gate_uses_combined_rs_not_bare_ticker_rs(monkeypatch):
    """rs_combined is 0.7*ticker + 0.3*sector. A ticker at 65 in a sector at
    20 combines to 51.5 and must be blocked at a 60 leader threshold."""
    monkeypatch.setattr(config, "RS_GATE", True)
    monkeypatch.setattr(config, "RS_LEADER_PERCENTILE", 60.0)
    assert _scan_with(ticker="AAPL", direction="bullish",
                      rs=65.0, sector_rs=20.0) == []


def test_blocked_scenarios_increment_the_funnel_counter(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", True)
    _items, funnel = _scan_with_funnel(ticker="AAPL", direction="bullish", rs=10.0)
    assert funnel["rs_blocked"] == 1
