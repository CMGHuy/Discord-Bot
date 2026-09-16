"""A star cannot outlive the plan it identifies."""
import pytest
import sqlalchemy as sa

from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.starred import StarredRepository


def _plan(plan_id="P1"):
    return {"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "status": "PENDING", "created_at": "2026-01-02T15:00:00+00:00"}


def test_starring_an_existing_plan_works(db_conn):
    PlanRepository().insert(_plan(), conn=db_conn)
    StarredRepository().star("P1", conn=db_conn)
    assert StarredRepository().ids(conn=db_conn) == {"P1"}


def test_starring_a_missing_plan_is_rejected(db_conn):
    with pytest.raises(sa.exc.IntegrityError):
        StarredRepository().star("GHOST", conn=db_conn)


def test_deleting_a_plan_removes_its_star(db_conn):
    PlanRepository().insert(_plan(), conn=db_conn)
    StarredRepository().star("P1", conn=db_conn)
    PlanRepository().delete("P1", conn=db_conn)
    assert StarredRepository().ids(conn=db_conn) == set()
