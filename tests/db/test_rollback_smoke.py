"""v220 V220-8: rollback_smoke steps every open plan once and writes nothing."""
from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from swingbot.core.db.repositories.journal import journal_repo
from swingbot.core.db.schema import METADATA
from swingbot.core.infra import rollback_smoke as rs
from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict, record_transition
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan


def _active(pid: str = "A1"):
    plan = _plan(plan_id=pid, entry_type="market", trigger_price=100.0, entry_price=100.0,
                 stop_loss=95.0, tp1=110.0)
    record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    return plan


def _pending(pid: str = "P1", **kw):
    base = dict(plan_id=pid, entry_type="stop_entry", trigger_price=105.0, entry_price=None,
                stop_loss=95.0, tp1=110.0)
    return _plan(**{**base, **kw})


def _journal(trade_id: str, closed_at: str | None) -> dict:
    return dict(trade_id=trade_id, strategy="RSI", outcome=None if closed_at is None else "win",
                closed_at=closed_at, created_at="2026-11-01T10:00:00+00:00", note="")


def _state(engine) -> dict:
    """Row count of every table plus each plans/journal row's updated_at and doc."""
    with engine.connect() as conn:
        counts = {t.name: conn.execute(sa.select(sa.func.count()).select_from(t)).scalar()
                  for t in METADATA.sorted_tables}
        plans = conn.execute(sa.text("SELECT plan_id, status, updated_at, doc FROM plans ORDER BY 1")).all()
        journal = conn.execute(sa.text("SELECT trade_id, updated_at, doc FROM journal_entries ORDER BY 1")).all()
    return {"counts": counts, "plans": [tuple(r) for r in plans], "journal": [tuple(r) for r in journal]}


class _Stub:
    def __init__(self, error: Exception | None = None):
        self.error, self.calls = error, []

    def _step(self, plan, price, now=None):
        self.calls.append((plan.plan_id, price))
        if self.error:
            raise self.error
        return []


def _seed():
    store = PlanStore()
    store.add(_active("A1"))
    store.add(_pending("P1"))
    store.add(_plan(plan_id="C1", status=PlanStatus.CLOSED))
    journal_repo().upsert(_journal("T-open", None))
    journal_repo().upsert(_journal("T-closed", "2026-11-02T10:00:00+00:00"))


def test_main_steps_every_open_plan_and_writes_nothing(db_engine, capsys):
    _seed()
    before = _state(db_engine)
    assert rs.main([]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (out["plans"], out["journal"], out["steps"]) == (2, 1, 2)
    assert out["errors"] == [] and out["unknown"] == []
    assert set(out["attempted"]) <= {"A1", "P1"}
    assert _state(db_engine) == before


def test_unknown_entry_type_fails_main_and_still_writes_nothing(db_engine, capsys):
    PlanStore().add(_pending("P9", entry_type="bracket"))
    before = _state(db_engine)
    assert rs.main([]) == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["unknown"] == ["P9: entry_type=bracket"] and out["steps"] == 0
    assert _state(db_engine) == before


def test_read_only_session_blocks_writes_and_is_lifted_after(db_engine):
    with rs.read_only_session():
        with pytest.raises(sa.exc.DBAPIError):
            PlanStore().add(_active("X1"))
    assert PlanStore().get("X1") is None
    PlanStore().add(_active("X2"))
    assert PlanStore().get("X2") is not None


def test_read_only_store_absorbs_every_write(db_engine):
    PlanStore().add(_active("A1"))
    store = rs.ReadOnlyPlanStore()
    plan = store.get("A1")
    plan.working_stop = 99.0
    assert store.update(plan) is True
    store.add(plan)
    assert store.lock_for_update("A1", conn=None).plan_id == "A1"
    assert store.attempted == ["A1", "A1", "A1"]
    assert PlanStore().get("A1").working_stop is None
    assert [p.plan_id for p in store.open_plans()] == ["A1"]


def test_unknown_direction_is_reported_and_not_stepped():
    record = plan_to_dict(_active("A1"))
    record["direction"] = "sideways"
    stub = _Stub()
    result = rs.evaluate([record], [], manager_factory=lambda store: stub)
    assert result["unknown"] == ["A1: direction=sideways"] and result["steps"] == 0 and stub.calls == []


def test_step_exception_is_an_error_and_the_price_is_the_entry():
    stub = _Stub(KeyError("boom"))
    result = rs.evaluate([plan_to_dict(_active("A1"))], [], manager_factory=lambda store: stub)
    assert stub.calls == [("A1", 100.0)]
    assert result["errors"] and result["errors"][0].startswith("A1: KeyError") and result["steps"] == 0


def test_pending_plan_steps_at_its_trigger_and_a_priceless_plan_is_an_error():
    stub = _Stub()
    good = plan_to_dict(_pending("P1"))
    bad = plan_to_dict(_pending("P2", trigger_price=0.0))
    result = rs.evaluate([good, bad], [{"trade_id": "T1"}, {}], manager_factory=lambda store: stub)
    assert stub.calls == [("P1", 105.0)] and result["steps"] == 1
    assert any(e.startswith("P2: ValueError") for e in result["errors"])
    assert "journal row without trade_id" in result["errors"]
    assert (result["plans"], result["journal"]) == (2, 2)


def test_load_failure_is_one_failed_json_line(monkeypatch, capsys):
    def boom():
        raise RuntimeError("db is down")
    monkeypatch.setattr(rs, "_open_journal_rows", boom)
    assert rs.main([]) == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["errors"] == ["load: RuntimeError: db is down"] and out["steps"] == 0
