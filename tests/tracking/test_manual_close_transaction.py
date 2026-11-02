"""v197 V197-3: a manual close composes on the caller's transaction.

`TradeLog.close_trade_manual_in_transaction` reads, settles and writes on the
supplied connection only -- no implicit engine connection, no price fetch, no
journal/snapshot hook while the transaction is open -- so an outer rollback
reverts the trade, the balance and its history point together. The derived
effects run only through `after_manual_close_commit`, after the caller
commits. `PlanStore.get/get_record` read (and optionally row-lock) on the same
connection `update` writes on."""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.planning import account
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog
from tests.admin.test_api_v1_trades import _plan

AT = "2026-10-28T12:00:00+00:00"
PLAN_ID = "11111111-1111-4111-8111-111111111111"


def seed(conn, *, legs=None):
    AccountRepository().save(dict(base_balance=1000, balance=1000), conn=conn)
    TradeRepository().insert(dict(
        trade_id="manual-t", ticker="AAPL", strategy="RSI", horizon="2w",
        direction="bullish", status="open", opened_at=AT, entry=100,
        stop_loss=95, shares=10, legs=legs or []), conn=conn)


def close(conn, price=101):
    return TradeLog().close_trade_manual_in_transaction(
        "manual-t", "manual", exit_price=price, closed_at=AT,
        transition_id="transition-t", conn=conn)


def test_all_account_and_trade_io_uses_supplied_connection(db_conn, monkeypatch):
    seed(db_conn)

    def no_implicit_connection():
        raise AssertionError("escaped caller transaction")

    monkeypatch.setattr("swingbot.core.db.repositories.base.get_engine", no_implicit_connection)
    monkeypatch.setattr(perf, "_manual_close_quote",
                        lambda ticker: pytest.fail("network inside transaction"))
    monkeypatch.setattr(perf, "_after_close", lambda trade: pytest.fail("premature journal hook"))
    monkeypatch.setattr(perf, "_refresh_snapshot_safely",
                        lambda: pytest.fail("premature snapshot"))
    result = close(db_conn)
    assert result["realized_pnl_amount"] == 10
    assert result["account_balance_after"] == 1010
    assert result["manual_transition_id"] == "transition-t"
    assert result["closed_at"] == AT
    assert TradeRepository().get("manual-t", conn=db_conn)["status"] == "closed"
    assert account.load_account_config(conn=db_conn)["balance"] == 1010
    history = AccountRepository().history(conn=db_conn)
    assert len(history) == 1
    assert history[0]["pnl_amount"] == 10


def test_outer_rollback_reverts_trade_balance_and_history(db_conn):
    seed(db_conn)
    before = AccountRepository().load(conn=db_conn)
    with pytest.raises(RuntimeError), db_conn.begin_nested():
        close(db_conn)
        raise RuntimeError("later queue insertion failed")
    assert TradeRepository().get("manual-t", conn=db_conn)["status"] == "open"
    assert AccountRepository().load(conn=db_conn) == before
    assert AccountRepository().history(conn=db_conn) == []


def test_settlement_failure_propagates_without_writing_trade(db_conn, monkeypatch):
    seed(db_conn)

    def failed(*args, **kwargs):
        raise RuntimeError("account save failed")

    monkeypatch.setattr(account, "apply_realized_pnl", failed)
    with pytest.raises(RuntimeError, match="account save failed"), db_conn.begin_nested():
        close(db_conn)
    assert TradeRepository().get("manual-t", conn=db_conn)["status"] == "open"


def test_missing_price_never_fetches_and_never_invents_realized_pnl(db_conn, monkeypatch):
    seed(db_conn)
    monkeypatch.setattr(perf, "_manual_close_quote", lambda ticker: pytest.fail("unexpected quote"))
    result = close(db_conn, price=None)
    assert result["status"] == "closed"
    assert result.get("exit_price") is None
    assert result.get("realized_pnl_amount") is None
    assert AccountRepository().history(conn=db_conn) == []


def test_partial_close_preserves_recorded_leg_and_settles_once(db_conn):
    seed(db_conn, legs=[dict(fraction=0.5, exit_price=110, r=2, reason="tp1")])
    result = close(db_conn, price=105)
    assert [leg["exit_price"] for leg in result["legs"]] == [110, 105]
    assert result["realized_pnl_amount"] == 75
    assert account.load_account_config(conn=db_conn)["balance"] == 1075
    assert close(db_conn, price=105) is None
    assert len(AccountRepository().history(conn=db_conn)) == 1


def test_unknown_trade_returns_none(db_conn):
    assert close(db_conn) is None


def test_a_connection_is_required():
    with pytest.raises(ValueError, match="caller_connection_required"):
        TradeLog().close_trade_manual_in_transaction(
            "manual-t", "manual", exit_price=101, closed_at=AT,
            transition_id="transition-t", conn=None)


def test_post_commit_hook_is_explicit_and_uses_recorded_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(perf, "_after_close", lambda trade: calls.append(("journal", trade["id"])))
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: calls.append(("snapshot", None)))
    TradeLog().after_manual_close_commit({"id": "manual-t"})
    assert calls == [("journal", "manual-t"), ("snapshot", None)]


def test_plan_get_and_update_share_outer_transaction_without_python_lock(db_conn, monkeypatch):
    PlanRepository().insert(_plan(PLAN_ID, status="ACTIVE"), conn=db_conn)
    store = PlanStore()

    @contextmanager
    def forbidden_lock():
        pytest.fail("caller-owned DB transaction must not wait on process-local plan lock")
        yield

    monkeypatch.setattr("swingbot.core.planning.plan_store._LOCK", forbidden_lock())
    plan = store.get(PLAN_ID, conn=db_conn, for_update=True)
    with db_conn.begin_nested() as savepoint:
        plan.status = "CLOSED"
        store.update(plan, conn=db_conn)
        assert store.get_record(plan.plan_id, conn=db_conn)["status"] == "CLOSED"
        savepoint.rollback()
    assert store.get_record(plan.plan_id, conn=db_conn)["status"] == "ACTIVE"


def test_plan_locking_read_requires_a_connection():
    with pytest.raises(ValueError, match="locking_read_requires_connection"):
        PlanStore().get_record(PLAN_ID, for_update=True)


def test_plan_reads_on_a_connection_return_none_for_a_missing_plan(db_conn):
    store = PlanStore()
    assert store.get_record(PLAN_ID, conn=db_conn) is None
    assert store.get(PLAN_ID, conn=db_conn, for_update=True) is None
