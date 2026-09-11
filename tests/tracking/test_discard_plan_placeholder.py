"""TradeLog.discard_plan_placeholder: removing a PENDING plan's placeholder
trade (logged by scan_run.py at scan-detection time) when the plan is
cancelled before it ever fills.

Production incident, 2026-09-11: PlanManager._on_event handled "filled",
"tp1_partial" and "closed" but not "cancelled_expired"/"cancelled_invalidated",
so a cancelled plan's placeholder trade -- entry sized against the trigger
price, never a real fill -- sat "open" forever. Found via a dashboard
mismatch: the "Open trades" chip counts TradeLog directly (10), while the
Open positions table reads plan status (all 10 plans were already
CLOSED/CANCELLED, so the table showed nothing). Confirmed on production data:
10 stuck trades, 2 of which (INTU, META) were this exact shape -- a single
placeholder with no closed sibling, its plan CANCELLED pre-fill.
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


def test_discard_removes_the_open_placeholder(tlog):
    tlog.log_trade(
        ticker="INTU", strategy="EMA", horizon_key="5m",
        direction="bullish", confidence_level=4, confidence_label="High",
        entry=361.04, stop_loss=353.62, take_profit=373.92, plan_id="p1")

    assert tlog.discard_plan_placeholder("p1") is True
    assert [t for t in tlog.get_trades(status=None, limit=None)
            if t.get("plan_id") == "p1"] == []


def test_discard_deletes_rather_than_closes(tlog):
    """A cancelled plan never filled -- there is no real exit to record, so
    the row must be gone entirely, not left behind with a synthetic status
    that would double-count it in win/loss/expectancy stats."""
    trade_id = tlog.log_trade(
        ticker="META", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", confidence_level=4, confidence_label="High",
        entry=662.79, stop_loss=647.94, take_profit=687.14, plan_id="p1")

    tlog.discard_plan_placeholder("p1")

    assert tlog.get_trade_by_id(trade_id) is None


def test_discard_returns_false_when_no_placeholder_exists(tlog):
    assert tlog.discard_plan_placeholder("nonexistent-plan") is False
    assert tlog.get_trades(status=None, limit=None) == []


def test_discard_ignores_an_already_filled_trade(tlog):
    """discard_plan_placeholder only ever matches status=="open" by design --
    cancellation is only reachable from PENDING (plan_manager._step_pending),
    so a plan that has already filled can never route here in practice. Pin
    the guard anyway: a status other than "open" (e.g. a closed position)
    must never be silently deleted."""
    trade_id = tlog.log_trade(
        ticker="META", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", confidence_level=4, confidence_label="High",
        entry=662.79, stop_loss=647.94, take_profit=687.14, plan_id="p1")
    tlog.close_plan_trade("p1", {"fraction": 1.0, "exit_price": 700.0,
                                  "r": 1.0, "reason": "win"}, "win")

    assert tlog.discard_plan_placeholder("p1") is False
    assert tlog.get_trade_by_id(trade_id) is not None
