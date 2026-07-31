from swingbot import config
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


# -- G128: trigger-time gate re-check ---------------------------------------


def test_gate_off_never_calls_recheck(tmp_path, monkeypatch):
    """GATE_ENABLED off (the default) -- _gate_recheck must not even be
    attempted, so a fill behaves byte-identically to pre-G128."""
    monkeypatch.setattr(config, "GATE_ENABLED", False, raising=False)
    feed = FakePriceFeed([("AAPL", 106.0)])
    store, mgr = _mgr(tmp_path, feed)
    monkeypatch.setattr(mgr, "_gate_recheck",
                        lambda plan: (_ for _ in ()).throw(AssertionError("must not be called")))
    store.add(_pending())
    events = mgr.poll()
    assert [e.transition for e in events] == ["filled"]
    assert "gate_delta" not in events[0].detail


def test_gate_delta_attached_to_filled_event_but_still_fires(tmp_path, monkeypatch):
    """A new flag since the alert shipped -- inform-first: the entry still
    fires, but the delta rides along on the event for the caller to ping
    about."""
    monkeypatch.setattr(config, "GATE_ENABLED", True, raising=False)
    feed = FakePriceFeed([("AAPL", 106.0)])
    store, mgr = _mgr(tmp_path, feed)
    monkeypatch.setattr(mgr, "_gate_recheck", lambda plan: {"delta": ["rf_news_whipsaw"]})
    store.add(_pending())
    events = mgr.poll()
    assert [e.transition for e in events] == ["filled"]
    assert events[0].detail["gate_delta"] == ["rf_news_whipsaw"]
    assert store.get("p1").status == PlanStatus.ACTIVE   # entry still fires


def test_gate_hold_keeps_plan_pending_this_tick(tmp_path, monkeypatch):
    """A fresh blackout appeared since the alert AND GATE_BLACKOUT_ENFORCE
    is on (G120 semantics, reused verbatim at trigger time) -- stay
    PENDING this tick instead of firing."""
    monkeypatch.setattr(config, "GATE_ENABLED", True, raising=False)
    feed = FakePriceFeed([("AAPL", 106.0)])
    store, mgr = _mgr(tmp_path, feed)
    monkeypatch.setattr(mgr, "_gate_recheck",
                        lambda plan: {"hold": {"action": "hold", "line": "⚠️ CPI soon",
                                               "release_at": "2099-01-01T00:00:00"}})
    store.add(_pending())
    events = mgr.poll()
    assert [e.transition for e in events] == ["recheck_held"]
    assert store.get("p1").status == PlanStatus.PENDING  # never fired this tick


def test_gate_recheck_failure_never_blocks_the_fill(tmp_path, monkeypatch):
    """A raising gate re-check must still let the entry fire -- same
    never-costs-a-trade guarantee as the scan path (G121)."""
    monkeypatch.setattr(config, "GATE_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "MACRO_ENABLED", True, raising=False)

    def boom():
        raise OSError("disk")

    monkeypatch.setattr("swingbot.core.macro.snapshot.load_snapshot", boom)
    feed = FakePriceFeed([("AAPL", 106.0)])
    store, mgr = _mgr(tmp_path, feed)
    store.add(_pending())
    events = mgr.poll()
    assert [e.transition for e in events] == ["filled"]


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
