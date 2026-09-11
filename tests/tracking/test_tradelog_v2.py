import datetime as dt

import pytest

from swingbot.core.tracking.performance import TradeLog, closed_r_multiple, expand_trade_legs
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_pending import _pending


def test_full_lifecycle_writes_two_leg_win(tmp_path):
    feed = FakePriceFeed()
    feed.set_series("AAPL", [
        106.0,    # fill (trigger 105)
        116.0,    # tp1 partial (tp1 110 -> touched; entry 106, stop 95)
        140.0,    # runner ratchets trail well above entry
        118.0,    # pierces trail -> tp1_runner_trail close
    ])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    log = TradeLog(path=str(tmp_path / "trades.json"))
    store.add(_pending(tp1=110.0, tp2=None))
    mgr = PlanManager(store, feed.get_price, atr_fn=lambda t: 2.0,
                      trade_log=log)

    transitions = []
    for day in range(27, 31):
        now = dt.datetime(2026, 8, day, 12, 0, tzinfo=US_MARKET_TZ)
        transitions.extend(e.transition for e in mgr.poll(now=now))
    assert transitions == ["filled", "tp1_partial", "closed"] or \
           transitions == ["filled", "tp1_partial", "be_moved", "closed"]

    log.refresh()
    [t] = [t for t in log.get_trades(limit=10) if t.get("plan_id") == "p1"]
    assert t["status"] == "win"
    assert len(t["legs"]) == 2
    assert t["legs"][0]["reason"] == "tp1"
    assert t["legs"][1]["reason"].startswith("tp1_runner")
    assert t["realized_pnl_amount"] is not None or t["shares"] is None


def test_extended_stats_uses_leg_aware_closed_r_multiple(tmp_path):
    trade = {
        "status": "win",
        "direction": "bullish",
        "entry": 100.0,
        "stop_loss": 95.0,
        "exit_price": 100.25,
        "legs": [
            {"fraction": 0.5, "r": 2.0, "exit_price": 110.0},
            {"fraction": 0.5, "r": 0.05, "exit_price": 100.25},
        ],
    }
    log = TradeLog(path=str(tmp_path / "trades.json"))

    # With leg expansion, each leg is counted as its own outcome, so expectancy_r
    # becomes the average of individual leg R-multiples (2.0 and 0.05), which is 1.025.
    # This equals the fraction-weighted sum (0.5*2.0 + 0.5*0.05 = 1.025) by coincidence
    # of equal weighting -- the difference from closed_r_multiple(trade) (1.02) is only
    # rounding: the original rounds the blended sum, but expanded legs average pre-rounded values.
    assert log.get_extended_stats(trades=[trade])["expectancy_r"] == pytest.approx(1.025)

def test_close_plan_trade_journals_and_refreshes_snapshot(tmp_path, monkeypatch):
    log = TradeLog(path=str(tmp_path / "trades.json"))
    log._trades = [{
        "id": "t-close", "plan_id": "p-close", "ticker": "AAPL",
        "status": "open", "direction": "bullish", "entry": 100.0,
        "stop_loss": 95.0, "shares": None, "legs": [],
    }]
    journaled = []
    refreshed = []
    monkeypatch.setattr("swingbot.core.tracking.performance._journal_close_safely", journaled.append)
    monkeypatch.setattr("swingbot.core.tracking.performance._refresh_snapshot_safely", lambda: refreshed.append(True))

    log.close_plan_trade("p-close", {"fraction": 1.0, "exit_price": 105.0, "r": 1.0}, "win")

    assert [trade["id"] for trade in journaled] == ["t-close"]
    assert refreshed == [True]

def test_expand_trade_legs_passes_through_a_trade_with_no_legs():
    trade = {"status": "win", "shares": 10, "entry": 100.0,
             "direction": "bullish", "stop_loss": 95.0, "exit_price": 110.0}
    assert expand_trade_legs(trade) == [trade]


def test_expand_trade_legs_splits_a_fully_closed_scaled_out_trade():
    trade = {
        "status": "win", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 118.0,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 118.0, "r": 3.6, "reason": "tp1_runner_tp2"},
        ],
    }
    rows = expand_trade_legs(trade)
    assert len(rows) == 2
    assert [r["shares"] for r in rows] == [5.0, 5.0]
    assert [r["exit_price"] for r in rows] == [110.0, 118.0]
    assert [r["status"] for r in rows] == ["win", "win"]


def test_expand_trade_legs_adds_the_open_remainder():
    trade = {
        "status": "open", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": None,
        "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}],
    }
    rows = expand_trade_legs(trade)
    assert len(rows) == 2
    assert rows[0]["status"] == "win" and rows[0]["shares"] == 5.0
    assert rows[1]["status"] == "open" and rows[1]["shares"] == 5.0
    assert rows[1]["exit_price"] is None


def test_expand_trade_legs_classifies_a_negative_r_leg_as_loss():
    trade = {
        "status": "closed", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 98.0,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 98.0, "r": -0.4, "reason": "manual"},
        ],
    }
    rows = expand_trade_legs(trade)
    assert [r["status"] for r in rows] == ["win", "loss"]


def test_get_extended_stats_counts_each_leg_as_its_own_outcome(tmp_path):
    trade = {
        "status": "win", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 118.0, "confidence_level": None,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 90.0, "r": -0.5, "reason": "manual"},
        ],
    }
    log = TradeLog(path=str(tmp_path / "trades.json"))
    stats = log.get_stats(trades=[trade])
    assert stats["total"] == 2 and stats["wins"] == 1 and stats["losses"] == 1


@pytest.fixture(autouse=True)
def _rth_gate_off(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)