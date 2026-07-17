from swingbot.core.performance import TradeLog
from swingbot.core.plan_manager import PlanManager
from swingbot.core.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.test_plan_manager_pending import _pending


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
    for _ in range(4):
        transitions.extend(e.transition for e in mgr.poll())
    assert transitions == ["filled", "tp1_partial", "closed"] or \
           transitions == ["filled", "tp1_partial", "be_moved", "closed"]

    log.refresh()
    [t] = [t for t in log.get_trades(limit=10) if t.get("plan_id") == "p1"]
    assert t["status"] == "win"
    assert len(t["legs"]) == 2
    assert t["legs"][0]["reason"] == "tp1"
    assert t["legs"][1]["reason"].startswith("tp1_runner")
    assert t["realized_pnl_amount"] is not None or t["shares"] is None
