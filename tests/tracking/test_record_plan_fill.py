"""TradeLog.record_plan_fill: moving a stop_entry plan's placeholder trade
(logged by scan_run.py at scan-detection time, while the plan is still
PENDING) onto its real fill price -- without creating a second trade record.

Production incident, 2026-09-10: QCOM's stop_entry plan got a placeholder
trade at detection time (entry=trigger price) and PlanManager._on_event's
"filled" handler then called log_trade() AGAIN at actual fill, leaving two
open trades sharing one plan_id. close_plan_trade() only ever finds and
closes the first; the second -- the one the admin UI actually displays, since
its plan/trade join keeps the LAST trade per plan_id -- never closed, no
matter how far price ran past its stop.
"""
import json

import pytest

from swingbot import config
from swingbot.core.tracking.performance import TradeLog


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    (tmp_path / "trades.json").write_text("[]", encoding="utf-8")
    (tmp_path / "account.json").write_text(json.dumps({
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    }), encoding="utf-8")
    return TradeLog()


def test_record_plan_fill_updates_the_placeholder_in_place(tlog):
    trade_id = tlog.log_trade(
        ticker="QCOM", strategy="FVG (bullish)", horizon_key="6m",
        direction="bullish", confidence_level=5, confidence_label="Very High",
        entry=174.5, stop_loss=170.96, take_profit=180.47, plan_id="p1")

    result_id = tlog.record_plan_fill("p1", 174.72)

    assert result_id == trade_id
    open_trades = [t for t in tlog.get_trades(status=None, limit=None)
                   if t.get("plan_id") == "p1"]
    assert len(open_trades) == 1, (
        "record_plan_fill must UPDATE the existing placeholder, never add a "
        "second trade record for the same plan_id"
    )
    assert open_trades[0]["entry"] == 174.72
    assert open_trades[0]["status"] == "open"


def test_record_plan_fill_resizes_shares_from_the_new_entry(tlog):
    tlog.log_trade(
        ticker="QCOM", strategy="FVG (bullish)", horizon_key="6m",
        direction="bullish", confidence_level=5, confidence_label="Very High",
        entry=174.5, stop_loss=170.96, take_profit=180.47, plan_id="p1")
    # dict(...) copy: get_trades() reloads self._trades from disk, but only
    # on the NEXT call -- between here and record_plan_fill() below, `before`
    # would otherwise alias the very dict record_plan_fill mutates in place.
    before = dict(next(t for t in tlog.get_trades(status=None, limit=None)
                       if t["plan_id"] == "p1"))

    tlog.record_plan_fill("p1", 174.72)

    after = next(t for t in tlog.get_trades(status=None, limit=None)
                 if t["plan_id"] == "p1")
    assert after["shares"] != before["shares"], (
        "shares/position_value must be resized off the real fill price, "
        "not left sized against the trigger price the placeholder used"
    )


def test_record_plan_fill_returns_none_when_no_placeholder_exists(tlog):
    assert tlog.record_plan_fill("nonexistent-plan", 100.0) is None


def test_record_plan_fill_ignores_an_already_closed_trade(tlog):
    trade_id = tlog.log_trade(
        ticker="QCOM", strategy="FVG (bullish)", horizon_key="6m",
        direction="bullish", confidence_level=5, confidence_label="Very High",
        entry=174.5, stop_loss=170.96, take_profit=180.47, plan_id="p1")
    tlog.close_plan_trade("p1", {"fraction": 1.0, "exit_price": 171.0,
                                  "r": -1.0, "reason": "loss"}, "loss")

    assert tlog.record_plan_fill("p1", 174.72) is None
    closed = next(t for t in tlog.get_trades(status=None, limit=None)
                 if t["id"] == trade_id)
    assert closed["status"] == "loss"
    assert closed["entry"] == 174.5   # untouched
