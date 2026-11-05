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
    from tests.db_diff import diff_records
    record = _plan("P1", legs=[{"fraction": 0.5, "r": 1.0}], take_profit=110.0,
                   confidence={"level": 4, "score": 71}, notified_stop=101.5,
                   issued_at="2026-09-15T14:31:07+00:00",
                   pending_notice={"transition": "closed", "detail": {"reason": "loss"}})
    repo.insert(record, conn=db_conn)
    assert diff_records(record, repo.get("P1", conn=db_conn)) == []


def test_version_moves_on_insert_update_and_delete(repo, db_conn):
    empty = repo.version(conn=db_conn)
    assert empty == (0, None)
    repo.insert(_plan("P1"), conn=db_conn)
    inserted = repo.version(conn=db_conn)
    repo.upsert(_plan("P1", status=PlanStatus.ACTIVE), conn=db_conn)
    updated = repo.version(conn=db_conn)
    repo.delete("P1", conn=db_conn)
    assert len({empty, inserted, updated, repo.version(conn=db_conn)}) >= 3
    assert inserted != updated


def test_v129_acceptance_fields_ride_in_the_doc(repo, db_conn):
    """v129 used schema-evolution's ADD path: no column, no revision -- the
    two fields live in plans.doc and must survive the repository."""
    from tests.db_diff import diff_records
    record = _plan("P1", acceptance_level=97.5, acceptance_close_below=97.0)
    repo.insert(record, conn=db_conn)
    assert diff_records(record, repo.get("P1", conn=db_conn)) == []


def test_v139_stop_ceiling_pct_rides_in_the_doc(repo, db_conn):
    """v139 used schema-evolution's ADD path: no column, no revision -- the
    arm S ceiling lives in plans.doc and must survive the repository."""
    from tests.db_diff import diff_records
    record = _plan("P1", source="confluence", stop_ceiling_pct=4.0)
    repo.insert(record, conn=db_conn)
    assert diff_records(record, repo.get("P1", conn=db_conn)) == []


def test_v192_reclaim_fields_ride_in_the_doc(repo, db_conn):
    """The next-open stamps survive plans.doc and reload as a TradePlanV2."""
    from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
    from tests.db_diff import diff_records
    from tests.planning.test_plan_engine_model import _plan as model_plan

    record = plan_to_dict(model_plan(plan_id="P192", reclaim_atr=1.2345, reclaim_level=99.69,
                                     reclaim_session="2026-10-26", waits_next_open=True))
    record["created_at"] = "2026-10-26T14:00:00+00:00"   # the store stamps one when absent
    repo.insert(record, conn=db_conn)
    stored = repo.get("P192", conn=db_conn)
    assert diff_records(record, stored) == []
    plan = plan_from_dict(stored)
    assert (plan.reclaim_atr, plan.reclaim_level, plan.reclaim_session, plan.waits_next_open) == (
        1.2345, 99.69, "2026-10-26", True)


def test_v192_plan_without_the_fields_stores_no_key(repo, db_conn):
    from swingbot.core.planning.plan_types import plan_to_dict
    from tests.planning.test_plan_engine_model import _plan as model_plan

    repo.insert(plan_to_dict(model_plan(plan_id="P0")), conn=db_conn)
    stored = repo.get("P0", conn=db_conn)
    assert not {"reclaim_atr", "reclaim_level", "reclaim_session", "waits_next_open"} & set(stored)
