"""v147: the append-only live gate-counterfactual store."""
import datetime as dt

import pytest

from swingbot.core.db import events
from swingbot.core.db.repositories import gate_rejections as store
from swingbot.core.db.repositories.gate_rejections import GateRejectionRepository

CREATED = "2026-10-05T20:00:00+00:00"


def _record(**over):
    base = {"ticker": "AAPL", "gate": "rs", "strategy": "RSI", "horizon": "2w",
            "signal_date": "2026-10-05", "cf_status": "pending", "created_at": CREATED,
            "reason": "rs_blocked", "margin": -3.5, "direction": "bearish", "source": "strategy",
            "plan": None, "scenario": None, "scan_params": {"stop_mult": 1.5}, "signal_close": 101.25,
            "entry_context": {}, "heat_before": None, "heat_cap": None}
    return {**base, **over}


@pytest.fixture
def repo():
    return GateRejectionRepository()


def test_a_second_insert_of_the_same_key_is_a_no_op(repo, db_conn):
    assert repo.insert_ignore(_record(), conn=db_conn) is True
    assert repo.insert_ignore(_record(margin=-1.0), conn=db_conn) is False
    (row,) = repo.list_since(conn=db_conn)
    assert row["margin"] == -3.5                                   # the first write wins


def test_one_ticker_gate_strategy_and_day_on_two_horizons_is_two_rows(repo, db_conn):
    assert repo.insert_ignore(_record(horizon="2w"), conn=db_conn)
    assert repo.insert_ignore(_record(horizon="4w"), conn=db_conn)
    assert repo.count(conn=db_conn) == 2


def test_doc_fields_round_trip_and_null_heat_keys_stay_present(repo, db_conn):
    repo.insert_ignore(_record(), conn=db_conn)
    (row,) = repo.list_since(conn=db_conn)
    assert isinstance(row["id"], int)
    assert row["scan_params"] == {"stop_mult": 1.5} and row["signal_close"] == 101.25
    assert "heat_before" in row and row["heat_before"] is None
    assert "heat_cap" in row and row["heat_cap"] is None


def test_pending_is_oldest_first_limited_and_carries_ids(repo, db_conn):
    for day, ticker in ((7, "C"), (5, "A"), (6, "B")):
        repo.insert_ignore(_record(ticker=ticker, signal_date=f"2026-10-0{day}",
                                   created_at=f"2026-10-0{day}T20:00:00+00:00"), conn=db_conn)
    repo.insert_ignore(_record(ticker="D", cf_status="no-plan"), conn=db_conn)
    rows = repo.pending(limit=2, conn=db_conn)
    assert [row["ticker"] for row in rows] == ["A", "B"]
    assert all(isinstance(row["id"], int) for row in rows)


def test_resolve_fills_the_outcome_once(repo, db_conn):
    repo.insert_ignore(_record(), conn=db_conn)
    (row,) = repo.pending(limit=10, conn=db_conn)
    outcome = {"cf_r": 1.25, "win": True, "exit_index": 9, "last_bar_date": "2026-10-20",
               "bars_sha256": "ab" * 32, "reanchored": False}
    resolved_at = dt.datetime(2026, 10, 21, 20, 45, tzinfo=dt.timezone.utc)
    assert repo.resolve(row["id"], cf_status="filled", resolved_at=resolved_at, outcome=outcome, conn=db_conn)
    assert repo.resolve(row["id"], cf_status="no-data", resolved_at=resolved_at,
                        outcome={"cf_r": None}, conn=db_conn) is False          # never re-resolved
    stored = repo.get(row["id"], conn=db_conn)
    assert stored["cf_status"] == "filled" and stored["resolved_at"] == resolved_at
    assert {key: stored[key] for key in outcome} == outcome
    assert stored["reason"] == "rs_blocked"                                      # the snapshot survives
    assert repo.pending(limit=10, conn=db_conn) == []


def test_a_grace_bump_keeps_the_row_pending(repo, db_conn):
    repo.insert_ignore(_record(), conn=db_conn)
    (row,) = repo.pending(limit=10, conn=db_conn)
    assert repo.resolve(row["id"], cf_status="pending", resolved_at=None,
                        outcome={"pending_checks": 1}, conn=db_conn)
    (still,) = repo.pending(limit=10, conn=db_conn)
    assert still["pending_checks"] == 1 and "resolved_at" not in still


def test_resolve_refuses_promoted_keys_and_unknown_statuses(repo, db_conn):
    repo.insert_ignore(_record(), conn=db_conn)
    (row,) = repo.pending(limit=10, conn=db_conn)
    with pytest.raises(ValueError):
        repo.resolve(row["id"], cf_status="filled", resolved_at=CREATED, outcome={"ticker": "X"}, conn=db_conn)
    with pytest.raises(ValueError):
        repo.resolve(row["id"], cf_status="won", resolved_at=CREATED, outcome={}, conn=db_conn)
    with pytest.raises(ValueError):
        repo.insert_ignore(_record(cf_status="done"), conn=db_conn)


def test_list_since_filters_on_created_at(repo, db_conn):
    repo.insert_ignore(_record(ticker="OLD", created_at="2026-09-30T20:00:00+00:00"), conn=db_conn)
    repo.insert_ignore(_record(ticker="NEW", created_at="2026-10-01T20:00:00+00:00"), conn=db_conn)
    assert [row["ticker"] for row in repo.list_since("2026-10-01", conn=db_conn)] == ["NEW"]
    assert [row["ticker"] for row in repo.list_since(conn=db_conn)] == ["OLD", "NEW"]


def test_statuses_mirror_the_simulator_and_the_table_raises_no_event():
    from swingbot.core.backtesting.gate_counterfactual import CF_STATUSES
    assert store.CF_STATUSES == CF_STATUSES
    assert "gate_rejections" not in events.TABLE_CHANNELS


def test_the_singleton_is_lazy_and_shared():
    assert store.gate_rejections_repo() is store.gate_rejections_repo()
