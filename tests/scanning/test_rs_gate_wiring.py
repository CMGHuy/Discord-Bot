"""v34 Task 6: applying the RS gate (rs_verdict, Task 4) as a pre-scenario
filter in the scan loop, behind config.RS_GATE -- default ON since v34 Task 8's
VALIDATION PASS. Every test here pins the flag with monkeypatch rather than
relying on that default, which is why flipping it changed nothing below.

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
from swingbot.core.scanning import engine, fetch, runstate
from swingbot.core.scanning.engine import ScanProgress
from swingbot.core.tracking.performance import TradeLog
from tests.helpers import make_ohlcv
from tests.scanning.conftest import _InlineProcessPool


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
            fetch, "get_daily_data",
            lambda t, period=None: df.copy() if t == ticker else None,
        )
        # v55: force the batched live-price/cold-fetch path to resolve empty
        # -- same "no live price -> falls back to the daily close" behavior
        # the old get_current_price->None mock gave, without a real batch
        # call hitting real network through a real ProcessPoolExecutor.
        mp.setattr(fetch, "get_daily_data_batch", lambda tickers, period=None: {})
        mp.setattr(fetch, "get_current_price_batch", lambda tickers: {})
        mp.setattr(fetch, "ProcessPoolExecutor", _InlineProcessPool)
        mp.setattr(engine, "trade_log",
                   TradeLog(path=os.path.join(config.DATA_DIR, "trades.json")))
        mp.setattr(runstate, "is_stop_requested", lambda: False)

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


def test_gate_switched_off_blocks_nothing(monkeypatch):
    """RS_GATE=false is a full bypass, not a softer gate.

    This used to be named test_gate_off_by_default. RS_GATE now ships
    `default="true"` (v34 Task 8's VALIDATION PASS), so the name would have
    asserted a default that is no longer the shipped one -- while the test
    itself pins the flag explicitly and never read the default at all.
    """
    monkeypatch.setattr(config, "RS_GATE", False)
    assert len(_scan_with(ticker="AAPL", direction="bullish", rs=10.0)) == 1


def test_gate_on_blocks_a_bullish_laggard(monkeypatch):
    """The bullish half of the gate still works when it is switched on.

    RS_LEADER_PERCENTILE is pinned rather than left at its default because
    v34's TRAIN sweep froze that default at 0 (= bullish arm disabled; see
    docs/superpowers/plans/implemented/v34-train-preregistration.md, Step 2).
    This test is about the WIRING -- a block drops the scenario -- not about
    the shipped default, which test_frozen_defaults_do_not_gate_bullish covers.
    """
    monkeypatch.setattr(config, "RS_GATE", True)
    monkeypatch.setattr(config, "RS_LEADER_PERCENTILE", 60.0)
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
    monkeypatch.setattr(config, "RS_LEADER_PERCENTILE", 60.0)   # see above
    _items, funnel = _scan_with_funnel(ticker="AAPL", direction="bullish", rs=10.0)
    assert funnel["rs_blocked"] == 1


def _declared_default(key):
    """The Field's DECLARED default, not the runtime global.

    config.<ATTR> is whatever this machine's .env resolved to, so asserting
    it would make the two guards below fail for an environmental reason
    rather than a real regression. The frozen constant is the Field
    default, so that is what gets guarded -- and then pinned onto the
    runtime globals so the behavioural half of each test exercises it."""
    return next(f for f in config.FIELDS if f.key == key).default


def test_frozen_defaults_do_not_gate_bullish(monkeypatch):
    """v34 TRAIN froze RS_LEADER_PERCENTILE at 0, which disables the bullish
    half of the gate (a percentile is never negative, so `rs >= 0` always
    holds). A bullish setup at the 10th percentile therefore SURVIVES with
    the gate on -- the TRAIN sweep found a bullish gate negative at every
    threshold it measured. Guards the frozen default itself, so a silent
    change to it fails a test rather than quietly re-enabling an arm that
    was measured to hurt."""
    assert _declared_default("RS_LEADER_PERCENTILE") == "0"
    monkeypatch.setattr(config, "RS_GATE", True)
    monkeypatch.setattr(config, "RS_LEADER_PERCENTILE", 0.0)
    assert len(_scan_with(ticker="AAPL", direction="bullish", rs=10.0)) == 1


def test_frozen_defaults_gate_a_bearish_non_laggard(monkeypatch):
    """The other half of the frozen shape: RS_LAGGARD_PERCENTILE = 25, so a
    bearish setup at the 40th percentile is not a laggard and is dropped,
    while one at the 10th is kept."""
    assert _declared_default("RS_LAGGARD_PERCENTILE") == "25"
    monkeypatch.setattr(config, "RS_GATE", True)
    monkeypatch.setattr(config, "RS_LAGGARD_PERCENTILE", 25.0)
    assert _scan_with(ticker="AAPL", direction="bearish", rs=40.0) == []
    assert len(_scan_with(ticker="AAPL", direction="bearish", rs=10.0)) == 1
