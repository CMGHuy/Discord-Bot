"""V189-6: PlanStore.update locks the row, refuses a stale write over a
terminal plan, and never loosens a stop of an ACTIVE/PARTIAL plan."""
from __future__ import annotations

import logging

import pytest

from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, transaction
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.planning import plan_store as plan_store_module
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan as _model_plan

LOGGER = "swingbot.core.planning.plan_store"


def _bull(**kw):
    base = dict(plan_id="P1", entry_type="market", direction="bullish", trigger_price=100.0,
                entry_price=100.0, stop_loss=95.0, tp1=110.0, status=PlanStatus.ACTIVE)
    base.update(kw)
    return _model_plan(**base)


def _bear(**kw):
    base = dict(plan_id="P1", entry_type="market", direction="bearish", trigger_price=100.0,
                entry_price=100.0, stop_loss=105.0, tp1=90.0, tp2=85.0, status=PlanStatus.ACTIVE)
    base.update(kw)
    return _model_plan(**base)


def _stored(plan_id="P1") -> dict:
    return PlanRepository().get(plan_id)


def test_the_default_timeout_is_the_admin_path():
    assert PlanStore().lock_timeout_ms == ADMIN_LOCK_TIMEOUT_MS
    assert PlanStore(lock_timeout_ms=1000).lock_timeout_ms == 1000


def test_lock_for_update_reads_the_plan_inside_the_callers_transaction():
    PlanStore().add(_bull())
    with transaction() as conn:
        plan = PlanStore().lock_for_update("P1", conn=conn)
        assert plan.plan_id == "P1" and plan.status == PlanStatus.ACTIVE
        assert PlanStore().lock_for_update("MISSING", conn=conn) is None


def test_an_ordinary_write_returns_true_and_lands():
    store = PlanStore()
    store.add(_bull())
    plan = store.get("P1")
    plan.first_seen_price = 101.0
    assert store.update(plan) is True
    assert _stored()["first_seen_price"] == 101.0


def test_an_unknown_plan_still_raises_keyerror():
    with pytest.raises(KeyError):
        PlanStore().update(_bull(plan_id="MISSING"))


@pytest.mark.parametrize("terminal, stale_status", [
    (PlanStatus.CLOSED, PlanStatus.ACTIVE),
    (PlanStatus.CLOSED, PlanStatus.PARTIAL),
    (PlanStatus.CANCELLED, PlanStatus.PENDING),
])
def test_a_stale_write_over_a_terminal_plan_is_refused(caplog, terminal, stale_status):
    store = PlanStore()
    store.add(_bull(status=terminal))
    stale = _bull(status=stale_status, first_seen_price=101.0)
    caplog.set_level(logging.INFO, logger=LOGGER)

    assert store.update(stale) is False

    row = _stored()
    assert row["status"] == terminal
    assert row.get("first_seen_price") is None
    assert (f"plan store: refused stale write to P1 (stored {terminal}, incoming {stale_status})"
            in caplog.text)


def test_the_same_terminal_write_is_allowed():
    store = PlanStore()
    store.add(_bull(status=PlanStatus.CLOSED))
    plan = store.get("P1")
    plan.first_seen_price = 101.0
    assert store.update(plan) is True
    assert _stored()["first_seen_price"] == 101.0


@pytest.mark.parametrize("stored_ws, incoming_ws, kept", [
    (100.0, 98.0, 100.0),     # stale, looser copy: the stored stop survives
    (100.0, 101.0, 101.0),    # a genuine ratchet: the incoming stop wins
    (100.0, None, 100.0),     # a copy without a working stop never clears one
    (None, 99.0, 99.0),       # nothing stored yet: the incoming stop stands
])
def test_a_bullish_working_stop_only_ever_tightens(stored_ws, incoming_ws, kept):
    store = PlanStore()
    store.add(_bull(working_stop=stored_ws))
    incoming = _bull(working_stop=incoming_ws)

    assert store.update(incoming) is True

    assert _stored()["working_stop"] == kept
    assert incoming.working_stop == kept          # written back onto the caller's plan


def test_a_bearish_working_stop_only_ever_tightens():
    store = PlanStore()
    store.add(_bear(working_stop=100.0))
    incoming = _bear(working_stop=102.0)          # looser for a short
    assert store.update(incoming) is True
    assert _stored()["working_stop"] == 100.0 and incoming.working_stop == 100.0


@pytest.mark.parametrize("incoming_stop, kept", [(90.0, 95.0), (97.0, 97.0)])
def test_the_original_stop_never_loosens_either(incoming_stop, kept):
    store = PlanStore()
    store.add(_bull(stop_loss=95.0))
    assert store.update(_bull(stop_loss=incoming_stop)) is True
    assert _stored()["stop_loss"] == kept


def test_the_tp1_transition_keeps_the_tighter_stop():
    store = PlanStore()
    store.add(_bull(working_stop=107.0))          # a fresher ratchet already stored
    incoming = _bull(status=PlanStatus.PARTIAL, working_stop=106.66666666666667)
    assert store.update(incoming) is True
    row = _stored()
    assert row["status"] == PlanStatus.PARTIAL and row["working_stop"] == 107.0


def test_a_pending_plan_is_written_as_given():
    store = PlanStore()
    store.add(_bull(status=PlanStatus.PENDING, entry_price=None, stop_loss=95.0))
    assert store.update(_bull(status=PlanStatus.PENDING, entry_price=None, stop_loss=90.0)) is True
    assert _stored()["stop_loss"] == 90.0


def test_update_joins_the_callers_transaction():
    store = PlanStore()
    store.add(_bull())
    plan = store.get("P1")
    plan.first_seen_price = 101.0
    with pytest.raises(RuntimeError):
        with transaction() as conn:
            assert store.update(plan, conn=conn) is True
            raise RuntimeError("the caller's next write failed")
    assert _stored().get("first_seen_price") is None


class _ExplodingLock:
    def __enter__(self):
        raise AssertionError("update must not take the process-local _LOCK")

    def __exit__(self, *exc):
        return False


def test_update_holds_no_process_local_lock(monkeypatch):
    store = PlanStore()
    store.add(_bull())
    monkeypatch.setattr(plan_store_module, "_LOCK", _ExplodingLock())
    plan = store.get("P1")
    plan.first_seen_price = 101.0
    assert store.update(plan) is True
