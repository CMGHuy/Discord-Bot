"""Flags are set/absent, like their .flag predecessors."""
import pytest
from swingbot.core.db.repositories.flags import FLAGS, FlagRepository

@pytest.fixture
def repo():
    return FlagRepository()

def test_flag_names_are_fixed():
    assert FLAGS == ("scan_running", "scan_paused", "trigger_check", "stop_scan")

def test_set_clear_and_unknown(repo, db_conn):
    assert not repo.is_set("scan_running", conn=db_conn)
    repo.set("scan_running", conn=db_conn)
    repo.set("scan_running", conn=db_conn)
    assert repo.is_set("scan_running", conn=db_conn) and repo.count(conn=db_conn) == 1
    repo.clear("scan_running", conn=db_conn)
    assert not repo.is_set("scan_running", conn=db_conn)
    with pytest.raises(ValueError, match="not a known flag"):
        repo.set("typo", conn=db_conn)
