"""v139 arm S: a confluence plan's stored ceiling is the ceiling
plan_manager._step_pending checks a stop-entry fill against."""
import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_pending import _mgr, _pending

# 3.75% under the 105.0 trigger: arm S at c = 4.0, exactly at c - headroom.
STOP = 105.0 * (1 - 0.0375)


def _poll(tmp_path, monkeypatch, price, **plan_kw):
    # poll() reads the wall clock; without this the quiet window returns [].
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    store, mgr = _mgr(tmp_path, FakePriceFeed([("AAPL", price)]))
    store.add(_pending(source="confluence", strategy="S/R Confluence", stop_loss=STOP, **plan_kw))
    return store, mgr.poll()


def test_a_fill_inside_the_headroom_fills(tmp_path, monkeypatch):
    store, events = _poll(tmp_path, monkeypatch, 105.2, stop_ceiling_pct=4.0)   # 3.93% at the fill
    assert [event.transition for event in events] == ["filled"]
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_a_fill_past_the_stored_ceiling_cancels_at_that_ceiling(tmp_path, monkeypatch):
    _, events = _poll(tmp_path, monkeypatch, 106.0, stop_ceiling_pct=4.0)       # 4.66% at the fill
    assert [event.transition for event in events] == ["cancelled_risk_cap"]
    assert events[0].detail["max_planned_loss_pct"] == pytest.approx(4.0)


def test_without_a_stored_ceiling_the_two_percent_cap_still_applies(tmp_path, monkeypatch):
    _, events = _poll(tmp_path, monkeypatch, 105.2)
    assert [event.transition for event in events] == ["cancelled_risk_cap"]
    assert events[0].detail["max_planned_loss_pct"] == pytest.approx(2.0)
