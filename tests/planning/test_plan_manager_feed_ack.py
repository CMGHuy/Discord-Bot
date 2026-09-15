"""v81 delivery acknowledgement and no-price notice sweep coverage."""
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_manager import Delivery, PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(pm, "_MANAGER", None)
    return PlanStore()


def _notice(transition="closed"):
    return {"transition": transition, "detail": {"reason": "loss", "exit_price": 94.5},
            "at": datetime.now(timezone.utc).isoformat()}


def test_delivered_stop_is_recorded(store):
    store.add(_plan(status="PARTIAL", entry_price=100.0, working_stop=107.3))
    pm.ack_notified([Delivery("p1", "stop", 107.3)])
    assert PlanStore().get("p1").notified_stop == 107.3


def test_delivered_notice_clears_only_matching_queue(store):
    store.add(_plan(status="CLOSED", pending_notice=_notice("closed")))
    pm.ack_notified([Delivery("p1", "notice", "filled")])
    assert PlanStore().get("p1").pending_notice["transition"] == "closed"
    pm.ack_notified([Delivery("p1", "notice", "closed")])
    assert PlanStore().get("p1").pending_notice is None


def test_ack_writes_through_live_manager_store(store, monkeypatch):
    store.add(_plan(status="PARTIAL", entry_price=100.0, working_stop=107.3))
    manager = PlanManager(PlanStore(), lambda ticker: 100.0)
    monkeypatch.setattr(pm, "_MANAGER", manager)
    pm.ack_notified([Delivery("p1", "stop", 107.3)])
    assert manager.store.get("p1").notified_stop == 107.3


def test_sweep_resends_without_price_fetch(store, monkeypatch):
    store.add(_plan(status="CLOSED", pending_notice=_notice("closed")))
    monkeypatch.setattr(pm, "_price_fn", lambda ticker: pytest.fail("no price fetch"))
    assert [event.transition for event in pm.run_notice_sweep()] == ["closed"]


def test_sweep_is_noop_when_manager_is_disabled(store, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", False)
    store.add(_plan(status="CLOSED", pending_notice=_notice("closed")))
    assert pm.run_notice_sweep() == []
