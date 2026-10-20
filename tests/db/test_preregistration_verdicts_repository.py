"""v173: PreregistrationVerdictRepository -- a verdict is written once, keyed by
ledger_id; a second insert writes nothing and never updates; the record reads
back exactly, with recorded_on as ISO text."""
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from swingbot.core.db.repositories.preregistration_verdicts import (
    PreregistrationVerdictRepository, verdict_repo)

LEDGER_ID = "v173-override-fidelity"


@pytest.fixture
def repo():
    return PreregistrationVerdictRepository()


def _record(verdict="COST", *, recorded_on="2026-12-04", mean=-0.212):
    return {"ledger_id": LEDGER_ID, "verdict": verdict, "recorded_on": recorded_on,
            "n": 31, "weeks": 12, "mean_delta_r": mean, "mean_delta_r_gross": -0.187,
            "ci": [-0.401, -0.033], "sum_delta_r": -6.572, "sum_delta_usd": -1314.4,
            "bar_close_n": 2, "excluded_share": 0.114,
            "engine_flags": {"stall_exit_enabled": True, "runner_structure_exit": "off"},
            "engine_config": {"STALL_EXIT_ENABLED": True, "RUNNER_HL_TRAIL_ATR_BUFFER": 0.0,
                              "STRUCTURAL_STOP_SCOPE": "",
                              "exit_sim.GIVEBACK_EXTREME_BASIS": "close"},
            "engine_config_sha256": "ab" * 32, "asof": "2026-12-04",
            "bars_last_date": {"AAPL": "2026-12-04", "MSFT": None},
            "rows": [{"plan_id": "p1", "delta_r": -0.5, "close_date": "2026-09-01",
                      "bars_sha256": "cd" * 32},
                     {"plan_id": "p2", "delta_r": 0.25, "close_date": "2026-09-09",
                      "bars_sha256": None}]}


def test_the_first_insert_writes_the_row(repo, db_conn):
    assert repo.insert_once(_record(), conn=db_conn) is True
    row = db_conn.execute(sa.text(
        "SELECT ledger_id, verdict, recorded_on, doc->>'n' AS n FROM preregistration_verdicts"
    )).one()
    assert (row.ledger_id, row.verdict, row.recorded_on, row.n) == (
        LEDGER_ID, "COST", date(2026, 12, 4), "31")


def test_a_second_insert_on_the_same_ledger_id_writes_nothing_and_keeps_the_first(repo, db_conn):
    assert repo.insert_once(_record(), conn=db_conn) is True
    later = _record("SAVED", recorded_on="2026-12-11", mean=0.4)
    assert repo.insert_once(later, conn=db_conn) is False
    assert repo.recorded(LEDGER_ID, conn=db_conn) == _record()
    count = db_conn.execute(sa.text("SELECT count(*) FROM preregistration_verdicts")).scalar_one()
    assert count == 1


def test_recorded_round_trips_the_record_with_recorded_on_as_iso_text(repo, db_conn):
    repo.insert_once(_record(recorded_on=date(2026, 12, 4)), conn=db_conn)
    stored = repo.recorded(LEDGER_ID, conn=db_conn)
    assert stored == _record()                     # recorded_on back as "2026-12-04"
    assert isinstance(stored["recorded_on"], str)
    assert stored["ci"] == [-0.401, -0.033] and stored["rows"][1]["delta_r"] == 0.25


def test_recorded_is_none_when_no_row_exists(repo, db_conn):
    assert repo.recorded(LEDGER_ID, conn=db_conn) is None
    assert repo.recorded("v999-other", conn=db_conn) is None


def test_a_plain_second_insert_fails_on_the_primary_key(repo, db_conn):
    repo.insert_once(_record(), conn=db_conn)
    savepoint = db_conn.begin_nested()
    with pytest.raises(IntegrityError):
        db_conn.execute(sa.text(
            "INSERT INTO preregistration_verdicts (ledger_id, verdict, recorded_on) "
            "VALUES (:id, 'SAVED', DATE '2026-12-11')"), {"id": LEDGER_ID})
    savepoint.rollback()
    assert repo.recorded(LEDGER_ID, conn=db_conn)["verdict"] == "COST"


@pytest.mark.parametrize("bad", [
    {"ledger_id": ""}, {"ledger_id": None}, {"verdict": ""},
    {"recorded_on": "04.12.2026"}, {"recorded_on": None},
])
def test_a_malformed_record_is_refused_before_any_sql(repo, bad):
    with pytest.raises(ValueError):
        repo.insert_once({**_record(), **bad}, conn=object())   # a fake conn: never reached


def test_no_code_path_updates_or_plain_inserts_a_verdict(repo):
    with pytest.raises(TypeError):
        repo.upsert(_record())
    with pytest.raises(TypeError):
        repo.insert(_record())


def test_verdict_repo_is_one_shared_instance():
    assert verdict_repo() is verdict_repo()
    assert isinstance(verdict_repo(), PreregistrationVerdictRepository)
