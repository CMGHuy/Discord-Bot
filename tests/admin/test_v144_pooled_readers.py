"""v144: the plan-reading pooled figures (soak verdict, plan funnel) skip outlook plans."""
import pytest

from swingbot.core.planning.plan_engine import plan_to_dict
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(admin_app, client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _plans():
    return [_plan(plan_id="r1", source="strategy", strategy="MACD"),
            _plan(plan_id="o1", source="strategy", strategy="MACD", origin="next_session",
                  valid_session="2026-10-12")]


def test_soak_reads_regular_plans_only(admin_app, monkeypatch):
    seed_store("plans", [plan_to_dict(p) for p in _plans()])
    seen = {}
    monkeypatch.setattr("swingbot.core.edge.strategy_soak.soak_verdict",
                        lambda plans, badge: seen.setdefault("ids", [p.plan_id for p in plans]))
    from swingbot.admin.api_v1.analytics import _soak_for
    _soak_for("MACD")
    assert seen["ids"] == ["r1"]


def test_plan_funnel_reads_regular_plans_only(logged_in, monkeypatch):
    seed_store("plans", [plan_to_dict(p) for p in _plans()])
    seen = {}
    monkeypatch.setattr("swingbot.admin.queries._plan_lifecycle",
                        lambda plans: seen.setdefault("ids", sorted(p.plan_id for p in plans)) and {})
    assert logged_in.get("/api/v1/analytics/plans").status_code == 200
    assert seen["ids"] == ["r1"]
