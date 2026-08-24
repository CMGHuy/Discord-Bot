"""v32 Task 7: RS/breadth are computed during a scan but were never
handed to score_confidence -- the whole premise of the unified score.
Driven through the real _sync_run_scan code path (not a direct call), same
pattern as test_engine_v2_plans.py's _sync_run_scan gate tests, so this
actually proves the wiring rather than the isolated function signature.

MTF was part of this wiring too until v33 Task 6 retired mtf_alignment as
a scored input (-8.0pp non-overlapping TRAIN lift); see
docs/superpowers/plans/implemented/v33-trend-signal-reconciliation.md."""
import json

import numpy as np
import pytest

import swingbot.config as config
from swingbot.core.edge import factors as rs_factors
from swingbot.core.scanning import engine
from swingbot.core.scanning.confidence import ConfidenceResult
from swingbot.core.tracking.performance import TradeLog
from tests.helpers import make_ohlcv


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


def _structured_df():
    """Same recipe as test_engine_v2_plans.py's _structured_df(): trend up,
    then a consolidation box, giving every level source real structure on
    both sides of price so build_scenarios() reliably produces a scenario."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


def test_score_confidence_receives_rs_breadth(monkeypatch, tmp_path, stub_batch_fetch):
    """Regression guard for the v32 premise: these were computed and
    then never handed to the gate. If this test fails, RS/breadth have
    stopped influencing which alerts fire."""
    df = _structured_df()

    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.01)
    monkeypatch.setitem(engine.HORIZONS["4w"], "sr_target_min_pct", 1.0)

    monkeypatch.setattr(engine, "load_watchlist", lambda: ["TEST"])
    monkeypatch.setattr(
        engine, "get_daily_data",
        lambda ticker, period=None: df.copy() if ticker in ("TEST", "SPY") else None,
    )
    monkeypatch.setattr(engine, "trade_log", TradeLog(path=str(tmp_path / "trades.json")))
    monkeypatch.setattr(engine, "is_stop_requested", lambda: False)

    # Deterministic, controlled RS/breadth readings -- the real universe-wide
    # computations need a real multi-ticker universe this fixture doesn't
    # build; injecting fixed values isolates what's actually under test
    # (does the wiring reach score_confidence), not the RS/breadth math
    # itself (covered elsewhere).
    monkeypatch.setattr(rs_factors, "refresh_rs_cache",
                        lambda fresh_data, spy_df: {"rels": {"TEST": 1.0}})
    monkeypatch.setattr(rs_factors, "rs_percentile", lambda *a, **kw: 82.0)
    monkeypatch.setattr(rs_factors, "breadth_pct_above_50ema", lambda universe_dfs: 61.0)

    captured = []

    def fake_score(scenario, **kwargs):
        captured.append(kwargs)
        return ConfidenceResult(level=4, label="High", score=70, breakdown={})

    monkeypatch.setattr(engine, "score_confidence", fake_score)
    monkeypatch.setattr(engine, "dedup_scan_items", lambda items: [])

    engine._sync_run_scan("4w", require_confirmation=False, progress=None, min_confluence=0)

    assert captured, "fixture must produce at least one real scenario to exercise the wiring"
    assert all(c.get("rs_percentile") == 82.0 for c in captured)
    assert all(c.get("breadth") == 61.0 for c in captured)
