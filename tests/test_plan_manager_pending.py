from swingbot.core.plan_engine import PlanStatus
from swingbot.core.plan_manager import PlanManager
from swingbot.core.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.test_plan_engine_model import _plan


def _pending(**kw):
    # base-dict-then-update (same idiom _plan() itself uses) so an explicit
    # override of any of these defaults doesn't collide as a duplicate kwarg.
    base = dict(entry_type="stop_entry", direction="bullish",
               trigger_price=105.0, stop_loss=95.0, tp1=110.0, expiry_bars=5)
    base.update(kw)
    return _plan(**base)


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


def test_pending_expires_past_expiry_bars(tmp_path):
    feed = FakePriceFeed([("AAPL", 100.0)])       # never reaches trigger
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_pending(expiry_bars=5))
    mgr = PlanManager(store, feed.get_price, bar_count_fn=lambda t, created: 6)
    events = mgr.poll()
    assert [e.transition for e in events] == ["cancelled_expired"]
    assert store.get("p1").status == PlanStatus.CANCELLED


def test_pending_at_exactly_expiry_bars_still_live(tmp_path):
    feed = FakePriceFeed([("AAPL", 100.0)])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_pending(expiry_bars=5))
    mgr = PlanManager(store, feed.get_price, bar_count_fn=lambda t, created: 5)
    assert mgr.poll() == []                        # boundary: == is NOT expired


def test_no_bar_count_fn_means_no_expiry(tmp_path):
    feed = FakePriceFeed([("AAPL", 100.0)])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_pending())
    assert PlanManager(store, feed.get_price).poll() == []


def test_pending_invalidates_when_price_breaks_stop(tmp_path):
    feed = FakePriceFeed([("AAPL", 94.0)])        # below stop 95, trigger never hit
    store, mgr = _mgr(tmp_path, feed)
    store.add(_pending())
    events = mgr.poll()
    assert [e.transition for e in events] == ["cancelled_invalidated"]
    assert store.get("p1").status == PlanStatus.CANCELLED


def test_bearish_pending_invalidates_above_stop(tmp_path):
    from tests.test_plan_engine_model import _plan
    feed = FakePriceFeed([("AAPL", 106.0)])
    store, mgr = _mgr(tmp_path, feed)
    store.add(_plan(entry_type="stop_entry", direction="bearish",
                    trigger_price=95.0, stop_loss=105.0, tp1=90.0))
    events = mgr.poll()
    assert [e.transition for e in events] == ["cancelled_invalidated"]
