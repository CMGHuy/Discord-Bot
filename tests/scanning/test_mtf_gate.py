"""v33 Task 4: the adjacent-horizon hard gate (MTF_ADJACENT_GATE).

Driven through the real _sync_run_scan pipeline -- same recipe as
test_engine_v2_plans.py / test_engine_quality_inputs.py: monkeypatch
load_watchlist/get_current_price/trade_log/is_stop_requested plus
dedup_scan_items to capture the real ScanItems pre-alert-build (chart
rendering etc. is irrelevant to the gate under test and would make this
slow and non-hermetic).

engine.adjacent_aligned itself is monkeypatched (rather than hand-built
EMA-crossover data for a *second* horizon) to report a controlled
"aligned"/"opposed" verdict for the scenario direction under test, so the
test proves the gate's placement/behavior inside _scan_one/_sync_run_scan,
not a reimplementation of adjacent_aligned's own logic (already covered by
tests/market/test_mtf.py from Task 3).

The fixture reliably produces scenarios in BOTH directions for most
horizons (see _structured_df) -- _scan_with/_scan_with_funnel filter the
captured items down to the `direction` under test, so the untouched
opposite-direction scenario (always mocked "aligned" so it can never
interfere) never pollutes the assertion.
"""
import json
import os

import numpy as np
import pytest

import swingbot.config as config
from swingbot.core.scanning import analyze, dedup, engine, fetch, runstate
from swingbot.core.scanning.engine import ScanProgress
from swingbot.core.tracking.performance import TradeLog
from tests.helpers import make_ohlcv
from tests.scanning.conftest import _InlineProcessPool

_UNSET = object()


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path, monkeypatch):
    """Same isolation as test_engine_v2_plans.py's fixture of the same name
    -- _sync_run_scan reads account config and writes scan telemetry, both
    of which must not touch the real data/."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    (tmp_path / "trades.json").write_text("[]", encoding="utf-8")
    (tmp_path / "plans.json").write_text("[]", encoding="utf-8")
    (tmp_path / "account.json").write_text(json.dumps({
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    }), encoding="utf-8")


def _structured_df(trend_len=120, box_len=60, seed=7):
    """Trend then consolidation box -- same recipe as
    test_engine_v2_plans.py's _structured_df(), parameterized on length so
    the 9m case (MIN_BARS["9m"] == 390) can ask for enough bars. Verified
    empirically (not just by inspection) to produce a real bullish AND
    bearish scenario at trend_len=120/box_len=60 (used for every horizon
    except 9m), and exactly one bullish scenario (no bearish) at
    trend_len=300/box_len=90 (used for the 9m exemption test)."""
    rng = np.random.RandomState(seed)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, trend_len)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(box_len)]
    return make_ohlcv(trend + box)


def _scan_with_funnel(direction, next_horizon_trend=_UNSET, horizon="4w"):
    """Run one real _sync_run_scan pass for a single ticker/horizon.

    Returns (items, funnel): `items` are the captured ScanItems (pre-
    alert-build) whose scenario direction matches `direction`; `funnel` is
    the scan's progress.funnel dict.

    next_horizon_trend controls what the mocked engine.adjacent_aligned
    reports for a `direction`-matching scenario: "bullish"/"bearish" ->
    aligned/opposed. Left at the _UNSET sentinel (its default) to leave
    the REAL adjacent_aligned in place instead -- used only by the 9m
    exemption test, where the real function already returns "exempt"
    with no df dependency (9m has no higher horizon).
    """
    trend_len, box_len = (300, 90) if horizon == "9m" else (120, 60)
    df = _structured_df(trend_len, box_len)

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

        mp.setattr(engine, "load_watchlist", lambda: ["TEST"])
        mp.setattr(
            fetch, "get_daily_data",
            lambda ticker, period=None: df.copy() if ticker == "TEST" else None,
        )
        # v55: force the batched live-price/cold-fetch path to resolve empty
        # (real batch calls would otherwise hit real network through a real
        # ProcessPoolExecutor) -- same "no live price -> falls back to the
        # daily close" behavior the old get_current_price->None mock gave.
        mp.setattr(fetch, "get_daily_data_batch", lambda tickers, period=None: {})
        mp.setattr(fetch, "get_current_price_batch", lambda tickers: {})
        mp.setattr(fetch, "ProcessPoolExecutor", _InlineProcessPool)
        mp.setattr(engine, "trade_log",
                   TradeLog(path=os.path.join(config.DATA_DIR, "trades.json")))
        mp.setattr(analyze, "trade_log", engine.trade_log)
        mp.setattr(runstate, "is_stop_requested", lambda: False)

        if next_horizon_trend is not _UNSET:
            def _fake_adjacent_aligned(_df, _horizon_key, scen_direction):
                if scen_direction != direction:
                    # The fixture's opposite-direction scenario -- not
                    # under test here, must never itself get dropped so
                    # it can't be mistaken for the scenario under test.
                    return {"status": "aligned", "reason": "not under test",
                            "trend": scen_direction}
                if next_horizon_trend == scen_direction:
                    return {"status": "aligned", "reason": "test: aligned",
                            "trend": next_horizon_trend}
                return {"status": "opposed", "reason": "test: opposed",
                        "trend": next_horizon_trend}

            mp.setattr(analyze, "adjacent_aligned", _fake_adjacent_aligned)

        captured = {}

        def _capture_and_shortcircuit(items):
            captured["items"] = list(items)
            return []   # skip the alert-building loop -- irrelevant to the gate

        mp.setattr(dedup, "dedup_scan_items", _capture_and_shortcircuit)

        progress = ScanProgress()
        engine._sync_run_scan(horizon, require_confirmation=False,
                               progress=progress, min_confluence=0)

    items = [item for item in captured.get("items", [])
             if item.result.trend == direction]
    return items, progress.funnel


def _scan_with(direction, next_horizon_trend=_UNSET, horizon="4w"):
    items, _funnel = _scan_with_funnel(direction, next_horizon_trend, horizon)
    return items


def test_gate_off_by_default_lets_counter_trend_through(monkeypatch):
    monkeypatch.setattr(config, "MTF_ADJACENT_GATE", False)
    items = _scan_with(direction="bullish", next_horizon_trend="bearish")
    assert len(items) == 1


def test_gate_on_drops_a_counter_trend_scenario(monkeypatch):
    monkeypatch.setattr(config, "MTF_ADJACENT_GATE", True)
    items = _scan_with(direction="bullish", next_horizon_trend="bearish")
    assert items == []


def test_gate_on_keeps_an_aligned_scenario(monkeypatch):
    monkeypatch.setattr(config, "MTF_ADJACENT_GATE", True)
    items = _scan_with(direction="bullish", next_horizon_trend="bullish")
    assert len(items) == 1


def test_exempt_horizon_is_never_dropped(monkeypatch):
    """9m has no higher horizon. It must pass the gate, not fail it."""
    monkeypatch.setattr(config, "MTF_ADJACENT_GATE", True)
    items = _scan_with(direction="bullish", horizon="9m")
    assert len(items) == 1


def test_dropped_scenarios_increment_the_funnel_counter(monkeypatch):
    monkeypatch.setattr(config, "MTF_ADJACENT_GATE", True)
    _items, funnel = _scan_with_funnel(direction="bullish",
                                        next_horizon_trend="bearish")
    assert funnel["mtf_misaligned"] == 1
