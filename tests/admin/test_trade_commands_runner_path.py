"""v142: closing a PARTIAL plan from the admin UI stamps runner_path; closing
an ACTIVE one does not, and a stamp that cannot be computed never blocks it."""
import pytest

from swingbot.core.analytics import runner_path as rp
from swingbot.core.planning.plan_store import PlanStore
from tests.admin.test_api_v1_trades import _plan
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
_PLAN_ID = "55555555-5555-4555-8555-555555555555"
_STAMP = {"mfe_r": 3.0, "mae_r": 1.5, "sessions_after_tp1": 1, "source": "live",
          "ladder": {"1.5": "2026-08-05", "2.0": None, "2.5": None, "3.0": None, "4.0": None}}


def _partial_record():
    record = _plan(_PLAN_ID, status="PARTIAL")
    record["status_history"] = [
        {"status": "ACTIVE", "reason": "filled", "at": "2026-08-04T14:00:00+00:00"},
        {"status": "PARTIAL", "reason": "tp1_partial", "at": "2026-08-05T15:00:00+00:00"}]
    record["legs_realized"] = [{"fraction": 0.5, "exit_price": 110.0, "r": 1.5, "reason": "tp1"}]
    return record


@pytest.fixture
def logged_in(admin_app, client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(rp, "cached_daily_bars", lambda ticker: f"bars:{ticker}")

    def fake(plan, bars, *, source="live"):
        seen.append((plan.status, bars, source))
        return dict(_STAMP)

    monkeypatch.setattr(rp, "compute_runner_path", fake)
    return seen


def test_a_manual_partial_close_stamps_from_the_disk_cache(logged_in, calls):
    seed_store("plans", [_partial_record()])
    assert logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close").status_code == 200
    assert calls == [("CLOSED", "bars:AAPL", "live")]
    assert PlanStore().get(_PLAN_ID).runner_path == _STAMP


def test_an_active_close_has_no_runner_and_no_stamp(logged_in, calls):
    seed_store("plans", [_plan(_PLAN_ID, status="ACTIVE")])
    assert logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close").status_code == 200
    assert calls == []
    assert PlanStore().get(_PLAN_ID).runner_path is None


def test_a_null_stamp_still_closes(logged_in, monkeypatch):
    monkeypatch.setattr(rp, "cached_daily_bars", lambda ticker: None)
    seed_store("plans", [_partial_record()])
    assert logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close").status_code == 200
    plan = PlanStore().get(_PLAN_ID)
    assert plan.status == "CLOSED" and plan.runner_path is None


def test_an_unreadable_cache_still_closes(logged_in, monkeypatch):
    def boom(ticker):
        raise OSError("bad csv")

    monkeypatch.setattr(rp, "cached_daily_bars", boom)
    seed_store("plans", [_partial_record()])
    assert logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close").status_code == 200
    plan = PlanStore().get(_PLAN_ID)
    assert plan.status == "CLOSED" and plan.runner_path is None
