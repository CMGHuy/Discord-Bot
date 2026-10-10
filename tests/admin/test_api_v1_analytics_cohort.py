"""v144: GET /api/v1/analytics/cohort and the origin scope on a pooled route."""
import pytest

from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict, record_transition
from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trades import _trade
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(admin_app, client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _book():
    filled = _plan(plan_id="o1", origin="next_session", valid_session="2026-10-12", entry_type="stop_entry")
    record_transition(filled, PlanStatus.ACTIVE, reason="stop_entry_fill", at="2026-10-12T14:00:00+00:00")
    missed = _plan(plan_id="o2", origin="next_session", valid_session="2026-10-12", entry_type="stop_entry")
    record_transition(missed, PlanStatus.CANCELLED, reason="never_triggered", at="2026-10-12T20:00:00+00:00")
    regular = _plan(plan_id="r1")
    win = _trade("aaaaaaaaaaaaaaaa", plan_id="o1", status="win")
    win["origin"] = "next_session"
    win["horizon_key"] = "4w"
    regular_win = _trade("bbbbbbbbbbbbbbbb", plan_id="r1", status="win")
    regular_win["horizon_key"] = "4w"
    seed_store("plans", [plan_to_dict(p) for p in (filled, missed, regular)])
    seed_store("trades", [win, regular_win])


def test_requires_auth(client):
    assert_error(client.get("/api/v1/analytics/cohort?origin=next_session"), "auth", 401)


def test_rejects_a_missing_or_unknown_origin(logged_in):
    assert_error(logged_in.get("/api/v1/analytics/cohort"), "invalid", 400)
    assert_error(logged_in.get("/api/v1/analytics/cohort?origin=regular"), "invalid", 400)


def test_reports_the_cohort_alone(logged_in):
    _book()
    body = logged_in.get("/api/v1/analytics/cohort?origin=next_session").get_json()
    assert (body["origin"], body["n"], body["issued"], body["filled"]) == ("next_session", 2, 2, 1)
    assert body["fill_rate_pct"] == 50.0
    assert body["closed"] == 1 and body["win_rate"] == 100.0
    assert body["expectancy_r"] == pytest.approx((108.0 - 101.0) / 6.0)
    assert body["cancel_reasons"] == {"never_triggered": 1}


def test_a_pooled_route_counts_the_regular_lane_unless_asked(logged_in):
    _book()
    assert logged_in.get("/api/v1/analytics/performance").get_json()["n"] == 1
    body = logged_in.get("/api/v1/analytics/performance?origin=next_session").get_json()
    assert body["n"] == 1 and body["scope"]["origin"] == "next_session"
