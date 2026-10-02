"""A plan write that halts mid-scan must not leave trades the book recorded
without an alert, nor an alert without a record (v116-23 review, finding A)."""
import pytest

import swingbot.config as config
from swingbot.core.db import write_failure
from swingbot.core.scanning import engine, fetch, runstate, scan_run
from swingbot.core.tracking.performance import TradeLog
from tests.scanning.test_engine_v2_plans import _structured_df

import sqlalchemy.exc as sa_exc


class _FailsOnSecondAdd:
    stored: list = []
    calls = 0

    def add(self, plan):
        type(self).calls += 1
        if type(self).calls >= 2:
            raise sa_exc.OperationalError("INSERT INTO plans", {}, Exception("gone"))
        type(self).stored.append(plan.plan_id)


def test_a_halt_on_the_second_plan_keeps_book_and_alerts_consistent(
        monkeypatch, tmp_path, stub_batch_fetch):
    df = _structured_df()
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.01)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 1)
    monkeypatch.setitem(scan_run.HORIZONS["4w"], "sr_target_min_pct", 1.0)
    monkeypatch.setattr(scan_run, "load_watchlist", lambda: ["T0", "T1"])
    monkeypatch.setattr(fetch, "get_daily_data",
                        lambda ticker, period=None: df.copy() if ticker in ("T0", "T1") else None)
    log = TradeLog()
    monkeypatch.setattr(scan_run, "trade_log", log)
    monkeypatch.setattr(runstate, "is_stop_requested", lambda: False)
    monkeypatch.setattr(scan_run, "earnings_within_window", lambda t, d: None)
    monkeypatch.setattr(scan_run, "get_market_events", lambda d: [])
    monkeypatch.setattr(scan_run, "generate_trade_chart", lambda *a, **k: None)
    monkeypatch.setattr(scan_run, "notify_secondary", lambda *a, **k: None)
    monkeypatch.setattr(scan_run, "log_plan_armed", lambda p: None)
    monkeypatch.setattr(scan_run, "build_embed", lambda item, *a, **k: item.result.ticker)
    monkeypatch.setattr(scan_run, "build_simple_alert", lambda item: "simple")
    _FailsOnSecondAdd.stored, _FailsOnSecondAdd.calls = [], 0
    monkeypatch.setattr(scan_run, "PlanStore", _FailsOnSecondAdd)

    with pytest.raises(write_failure.StoreWriteHalt) as caught:
        engine._sync_run_scan("4w", require_confirmation=False, progress=None, min_confluence=0)

    sent = caught.value.alerts
    recorded = log.get_trades(status=None, limit=None)
    assert _FailsOnSecondAdd.calls == 2, "fixture must reach a second plan write"
    assert len(sent) == len(recorded) == 1
    assert [t["plan_id"] for t in recorded] == _FailsOnSecondAdd.stored
