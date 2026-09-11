import json

import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan


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
    from tests.planning.test_plan_engine_model import _plan
    feed = FakePriceFeed([("AAPL", 106.0)])
    store, mgr = _mgr(tmp_path, feed)
    store.add(_plan(entry_type="stop_entry", direction="bearish",
                    trigger_price=95.0, stop_loss=105.0, tp1=90.0))
    events = mgr.poll()
    assert [e.transition for e in events] == ["cancelled_invalidated"]

@pytest.fixture(autouse=True)
def _rth_gate_off(monkeypatch):
    """Arithmetic tests stay independent of the wall clock."""
    from swingbot import config
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)


def test_fill_updates_the_scan_time_placeholder_not_a_second_trade(tmp_path, monkeypatch):
    """Production incident, 2026-09-10: scan_run.py logs a placeholder trade
    for a stop_entry plan the moment it's detected (still PENDING, sized off
    the trigger price) -- see its log_trade() call right before PlanStore().
    add(plan_v2). Before this fix, PlanManager's "filled" handler logged a
    SECOND trade at actual fill instead of updating that placeholder, so two
    open trades ended up sharing one plan_id. close_plan_trade() only ever
    finds and closes the first (chronologically earliest) one, leaving the
    other -- the one the admin UI's plan/trade join actually shows -- open
    forever, regardless of price. Pin: exactly one trade per plan_id, its
    entry moved onto the real fill."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    (tmp_path / "trades.json").write_text("[]", encoding="utf-8")
    (tmp_path / "account.json").write_text(json.dumps({
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    }), encoding="utf-8")
    trade_log = TradeLog()
    # The scan-time placeholder: entry = trigger_price, not the eventual fill.
    trade_log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", confidence_level=None, confidence_label=None,
        entry=105.0, stop_loss=95.0, take_profit=110.0, plan_id="p1")

    feed = FakePriceFeed([("AAPL", 106.0)])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_pending())
    mgr = PlanManager(store, feed.get_price, trade_log=trade_log)

    events = mgr.poll()

    assert [e.transition for e in events] == ["filled"]
    open_for_plan = [t for t in trade_log.get_trades(status=None, limit=None)
                     if t.get("plan_id") == "p1"]
    assert len(open_for_plan) == 1, (
        "the fill must update the existing placeholder trade, not add a "
        "second one for the same plan_id"
    )
    assert open_for_plan[0]["entry"] == 106.0
    assert open_for_plan[0]["status"] == "open"


def test_fill_still_logs_a_trade_when_no_placeholder_exists(tmp_path, monkeypatch):
    """Defensive fallback: a plan can reach PlanStore some way other than
    scan_run.py's normal alert path (tests, a future manual-add feature) and
    so have no placeholder trade waiting. The fill must still get logged --
    not silently dropped -- just via a fresh trade this once."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    (tmp_path / "trades.json").write_text("[]", encoding="utf-8")
    (tmp_path / "account.json").write_text(json.dumps({
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    }), encoding="utf-8")
    trade_log = TradeLog()   # no placeholder logged

    feed = FakePriceFeed([("AAPL", 106.0)])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_pending())
    mgr = PlanManager(store, feed.get_price, trade_log=trade_log)

    events = mgr.poll()

    assert [e.transition for e in events] == ["filled"]
    assert events[0].detail.get("trade_id") is not None
    open_for_plan = [t for t in trade_log.get_trades(status=None, limit=None)
                     if t.get("plan_id") == "p1"]
    assert len(open_for_plan) == 1
    assert open_for_plan[0]["entry"] == 106.0


def test_expiry_discards_the_placeholder_trade(tmp_path, monkeypatch):
    """Production incident, 2026-09-11: PlanManager._on_event had no handler
    for cancelled_expired/cancelled_invalidated, so a PENDING plan's
    scan-time placeholder trade (see the fill-handler tests above) sat
    "open" forever once the plan itself was cancelled -- 10 stuck trades
    found via a dashboard chip/table mismatch (open_trades count vs. the
    Open positions panel, which reads plan status). A cancelled plan never
    filled, so the placeholder is deleted, not closed -- there is no real
    fill/exit to record."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    (tmp_path / "trades.json").write_text("[]", encoding="utf-8")
    (tmp_path / "account.json").write_text(json.dumps({
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    }), encoding="utf-8")
    trade_log = TradeLog()
    trade_log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", confidence_level=None, confidence_label=None,
        entry=105.0, stop_loss=95.0, take_profit=110.0, plan_id="p1")

    feed = FakePriceFeed([("AAPL", 100.0)])       # never reaches trigger
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_pending(expiry_bars=5))
    mgr = PlanManager(store, feed.get_price, bar_count_fn=lambda t, created: 6,
                      trade_log=trade_log)

    events = mgr.poll()

    assert [e.transition for e in events] == ["cancelled_expired"]
    remaining = [t for t in trade_log.get_trades(status=None, limit=None)
                if t.get("plan_id") == "p1"]
    assert remaining == []


def test_invalidation_discards_the_placeholder_trade(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    (tmp_path / "trades.json").write_text("[]", encoding="utf-8")
    (tmp_path / "account.json").write_text(json.dumps({
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    }), encoding="utf-8")
    trade_log = TradeLog()
    trade_log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", confidence_level=None, confidence_label=None,
        entry=105.0, stop_loss=95.0, take_profit=110.0, plan_id="p1")

    feed = FakePriceFeed([("AAPL", 94.0)])        # below stop 95, trigger never hit
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_pending())
    mgr = PlanManager(store, feed.get_price, trade_log=trade_log)

    events = mgr.poll()

    assert [e.transition for e in events] == ["cancelled_invalidated"]
    remaining = [t for t in trade_log.get_trades(status=None, limit=None)
                if t.get("plan_id") == "p1"]
    assert remaining == []


def test_cancellation_with_no_placeholder_is_a_safe_no_op(tmp_path, monkeypatch):
    """Defensive fallback mirroring test_fill_still_logs_a_trade_when_no_placeholder_exists:
    a plan can reach PlanStore with no placeholder trade waiting. Cancelling
    it must not raise just because there is nothing to discard."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    (tmp_path / "trades.json").write_text("[]", encoding="utf-8")
    (tmp_path / "account.json").write_text(json.dumps({
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    }), encoding="utf-8")
    trade_log = TradeLog()   # no placeholder logged

    feed = FakePriceFeed([("AAPL", 94.0)])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_pending())
    mgr = PlanManager(store, feed.get_price, trade_log=trade_log)

    events = mgr.poll()

    assert [e.transition for e in events] == ["cancelled_invalidated"]
    assert trade_log.get_trades(status=None, limit=None) == []