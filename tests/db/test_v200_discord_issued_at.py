"""v200_001: stamp exactly the pinned Discord issue times, refusing before any write."""
from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import logging
import pathlib
import re
import types

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

REPO = pathlib.Path(__file__).resolve().parents[2]
REVISION_FILE = (REPO / "swingbot" / "core" / "db" / "migrations" / "versions"
                 / "v200_001_discord_issued_at.py")
DRY_RUN = REPO / "docs" / "superpowers" / "results" / "2026-10-29-v200-backfill-dry-run.md"


def _load_revision():
    spec = importlib.util.spec_from_file_location("v200_001_discord_issued_at", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIG = _load_revision()
PINS = {"p-1": "2026-08-03T21:10:00+00:00", "p-2": "2026-08-04T13:40:00+00:00"}


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeConn:
    """`plans` maps plan_id -> doc (a dict), like the jsonb doc column."""

    def __init__(self, plans):
        self.plans = plans
        self.select_sql = None
        self.selected_ids = None
        self.updates = []

    def execute(self, statement, params):
        sql = str(statement).strip()
        if sql.upper().startswith("SELECT"):
            self.select_sql, self.selected_ids = sql, list(params["ids"])
            return _Result([(pid, doc.get("issued_at"), doc.get("issued_at_source"))
                            for pid, doc in self.plans.items() if pid in params["ids"]])
        assert sql.upper().startswith("UPDATE PLANS"), sql
        doc = self.plans[params["plan_id"]]
        if "jsonb_build_object" in sql:
            doc.update(issued_at=params["issued_at"], issued_at_source="discord")
        else:
            doc.pop("issued_at", None)
            doc.pop("issued_at_source", None)
        self.updates.append(params["plan_id"])
        return _Result([])


def _book(pins=PINS, **extra):
    book = {pid: {"ticker": "AAA", "status": "CLOSED"} for pid in pins}
    book.update(extra)
    return book


def test_upgrade_stamps_exactly_the_pinned_plans():
    conn = FakeConn(_book(other={"ticker": "ZZZ"}))
    assert MIG.apply_upgrade(conn, PINS) == 2
    for pid, at in PINS.items():
        assert conn.plans[pid] == {"ticker": "AAA", "status": "CLOSED",
                                   "issued_at": at, "issued_at_source": "discord"}
    assert conn.plans["other"] == {"ticker": "ZZZ"}
    assert sorted(conn.updates) == sorted(PINS)
    assert "FOR UPDATE" in conn.select_sql and conn.selected_ids == list(PINS)


def test_downgrade_removes_both_fields_from_exactly_the_pinned_plans():
    live = {"issued_at": "2026-10-01T13:31:00+00:00", "issued_at_source": "live"}
    conn = FakeConn(_book(other=dict(live)))
    MIG.apply_upgrade(conn, PINS)
    assert MIG.apply_downgrade(conn, PINS) == 2
    for pid in PINS:
        assert conn.plans[pid] == {"ticker": "AAA", "status": "CLOSED"}
    assert conn.plans["other"] == live


def test_a_partial_book_is_refused_before_any_write():
    conn = FakeConn({"p-1": {}})
    with pytest.raises(RuntimeError, match=r"missing.*p-2"):
        MIG.apply_upgrade(conn, PINS)
    assert conn.updates == []


def test_a_pinned_plan_already_carrying_issued_at_is_refused():
    conn = FakeConn(_book(**{"p-2": {"issued_at": "2026-08-04T13:00:00+00:00"}}))
    with pytest.raises(RuntimeError, match=r"already carry issued_at.*p-2"):
        MIG.apply_upgrade(conn, PINS)
    assert conn.updates == []


def test_downgrade_refuses_a_plan_that_is_not_the_pinned_stamp():
    conn = FakeConn(_book())
    MIG.apply_upgrade(conn, PINS)
    conn.plans["p-2"]["issued_at_source"] = "live"
    conn.updates.clear()
    with pytest.raises(RuntimeError, match=r"p-2"):
        MIG.apply_downgrade(conn, PINS)
    assert conn.updates == []


def test_a_book_without_any_pinned_plan_is_a_logged_no_op(caplog):
    conn = FakeConn({"other": {}})
    with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
        assert MIG.apply_upgrade(conn, PINS) == 0
        assert MIG.apply_downgrade(conn, PINS) == 0
    assert conn.updates == []
    assert "none of the 2 pinned plans" in caplog.text


def test_the_pure_steps_never_mutate_their_input():
    docs = {pid: {"issued_at": None, "issued_at_source": None} for pid in PINS}
    before = copy.deepcopy(docs)
    assert MIG.stamp(docs, PINS) == {pid: {"issued_at": at, "issued_at_source": "discord"}
                                     for pid, at in PINS.items()}
    assert docs == before


def test_upgrade_and_downgrade_run_on_the_alembic_bind(monkeypatch):
    conn = FakeConn(_book(MIG.PINNED_ISSUED_AT))
    monkeypatch.setattr(MIG, "op", types.SimpleNamespace(get_bind=lambda: conn))
    MIG.upgrade()
    assert all(conn.plans[p]["issued_at_source"] == "discord" for p in MIG.PINNED_ISSUED_AT)
    MIG.downgrade()
    assert all("issued_at" not in conn.plans[p] for p in MIG.PINNED_ISSUED_AT)


def test_the_revision_writes_only_the_two_fields():
    assert set(re.findall(r"'(\w+)'", str(MIG._STAMP))) == {"issued_at", "issued_at_source", "discord"}
    assert set(re.findall(r"'(\w+)'", str(MIG._UNSTAMP))) == {"issued_at", "issued_at_source"}


def test_the_pinned_mapping_is_well_formed_and_matches_the_dry_run():
    pins = MIG.PINNED_ISSUED_AT
    assert pins
    for pid, at in pins.items():
        assert re.fullmatch(r"[0-9a-f-]{36}", pid), pid
        stamp = dt.datetime.fromisoformat(at)
        assert stamp.utcoffset() == dt.timedelta(0), pid
        assert dt.date(2026, 7, 1) <= stamp.date() <= dt.date(2026, 9, 18), pid
    matched = re.search(r"Matched: (\d+) of", DRY_RUN.read_text(encoding="utf-8"))
    assert matched and int(matched.group(1)) == len(pins)


@pytest.fixture(scope="module")
def scripts():
    return ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))


def test_v200_001_sits_on_v201_001_and_is_the_single_head(scripts):
    assert (MIG.revision, MIG.down_revision) == ("v200_001", "v201_001")
    assert scripts.get_revision("v200_001").down_revision == "v201_001"
    assert len(scripts.get_heads()) == 1    # v204_001 now sits on top; its test pins the head
