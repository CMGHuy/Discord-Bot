"""v170 A1: TradeLog.trade_for_plan finds a plan's paper trade in ANY status.

append_leg_by_plan / close_plan_trade only match status == "open", so a
closed trade could not be found by plan id before this accessor. The feed's
lifecycle money and the P&L-now reply both read it."""
import pytest

from swingbot import config
from swingbot.core.tracking.performance import TradeLog
from tests.store_seed import seed_store


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    return TradeLog()


def _log(tlog, plan_id="p1", ticker="INTU"):
    tlog.log_trade(
        ticker=ticker, strategy="EMA", horizon_key="5m",
        direction="bullish", confidence_level=4, confidence_label="High",
        entry=361.04, stop_loss=353.62, take_profit=373.92, plan_id=plan_id)


def test_an_open_trade_is_found_by_its_plan_id(tlog):
    _log(tlog)
    trade = tlog.trade_for_plan("p1")
    assert trade is not None
    assert (trade["plan_id"], trade["ticker"], trade["status"]) == ("p1", "INTU", "open")
    assert trade["entry"] == pytest.approx(361.04)
    assert trade["shares"] > 0
    assert trade["realized_pnl_amount"] is None


def test_a_closed_trade_is_still_found_with_its_settled_amount(tlog):
    _log(tlog)
    tlog.close_plan_trade("p1", {"fraction": 1.0, "exit_price": 370.0, "r": 1.2,
                                 "reason": "win"}, "win")
    trade = tlog.trade_for_plan("p1")
    assert trade is not None and trade["status"] == "win"
    shares = trade["shares"]
    assert trade["realized_pnl_amount"] == pytest.approx(shares * (370.0 - 361.04), abs=0.01)


def test_the_shape_matches_get_trade_by_id(tlog):
    _log(tlog)
    by_plan = tlog.trade_for_plan("p1")
    assert by_plan == tlog.get_trade_by_id(by_plan["id"])


def test_an_unknown_or_empty_plan_id_is_none(tlog):
    _log(tlog)
    assert tlog.trade_for_plan("nope") is None
    assert tlog.trade_for_plan("") is None
    assert tlog.trade_for_plan(None) is None


def test_another_plans_trade_is_never_returned(tlog):
    _log(tlog, plan_id="p1", ticker="INTU")
    _log(tlog, plan_id="p2", ticker="MSFT")
    assert tlog.trade_for_plan("p2")["ticker"] == "MSFT"


def test_it_does_not_rescan_the_whole_log(tlog, monkeypatch):
    _log(tlog)
    monkeypatch.setattr(TradeLog, "_all", lambda self: pytest.fail("rescanned every trade"))
    assert tlog.trade_for_plan("p1")["plan_id"] == "p1"
