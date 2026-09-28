"""v104 §2.3: pending fills are checked against the plan's own stop ceiling."""
import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_pending import _mgr, _pending


def _poll(tmp_path, monkeypatch, scope, **plan_kw):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", scope, raising=False)
    store, mgr = _mgr(tmp_path, FakePriceFeed([("AAPL", 106.0)]))
    store.add(_pending(**plan_kw))
    return store, mgr.poll()


def test_in_scope_fill_within_max_risk_pct_fills(tmp_path, monkeypatch):
    store, events = _poll(tmp_path, monkeypatch, "Fibonacci:bullish", stop_loss=99.0)
    assert [event.transition for event in events] == ["filled"]
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_in_scope_fill_beyond_max_risk_pct_cancels_at_that_ceiling(tmp_path, monkeypatch):
    _, events = _poll(tmp_path, monkeypatch, "Fibonacci:bullish", stop_loss=95.0)
    assert [event.transition for event in events] == ["cancelled_risk_cap"]
    assert events[0].detail["max_planned_loss_pct"] == pytest.approx(7.0)


def test_out_of_scope_keeps_the_two_percent_cap(tmp_path, monkeypatch):
    _, events = _poll(tmp_path, monkeypatch, "", stop_loss=99.0)
    assert [event.transition for event in events] == ["cancelled_risk_cap"]
    assert events[0].detail["max_planned_loss_pct"] == pytest.approx(2.0)


def test_confluence_plans_are_never_in_scope(tmp_path, monkeypatch):
    _, events = _poll(
        tmp_path, monkeypatch, "Fibonacci:bullish", stop_loss=99.0, source="confluence")
    assert [event.transition for event in events] == ["cancelled_risk_cap"]
