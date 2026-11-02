"""v197 V197-4: the admin lifecycle commands commit the plan, its linked trade,
the account settlement and the notification event in one transaction; the
derived journal/snapshot hooks run only after that commit."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from swingbot import config
from swingbot.admin import app as _admin_app  # noqa: F401 -- loads the blueprint before its route modules
from swingbot.admin.api_v1 import lifecycle_commands as command
from swingbot.admin.api_v1 import trade_commands
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.planning import account
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog
from tests.admin.test_api_v1_trades import _plan, _trade

PLAN = "11111111-1111-4111-8111-111111111111"
TRADE = "lifecycle-trade"


@pytest.fixture
def book(store_db, monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "5")
    monkeypatch.setattr(trade_commands, "_override_stamp",
                        lambda ticker: {"exit_price": 102, "price_source": "quote"})
    monkeypatch.setattr(command, "_manual_close_quote", lambda ticker: 102)
    monkeypatch.setattr(command.rp, "cached_daily_bars", lambda ticker: None)
    hooks = []
    monkeypatch.setattr(TradeLog, "after_manual_close_commit", lambda self, trade: hooks.append(trade))
    AccountRepository().save(dict(base_balance=1000, balance=1000))
    PlanRepository().insert(_plan(PLAN, status="ACTIVE"))
    TradeRepository().insert(perf._db_record(_trade(TRADE, plan_id=PLAN)))
    return hooks


def snapshot():
    return dict(plan=PlanRepository().get(PLAN), trade=TradeRepository().get(TRADE),
                account=AccountRepository().load(), history=AccountRepository().history(),
                events=NotifyQueueRepository().list_all())


def fail_after(fn):
    def wrapped(*args, **kwargs):
        fn(*args, **kwargs)
        raise RuntimeError("injected write failure")
    return wrapped


@pytest.mark.parametrize("point", ["account", "trade", "plan", "queue"])
def test_any_authoritative_write_failure_rolls_everything_back(book, monkeypatch, point):
    before = snapshot()
    if point == "account":
        monkeypatch.setattr(account, "apply_realized_pnl", fail_after(account.apply_realized_pnl))
    elif point == "trade":
        monkeypatch.setattr(TradeLog, "_db_upsert", staticmethod(fail_after(TradeLog._db_upsert)))
    elif point == "plan":
        monkeypatch.setattr(PlanStore, "update", fail_after(PlanStore.update))
    else:
        monkeypatch.setattr(NotifyQueueRepository, "enqueue", fail_after(NotifyQueueRepository.enqueue))
    with pytest.raises(RuntimeError, match="injected write failure"):
        command.close_plan_atomic(PLAN)
    assert snapshot() == before
    assert book == []


def test_success_commits_one_event_and_one_settlement_before_hooks(book, monkeypatch):
    observations = []
    def observe(self, closed):
        committed = snapshot()  # independent real connections after outer commit
        assert committed["plan"]["status"] == "CLOSED"
        assert committed["trade"]["status"] == "closed"
        assert len(committed["history"]) == 1
        assert len(committed["events"]) == 1
        observations.append(closed["id"])
    monkeypatch.setattr(TradeLog, "after_manual_close_commit", observe)
    command.close_plan_atomic(PLAN)
    state = snapshot()
    assert observations == [TRADE]
    assert state["account"]["balance"] == 1010
    event = state["events"][0]
    assert event["kind"] == "plan_transition"
    assert event["payload"]["prior_status"] == "ACTIVE"
    assert event["payload"]["new_status"] == "CLOSED"
    assert event["payload"]["trade"]["exit_price"] == 102
    history = state["plan"]["status_history"][-1]
    assert event["transition_id"] == history["transition_id"]
    assert state["trade"]["manual_transition_id"] == history["transition_id"]
    assert event["payload"]["occurred_at"] == history["at"]


def test_concurrent_double_close_settles_and_enqueues_only_once(book):
    def attempt():
        try:
            command.close_plan_atomic(PLAN)
            return "closed"
        except command.LifecycleConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["closed", "conflict"]
    state = snapshot()
    assert len(state["events"]) == len(state["history"]) == 1
    assert len(book) == 1


def test_cancel_is_unfilled_and_rollback_preserves_pending(book, monkeypatch):
    row = PlanRepository().get(PLAN)
    row["status"] = "PENDING"
    PlanRepository().upsert(row)
    before = snapshot()
    with monkeypatch.context() as patch:
        patch.setattr(NotifyQueueRepository, "enqueue", fail_after(NotifyQueueRepository.enqueue))
        with pytest.raises(RuntimeError):
            command.cancel_plan_atomic(PLAN)
    assert snapshot() == before
    command.cancel_plan_atomic(PLAN)
    event = NotifyQueueRepository().list_all()[0]
    assert event["payload"]["new_status"] == "CANCELLED"
    assert event["payload"]["prior_status"] == "PENDING"
    assert "trade" not in event["payload"]
    assert AccountRepository().history() == []
    assert TradeRepository().get(TRADE)["status"] == "open"
    assert book == []


def test_legacy_close_preserves_recorded_fill_and_freezes_destination(book, monkeypatch):
    row = TradeRepository().get(TRADE)
    row["plan_id"] = None
    TradeRepository().upsert(row)
    command.close_legacy_atomic(TRADE)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "99")
    event = NotifyQueueRepository().list_all()[0]
    assert event["kind"] == "trade_closed"
    assert event["target_channel_id"] == "5"
    assert event["payload"]["trade_id"] == TRADE
    assert event["payload"]["trade"]["exit_price"] == 102
    assert event["payload"]["trade"]["realized_pnl_amount"] == 10
    assert len(book) == 1


def test_linked_trade_id_uses_same_atomic_plan_command(book):
    command.close_legacy_atomic(TRADE)
    state = snapshot()
    assert state["plan"]["status"] == "CLOSED"
    assert state["events"][0]["kind"] == "plan_transition"
    assert len(state["events"]) == 1


def test_post_commit_hook_failure_does_not_relabel_committed_action(book, monkeypatch):
    def fail(self, trade):
        raise RuntimeError("derived journal unavailable")
    monkeypatch.setattr(TradeLog, "after_manual_close_commit", fail)
    command.close_plan_atomic(PLAN)
    assert snapshot()["plan"]["status"] == "CLOSED"
    assert NotifyQueueRepository().pending() == 1


# --- edge cases beyond the plan's regressions --------------------------------

def _set_plan(**fields):
    row = PlanRepository().get(PLAN)
    row.update(fields)
    PlanRepository().upsert(row)


def test_partial_close_realizes_the_runner_leg_at_the_prepared_quote(book):
    _set_plan(status="PARTIAL", legs_realized=[
        {"fraction": 0.5, "exit_price": 110.0, "r": 1.5, "reason": "tp1"}])
    command.close_plan_atomic(PLAN)
    plan = PlanRepository().get(PLAN)
    assert plan["status"] == "CLOSED"
    runner = plan["legs_realized"][-1]
    assert (runner["fraction"], runner["exit_price"], runner["reason"]) == (0.5, 102, "manual")
    assert plan["status_history"][-1]["prior_status"] == "PARTIAL"
    assert NotifyQueueRepository().list_all()[0]["payload"]["prior_status"] == "PARTIAL"


def test_close_of_a_missing_plan_is_not_found_and_writes_nothing(book):
    before = snapshot()
    with pytest.raises(command.LifecycleNotFound):
        command.close_plan_atomic("22222222-2222-4222-8222-222222222222")
    assert snapshot() == before


@pytest.mark.parametrize("status", ["PENDING", "CLOSED", "CANCELLED"])
def test_close_of_a_non_closeable_plan_conflicts(book, status):
    _set_plan(status=status)
    before = snapshot()
    with pytest.raises(command.LifecycleConflict):
        command.close_plan_atomic(PLAN)
    assert snapshot() == before
    assert book == []


def test_cancel_of_an_active_plan_conflicts_and_missing_plan_is_not_found(book):
    before = snapshot()
    with pytest.raises(command.LifecycleConflict):
        command.cancel_plan_atomic(PLAN)
    with pytest.raises(command.LifecycleNotFound):
        command.cancel_plan_atomic("22222222-2222-4222-8222-222222222222")
    assert snapshot() == before


def test_legacy_close_of_missing_or_closed_trade_writes_nothing(book):
    with pytest.raises(command.LifecycleNotFound):
        command.close_legacy_atomic("no-such-trade")
    row = TradeRepository().get(TRADE)
    row.update(plan_id=None, status="closed")
    TradeRepository().upsert(row)
    before = snapshot()
    with pytest.raises(command.LifecycleConflict):
        command.close_legacy_atomic(TRADE)
    assert snapshot() == before
    assert book == []


def test_plan_without_a_linked_trade_closes_with_no_trade_snapshot(book):
    TradeRepository().delete(TRADE)
    command.close_plan_atomic(PLAN)
    event = NotifyQueueRepository().list_all()[0]
    assert event["payload"]["trade_id"] is None
    assert "trade" not in event["payload"]
    assert AccountRepository().history() == []
    assert book == []
