"""PlanRepository keeps PlanStore's status semantics and full documents."""
import pytest

from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.planning.plan_engine import PlanStatus


@pytest.fixture
def repo():
    return PlanRepository()


def _plan(plan_id, status=PlanStatus.PENDING, **overrides):
    row = {"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
           "status": status, "created_at": "2026-01-02T15:00:00+00:00",
           "entry": 100.0, "stop_loss": 95.0}
    row.update(overrides)
    return row


def test_open_plans_covers_pending_active_and_partial(repo, db_conn):
    for index, status in enumerate((PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL)):
        repo.insert(_plan(f"P{index}", status=status), conn=db_conn)
    repo.insert(_plan("CLOSED", status=PlanStatus.CLOSED), conn=db_conn)
    assert {row["plan_id"] for row in repo.open_plans(conn=db_conn)} == {"P0", "P1", "P2"}


def test_open_statuses_are_plan_store_statuses(repo):
    from swingbot.core.planning.plan_store import _OPEN_STATUSES
    assert set(repo.OPEN_STATUSES) == set(_OPEN_STATUSES)


def test_by_ticker_is_case_insensitive(repo, db_conn):
    repo.insert(_plan("P1", ticker="AAPL"), conn=db_conn)
    repo.insert(_plan("P2", ticker="MSFT"), conn=db_conn)
    assert [row["plan_id"] for row in repo.by_ticker("aapl", conn=db_conn)] == ["P1"]


def test_full_plan_document_round_trips(repo, db_conn):
    from swingbot.core.db.dual import diff_records
    record = _plan("P1", legs=[{"fraction": 0.5, "r": 1.0}], take_profit=110.0,
                   confidence={"level": 4, "score": 71}, notified_stop=101.5,
                   issued_at="2026-09-15T14:31:07+00:00",
                   pending_notice={"transition": "closed", "detail": {"reason": "loss"}})
    repo.insert(record, conn=db_conn)
    assert diff_records(record, repo.get("P1", conn=db_conn)) == []
