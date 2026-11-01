"""v189 A7 over HTTP: a trade-id delete and clear-open end the linked plans
and report them; a lock timeout is a 409 and nothing changes."""
import pytest

from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
_PLAN_ID = "55555555-5555-4555-8555-555555555555"
_TRADE_ID = "bbbbbbbbbbbbbbbb"
_TP1 = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}


@pytest.fixture
def seed(admin_app):
    def _seed(plans=(), trades=()):
        seed_store("plans", list(plans))
        seed_store("trades", list(trades))
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture(autouse=True)
def _no_live_quote(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)


def _stored(plan_id):
    from swingbot.core.planning.plan_store import PlanStore
    return PlanStore().get(plan_id)


def test_deleting_a_partial_trade_closes_its_plan_and_says_so(seed, logged_in):
    seed(plans=[{**_plan(_PLAN_ID, status="PARTIAL"), "legs_realized": [dict(_TP1)]}],
         trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    r = logged_in.delete(f"/api/v1/trades/{_TRADE_ID}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["deleted"] == _TRADE_ID
    assert body["ended"] == [{"plan_id": _PLAN_ID, "ticker": "AAPL",
                              "status_before": "PARTIAL", "status_after": "CLOSED"}]
    assert f"AAPL (`{_PLAN_ID}`, was PARTIAL)" in body["notice"]
    assert "no more stop or take-profit alerts" in body["notice"]
    assert "TP1 dollars" in body["notice"]
    plan = _stored(_PLAN_ID)
    assert plan.status == "CLOSED"
    assert plan.pending_notice["detail"] == {"reason": "trade_deleted"}


def test_deleting_a_pending_placeholder_cancels_its_plan(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID, status="PENDING")], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    body = logged_in.delete(f"/api/v1/trades/{_TRADE_ID}").get_json()
    assert [e["status_after"] for e in body["ended"]] == ["CANCELLED"]
    assert _stored(_PLAN_ID).pending_notice["transition"] == "cancelled_trade_deleted"


def test_deleting_a_legacy_trade_reports_nothing_ended(seed, logged_in):
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")])
    body = logged_in.delete(f"/api/v1/trades/{_TRADE_ID}").get_json()
    assert body == {"deleted": _TRADE_ID, "ended": [], "notice": ""}


def test_clear_open_ends_the_plans_and_reports_them(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID, status="ACTIVE")],
         trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID),
                 _trade("cccccccccccccccc", plan_id=None, status="win")])
    body = logged_in.post("/api/v1/trades/clear-open").get_json()
    assert body["removed"] == 1
    assert [(e["plan_id"], e["status_after"]) for e in body["ended"]] == [(_PLAN_ID, "CLOSED")]
    assert body["notice"].startswith("Ended 1 open position(s): AAPL")
    assert _stored(_PLAN_ID).status == "CLOSED"


@pytest.mark.parametrize("method, path, attr", [
    ("delete", f"/api/v1/trades/{_TRADE_ID}", "delete_trade"),
    ("post", "/api/v1/trades/clear-open", "clear_open"),
])
def test_a_lock_timeout_is_a_409(seed, logged_in, monkeypatch, method, path, attr):
    from swingbot.core.db.engine import LockTimeout
    from swingbot.core.tracking.performance import TradeLog

    def locked(self, *args):
        raise LockTimeout("plan row held by the bot")

    seed(plans=[_plan(_PLAN_ID, status="ACTIVE")], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    monkeypatch.setattr(TradeLog, attr, locked)
    assert_error(getattr(logged_in, method)(path), "conflict", 409)
    assert _stored(_PLAN_ID).status == "ACTIVE"
