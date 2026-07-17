from swingbot.core.plan_engine import PlanStatus
from swingbot.core.plan_manager import PlanManager
from swingbot.core.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.test_plan_engine_model import _plan


def _pending(**kw):
    return _plan(entry_type="stop_entry", direction="bullish",
                 trigger_price=105.0, stop_loss=95.0, tp1=110.0,
                 expiry_bars=5, **kw)


def _mgr(tmp_path, feed, **kw):
    store = PlanStore(path=str(tmp_path / "plans.json"))
    return store, PlanManager(store, feed.get_price, **kw)


def test_pending_fills_when_price_crosses_trigger(tmp_path):
    feed = FakePriceFeed([("AAPL", 106.0)])
    store, mgr = _mgr(tmp_path, feed)
    store.add(_pending())
    events = mgr.poll()
    assert [e.transition for e in events] == ["filled"]
    p = store.get("p1")
    assert p.status == PlanStatus.ACTIVE
    assert p.entry_price == 106.0        # max(live 106, trigger 105)
    assert events[0].detail["entry_price"] == 106.0


def test_pending_below_trigger_no_event(tmp_path):
    feed = FakePriceFeed([("AAPL", 104.0)])
    store, mgr = _mgr(tmp_path, feed)
    store.add(_pending())
    assert mgr.poll() == []
    assert store.get("p1").status == PlanStatus.PENDING


def test_price_fetch_failure_skips_plan_not_poll(tmp_path):
    def flaky(ticker):
        raise TimeoutError("yfinance hiccup")
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_pending())
    mgr = PlanManager(store, flaky)
    assert mgr.poll() == []              # no crash, no transition
