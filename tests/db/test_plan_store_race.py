"""V189-6: the bot's stale plan write racing an admin close or a fresh ratchet,
on two real connections. The admin transaction holds the plan row lock while
the bot's update waits on it; after the admin commits, the bot's write is
refused (terminal) or merged (tighter stop)."""
from __future__ import annotations

import logging
import threading
import time

import pytest

from swingbot.core.db.engine import BOT_LOCK_TIMEOUT_MS, LockTimeout, transaction
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan as _model_plan

pytestmark = pytest.mark.slow
LOGGER = "swingbot.core.planning.plan_store"


def _active(**kw):
    base = dict(plan_id="P1", entry_type="market", direction="bullish", trigger_price=100.0,
                entry_price=100.0, stop_loss=95.0, tp1=110.0, status=PlanStatus.ACTIVE)
    base.update(kw)
    return _model_plan(**base)


def _bot_update_in_thread(store: PlanStore, plan) -> tuple[threading.Thread, dict]:
    outcome: dict = {}

    def run():
        try:
            outcome["result"] = store.update(plan)
        except BaseException as exc:  # noqa: BLE001 - the test inspects it
            outcome["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def _to_partial(plan):
    record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial", at="t0")


def _first_seen(plan):
    plan.first_seen_price = 101.0


def _ratchet(plan):
    plan.working_stop = 100.0


@pytest.mark.parametrize("stale_change", [_to_partial, _first_seen, _ratchet],
                         ids=["status-changing", "first_seen_price", "stop-ratchet"])
def test_an_admin_close_survives_the_bots_stale_write(caplog, stale_change):
    PlanStore().add(_active())
    bot_store = PlanStore(lock_timeout_ms=BOT_LOCK_TIMEOUT_MS)
    stale = bot_store.get("P1")          # the copy the bot read earlier in its poll
    stale_change(stale)
    caplog.set_level(logging.INFO, logger=LOGGER)

    admin = PlanStore()
    with transaction() as conn:
        plan = admin.lock_for_update("P1", conn=conn)
        record_transition(plan, PlanStatus.CLOSED, reason="manual", at="t1")
        assert admin.update(plan, conn=conn) is True
        thread, outcome = _bot_update_in_thread(bot_store, stale)
        time.sleep(0.3)
        assert thread.is_alive(), "the bot's write must wait on the admin's row lock"
    thread.join(timeout=5)

    assert not thread.is_alive() and "error" not in outcome, outcome
    assert outcome["result"] is False
    final = PlanStore().get("P1")
    assert final.status == PlanStatus.CLOSED
    assert final.first_seen_price is None and final.working_stop is None
    assert "plan store: refused stale write to P1 (stored CLOSED" in caplog.text


def test_a_fresh_ratchet_survives_a_stale_looser_stop():
    PlanStore().add(_active(working_stop=100.0))
    bot_store = PlanStore(lock_timeout_ms=BOT_LOCK_TIMEOUT_MS)
    stale = bot_store.get("P1")           # working_stop 100 at read time
    stale.first_seen_price = 101.0

    other = PlanStore()
    with transaction() as conn:
        plan = other.lock_for_update("P1", conn=conn)
        plan.working_stop = 102.0         # the fresher ratchet
        assert other.update(plan, conn=conn) is True
        thread, outcome = _bot_update_in_thread(bot_store, stale)
        time.sleep(0.3)
        assert thread.is_alive()
    thread.join(timeout=5)

    assert outcome.get("result") is True, outcome
    final = PlanStore().get("P1")
    assert final.working_stop == 102.0     # tighter stop kept
    assert final.first_seen_price == 101.0  # the bot's other field still lands


def test_a_lock_held_past_the_timeout_raises_and_writes_nothing():
    PlanStore().add(_active())
    bot_store = PlanStore(lock_timeout_ms=200)
    stale = bot_store.get("P1")
    stale.first_seen_price = 101.0

    holder = PlanStore()
    with transaction() as conn:
        assert holder.lock_for_update("P1", conn=conn) is not None
        thread, outcome = _bot_update_in_thread(bot_store, stale)
        thread.join(timeout=5)

    assert isinstance(outcome.get("error"), LockTimeout), outcome
    assert PlanStore().get("P1").first_seen_price is None
