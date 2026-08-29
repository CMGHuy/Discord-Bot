import datetime as dt

import pytest

from swingbot.core.tracking.performance import TradeLog, closed_r_multiple
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

    assert log.get_extended_stats(trades=[trade])["expectancy_r"] == pytest.approx(
        closed_r_multiple(trade)
    )

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

@pytest.fixture(autouse=True)
def _rth_gate_off(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)