"""v144: plans.valid_session is a promoted, indexed column with one reason."""
import datetime as dt

from swingbot.core.db import schema
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan


def _row(plan_id, valid_session=None, created_at="2026-10-09T21:30:00+00:00"):
    row = {"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
           "status": PlanStatus.PENDING, "created_at": created_at}
    if valid_session is not None:
        row["valid_session"] = valid_session
    return row


def test_valid_session_is_a_nullable_indexed_promoted_column():
    table = schema.METADATA.tables["plans"]
    assert table.c.valid_session.nullable is True
    assert "valid_session" in schema.promoted_for("plans")
    assert "valid_session" in schema.PROMOTION_REASONS["plans"]
    assert any(index.name == "plans_valid_session_idx" for index in table.indexes)


def test_for_session_returns_only_that_sessions_plans_oldest_first(db_conn):
    repo = PlanRepository()
    repo.insert(_row("late", "2026-10-12", "2026-10-09T21:40:00+00:00"), conn=db_conn)
    repo.insert(_row("early", "2026-10-12", "2026-10-09T21:30:00+00:00"), conn=db_conn)
    repo.insert(_row("other", "2026-10-13"), conn=db_conn)
    repo.insert(_row("regular"), conn=db_conn)
    assert [r["plan_id"] for r in repo.for_session("2026-10-12", conn=db_conn)] == ["early", "late"]


def test_a_regular_row_reads_back_without_the_key(db_conn):
    repo = PlanRepository()
    repo.insert(_row("regular"), conn=db_conn)
    assert "valid_session" not in repo.get("regular", conn=db_conn)


def test_plan_store_for_session_accepts_a_date_or_a_string():
    store = PlanStore()
    store.add(_plan(plan_id="o1", origin="next_session", valid_session="2026-10-12"))
    store.add(_plan(plan_id="r1"))
    assert [p.plan_id for p in store.for_session(dt.date(2026, 10, 12))] == ["o1"]
    assert [p.plan_id for p in store.for_session("2026-10-12")] == ["o1"]
    assert store.get("o1").valid_session == "2026-10-12"
    assert store.get("r1").valid_session is None
