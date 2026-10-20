"""v173_001: re-tag exactly the 15 pinned 2026-09-30 bulk-clear closes as
manual_bulk, refusing before any write on a missing id or a mismatch.

The revision's logic is pure (`retag`, `apply` over a connection seam), so
every test here runs on a fake connection: no database, never the
production replica."""
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import types

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

REPO = pathlib.Path(__file__).resolve().parents[2]
REVISION_FILE = (REPO / "swingbot" / "core" / "db" / "migrations" / "versions"
                 / "v173_001_manual_bulk_retag.py")
BULK_AT = "2026-09-30T20:54:31+00:00"


def _load_revision():
    spec = importlib.util.spec_from_file_location("v173_001_manual_bulk_retag", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIG = _load_revision()
PINNED = MIG.PINNED_PLAN_IDS


def _history(reason="manual", *, partial=False):
    history = [{"status": "ACTIVE", "reason": "filled", "at": "2026-09-22T14:00:00+00:00"}]
    if partial:
        history.append({"status": "PARTIAL", "reason": "tp1_partial", "at": "2026-09-25T15:00:00+00:00"})
    history.append({"status": "CLOSED", "reason": reason, "at": BULK_AT})
    return history


def _book(reason="manual"):
    return {pid: _history(reason, partial=i % 2 == 1) for i, pid in enumerate(PINNED)}


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeConn:
    """`plans` maps plan_id -> status_history (a list), like the doc column."""

    def __init__(self, plans):
        self.plans = plans
        self.selected_ids = None
        self.select_sql = None
        self.updates = []

    def execute(self, statement, params):
        sql = str(statement).strip()
        if sql.upper().startswith("SELECT"):
            self.select_sql = sql
            self.selected_ids = list(params["ids"])
            return _Result([(pid, copy.deepcopy(hist)) for pid, hist in self.plans.items()
                            if pid in params["ids"]])
        assert sql.upper().startswith("UPDATE PLANS"), sql
        history = json.loads(params["hist"])
        self.updates.append(params["plan_id"])
        self.plans[params["plan_id"]] = history
        return _Result([])


# --- the pinned ids -------------------------------------------------------------

def test_exactly_fifteen_unique_pinned_plan_ids():
    assert len(PINNED) == 15
    assert len(set(PINNED)) == 15
    assert all(isinstance(pid, str) and len(pid) == 36 and pid.count("-") == 4 for pid in PINNED)


# --- retag (pure) ---------------------------------------------------------------

def test_retag_changes_only_the_terminal_reason():
    book = _book()
    out = MIG.retag(book, frm="manual", to="manual_bulk")
    assert set(out) == set(PINNED)
    for pid in PINNED:
        assert out[pid][-1] == {"status": "CLOSED", "reason": "manual_bulk", "at": BULK_AT}
        assert out[pid][:-1] == book[pid][:-1]


def test_retag_never_mutates_its_input():
    book = _book()
    before = copy.deepcopy(book)
    MIG.retag(book, frm="manual", to="manual_bulk")
    assert book == before


def test_retag_keeps_any_other_key_on_the_terminal_entry():
    book = _book()
    book[PINNED[0]][-1]["note"] = "kept"
    out = MIG.retag(book, frm="manual", to="manual_bulk")
    assert out[PINNED[0]][-1]["note"] == "kept"


def test_retag_refuses_a_missing_pinned_id():
    book = _book()
    del book[PINNED[3]]
    with pytest.raises(RuntimeError, match=PINNED[3]):
        MIG.retag(book, frm="manual", to="manual_bulk")


@pytest.mark.parametrize("terminal", [
    {"status": "CLOSED", "reason": "manual_bulk", "at": BULK_AT},     # already changed
    {"status": "CLOSED", "reason": "tp1_runner_trail", "at": BULK_AT},
    {"status": "CANCELLED", "reason": "manual", "at": BULK_AT},
])
def test_retag_refuses_a_terminal_entry_that_is_not_closed_manual(terminal):
    book = _book()
    book[PINNED[5]][-1] = terminal
    with pytest.raises(RuntimeError, match=PINNED[5]):
        MIG.retag(book, frm="manual", to="manual_bulk")


def test_retag_refuses_an_empty_history():
    book = _book()
    book[PINNED[0]] = []
    with pytest.raises(RuntimeError, match=PINNED[0]):
        MIG.retag(book, frm="manual", to="manual_bulk")


# --- apply over a connection -----------------------------------------------------

def test_upgrade_then_downgrade_round_trips_exactly():
    original = _book()
    conn = FakeConn(copy.deepcopy(original))
    assert MIG.apply(conn, frm="manual", to="manual_bulk") == 15
    assert all(conn.plans[pid][-1]["reason"] == "manual_bulk" for pid in PINNED)
    assert MIG.apply(conn, frm="manual_bulk", to="manual") == 15
    assert conn.plans == original


def test_only_pinned_ids_are_read_and_written():
    plans = _book()
    plans["99999999-9999-4999-8999-999999999999"] = _history("manual")   # an individual override
    conn = FakeConn(plans)
    MIG.apply(conn, frm="manual", to="manual_bulk")
    assert set(conn.selected_ids) == set(PINNED)
    assert sorted(conn.updates) == sorted(PINNED)
    assert plans["99999999-9999-4999-8999-999999999999"][-1]["reason"] == "manual"


def test_the_pinned_read_locks_its_rows():
    """The check and the write must see the same 15 rows: FOR UPDATE."""
    assert "FOR UPDATE" in " ".join(str(MIG._SELECT).upper().split())
    conn = FakeConn(_book())
    MIG.apply(conn, frm="manual", to="manual_bulk")
    assert conn.select_sql.upper().rstrip().endswith("FOR UPDATE")


def test_a_mismatch_refuses_before_any_write():
    plans = _book()
    plans[PINNED[-1]][-1]["reason"] = "manual_bulk"
    conn = FakeConn(plans)
    with pytest.raises(RuntimeError):
        MIG.apply(conn, frm="manual", to="manual_bulk")
    assert conn.updates == []


def test_some_but_not_all_pinned_plans_present_refuses_before_any_write():
    plans = _book()
    del plans[PINNED[7]]
    conn = FakeConn(plans)
    with pytest.raises(RuntimeError, match=PINNED[7]):
        MIG.apply(conn, frm="manual", to="manual_bulk")
    assert conn.updates == []


def test_a_database_with_none_of_the_pinned_plans_is_left_alone():
    """A fresh install or the test database: `alembic upgrade head` must pass."""
    conn = FakeConn({"99999999-9999-4999-8999-999999999999": _history("manual")})
    assert MIG.apply(conn, frm="manual", to="manual_bulk") == 0
    assert conn.updates == []


def test_downgrade_refuses_unless_every_pinned_entry_reads_manual_bulk():
    plans = _book("manual_bulk")
    plans[PINNED[2]][-1]["reason"] = "manual"
    conn = FakeConn(plans)
    with pytest.raises(RuntimeError, match=PINNED[2]):
        MIG.apply(conn, frm="manual_bulk", to="manual")
    assert conn.updates == []


def test_upgrade_and_downgrade_run_on_the_alembic_bind(monkeypatch):
    conn = FakeConn(_book())
    monkeypatch.setattr(MIG, "op", types.SimpleNamespace(get_bind=lambda: conn))
    MIG.upgrade()
    assert all(conn.plans[pid][-1]["reason"] == "manual_bulk" for pid in PINNED)
    MIG.downgrade()
    assert all(conn.plans[pid][-1]["reason"] == "manual" for pid in PINNED)


def test_a_history_returned_as_json_text_is_decoded():
    book = _book()
    conn = FakeConn(book)
    real_execute = conn.execute

    def as_text(statement, params):
        result = real_execute(statement, params)
        return _Result([(pid, json.dumps(hist)) for pid, hist in result.fetchall()])

    conn.execute = as_text
    assert MIG.apply(conn, frm="manual", to="manual_bulk") == 15


# --- the revision graph (script directory only) ----------------------------------

@pytest.fixture(scope="module")
def scripts():
    return ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))


def test_v173_001_is_on_the_single_head_chain(scripts):
    """True now (v173_001 is the head) and after V173-24 (v173_002 on top)."""
    assert MIG.revision == "v173_001"
    heads = scripts.get_heads()
    assert len(heads) == 1
    chain = {rev.revision for rev in scripts.iterate_revisions(heads[0], "base")}
    assert "v173_001" in chain


def test_it_chains_onto_an_existing_revision(scripts):
    assert MIG.down_revision == "v172_001"   # re-chained only by V173-17 if main moved
    assert scripts.get_revision(MIG.down_revision) is not None
    assert scripts.get_revision("v173_001").down_revision == MIG.down_revision
