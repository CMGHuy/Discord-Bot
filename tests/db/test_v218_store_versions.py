"""v218 V218-1: version() twins for trades and journal, and the stamp gap.

`(count, max(updated_at))` is a cheap change token, but the stamp is taken
before commit (`clock_timestamp()` in upsert/patch, `now()` in insert), so a
transaction that commits after a concurrent one can land under an older stamp
and leave the token unchanged. The gap tests below reproduce that on two real
connections; V218-6 adds the NOTIFY generation to the existing callers' keys."""
import time

import pytest

from swingbot.core.db.repositories.journal import JournalRepository
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.trades import TradeRepository


def _trade(trade_id, **overrides):
    trade = {"trade_id": trade_id, "ticker": "MSFT", "strategy": "swing", "horizon": "swing",
             "direction": "long", "status": "open", "opened_at": "2026-01-02T15:00:00+00:00"}
    trade.update(overrides)
    return trade


def _plan(plan_id, **overrides):
    plan = {"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "status": "PENDING", "created_at": "2026-01-02T15:00:00+00:00",
            "entry": 100.0, "stop_loss": 95.0}
    plan.update(overrides)
    return plan


def _entry(trade_id, **overrides):
    entry = {"trade_id": trade_id, "strategy": "RSI", "outcome": "win",
             "closed_at": "2026-01-09T15:00:00+00:00", "created_at": "2026-01-09T16:00:00+00:00",
             "tags": [], "note": "", "lesson": ""}
    entry.update(overrides)
    return entry


@pytest.mark.parametrize("repo_cls, make", [(TradeRepository, _trade), (JournalRepository, _entry)])
def test_version_is_count_and_newest_stamp_and_moves_on_every_write(repo_cls, make, db_conn):
    repo = repo_cls()
    assert repo.version(conn=db_conn) == (0, None)
    repo.insert(make("A"), conn=db_conn)
    inserted = repo.version(conn=db_conn)
    assert inserted[0] == 1 and isinstance(inserted[1], str)
    repo.upsert(make("A", strategy="changed"), conn=db_conn)
    updated = repo.version(conn=db_conn)
    repo.delete("A", conn=db_conn)
    assert inserted != updated                          # clock_timestamp() moved inside one tx
    assert repo.version(conn=db_conn) == (0, None)


def test_version_shape_matches_the_plans_twin(db_conn):
    PlanRepository().insert(_plan("P1"), conn=db_conn)
    TradeRepository().insert(_trade("T1"), conn=db_conn)
    JournalRepository().insert(_entry("T1"), conn=db_conn)
    shapes = [type(part) for repo in (PlanRepository(), TradeRepository(), JournalRepository())
              for part in repo.version(conn=db_conn)]
    assert shapes == [int, str] * 3


def _version(engine, repo):
    with engine.begin() as connection:
        return repo.version(conn=connection)


def _gap(engine, repo, make, changed):
    """Commit X's change under an older stamp than Y's; return (after_y, after_x)."""
    with engine.begin() as connection:
        repo.insert(make("X"), conn=connection)
        repo.insert(make("Y"), conn=connection)
    slow = engine.connect()
    slow_tx = slow.begin()
    try:
        repo.upsert(make("X", **changed), conn=slow)     # stamped now, not yet committed
        time.sleep(0.01)
        with engine.begin() as fast:
            repo.upsert(make("Y", **changed), conn=fast)  # later stamp, commits first
        after_y = _version(engine, repo)
        slow_tx.commit()                                 # X commits under the OLDER stamp
    finally:
        slow.close()
    return after_y, _version(engine, repo)


def test_trades_version_misses_a_commit_stamped_before_a_concurrent_one(db_engine, db_committed):
    repo = TradeRepository()
    after_y, after_x = _gap(db_engine, repo, _trade, {"status": "win"})
    with db_engine.begin() as connection:
        assert repo.get("X", conn=connection)["status"] == "win"      # X really changed
    assert after_x == after_y                                         # ...and the token did not move


def test_plans_version_has_the_same_gap_the_existing_callers_rely_on(db_engine, db_committed):
    """cancel_precision._memo_key and watchlist_rows._plans_signature key on this."""
    repo = PlanRepository()
    after_y, after_x = _gap(db_engine, repo, _plan, {"status": "ACTIVE"})
    with db_engine.begin() as connection:
        assert repo.get("X", conn=connection)["status"] == "ACTIVE"
    assert after_x == after_y
