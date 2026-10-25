"""v188: a live risk_cap cancel writes the crossing price onto its history entry.

The only bot-side change in v188. Everything else a cancel produces -- the
event, its detail, the plan status, every stored field -- stays byte-identical;
the history entry gains exactly one key, `entry_price`.
"""
import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict, record_transition
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_pending import _mgr, _pending

AT = "2026-08-03T15:00:00+00:00"


def _poll(tmp_path, monkeypatch, price, **plan_kw):
    """One poll at a pinned clock, out of structural-stop scope (2% ceiling)."""
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    store, mgr = _mgr(tmp_path, FakePriceFeed([("AAPL", price)]))
    monkeypatch.setattr(mgr, "_now", lambda: AT)
    store.add(_pending(**plan_kw))
    return store, mgr.poll()


def test_risk_cap_history_entry_carries_the_crossing_price(tmp_path, monkeypatch):
    store, events = _poll(tmp_path, monkeypatch, 106.0, stop_loss=95.0)
    assert [e.transition for e in events] == ["cancelled_risk_cap"]
    entry = store.get("p1").status_history[-1]
    assert entry == {"entry_price": 106.0, "status": "CANCELLED",
                     "reason": "risk_cap", "at": AT}


def test_the_recorded_price_is_the_fill_not_the_live_quote_below_trigger(tmp_path, monkeypatch):
    # bearish: fill = min(price, trigger); live 94.0 under trigger 95.0 fills at 94.0
    store, _ = _poll(tmp_path, monkeypatch, 94.0, direction="bearish",
                     trigger_price=95.0, stop_loss=105.0, tp1=80.0)
    assert store.get("p1").status_history[-1]["entry_price"] == 94.0


def test_event_detail_is_unchanged(tmp_path, monkeypatch):
    _, events = _poll(tmp_path, monkeypatch, 106.0, stop_loss=95.0)
    assert events[0].detail == {
        "entry_price": 106.0,
        "stop_loss": 95.0,
        "planned_loss_pct": round(abs(106.0 - 95.0) / 106.0 * 100, 4),
        "max_planned_loss_pct": pytest.approx(2.0),
    }


def test_stored_plan_is_byte_identical_but_for_the_new_key(tmp_path, monkeypatch):
    store, _ = _poll(tmp_path, monkeypatch, 106.0, stop_loss=95.0)
    stored = plan_to_dict(store.get("p1"))
    assert stored["status_history"][-1].pop("entry_price") == 106.0

    control = _pending(stop_loss=95.0)
    record_transition(control, PlanStatus.CANCELLED, reason="risk_cap", at=AT)
    expected = plan_to_dict(control)
    # created_at is normalised by the store and pending_notice is the v81 feed
    # bookkeeping of any poll; neither is touched by v188.
    for key in ("created_at", "pending_notice"):
        stored.pop(key), expected.pop(key)
    assert stored == expected
    assert store.get("p1").entry_price is None        # a cancel never sets entry_price


def test_invalidated_and_filled_entries_gain_no_key(tmp_path, monkeypatch):
    store, events = _poll(tmp_path, monkeypatch, 94.0, stop_loss=95.0)
    assert [e.transition for e in events] == ["cancelled_invalidated"]
    assert set(store.get("p1").status_history[-1]) == {"status", "reason", "at"}

    store, events = _poll(tmp_path, monkeypatch, 106.0, stop_loss=104.0)
    assert [e.transition for e in events] == ["filled"]
    assert set(store.get("p1").status_history[-1]) == {"status", "reason", "at"}
