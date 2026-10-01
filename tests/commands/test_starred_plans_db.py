"""Starred plans preserve their set semantics in the starred_plans table."""
from swingbot.commands import views
from swingbot.core.db.repositories.starred import StarredRepository
from swingbot.core.db.repositories.plans import PlanRepository


def _seed_plans(*plan_ids):
    for plan_id in plan_ids:
        PlanRepository().upsert({"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI",
                                 "horizon_key": "2w", "status": "PENDING",
                                 "created_at": "2026-01-02T15:00:00+00:00"})


def test_star_writes_a_row_and_reads_it_back():
    _seed_plans("P1")
    views.star_plan("P1")
    assert views.starred_ids() == {"P1"}
    assert StarredRepository().ids() == {"P1"}


def test_star_and_unstar_are_idempotent():
    _seed_plans("P1")
    views.star_plan("P1")
    views.star_plan("P1")
    assert StarredRepository().count() == 1
    views.unstar_plan("P1")
    views.unstar_plan("P1")
    assert views.starred_ids() == set()
