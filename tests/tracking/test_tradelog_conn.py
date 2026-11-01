"""V189-7: TradeLog's plan writers and the account balance join the caller's
transaction; journal and snapshot hooks can wait for the commit."""
from __future__ import annotations

import logging

import pytest

from swingbot import config
from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.account import account_repo
from swingbot.core.planning import account as account_module
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog, run_after_commit
from tests.store_seed import seed_store

WIN_LEG = {"fraction": 1.0, "exit_price": 110.0, "r": 2.0, "reason": "win"}
TP1_LEG = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    return TradeLog()


def _open(tlog, plan_id="p1") -> str:
    return tlog.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=4, confidence_label="High", entry=100.0, stop_loss=95.0,
        take_profit=110.0, plan_id=plan_id)


def _trade(tlog, plan_id="p1") -> dict | None:
    return next((t for t in tlog.get_trades(status=None, limit=None)
                 if t.get("plan_id") == plan_id), None)


def _history_len() -> int:
    return len(account_repo().history())


class _Boom(RuntimeError):
    pass


def _rolled_back(write) -> None:
    """Run ``write(conn)`` in a transaction whose next statement fails."""
    with pytest.raises(_Boom):
        with transaction() as conn:
            write(conn)
            raise _Boom("the plan write after it failed")


# --- the leg, the fill and the placeholder -------------------------------------------

def test_a_leg_written_on_the_callers_connection_rolls_back_with_it(tlog):
    _open(tlog)
    _rolled_back(lambda conn: tlog.append_leg_by_plan("p1", TP1_LEG, conn=conn))
    assert not _trade(tlog).get("legs")


def test_a_leg_written_on_the_callers_connection_commits_with_it(tlog):
    _open(tlog)
    with transaction() as conn:
        tlog.append_leg_by_plan("p1", TP1_LEG, conn=conn)
    assert _trade(tlog)["legs"] == [TP1_LEG]


def test_a_fill_rolls_back_with_the_callers_transaction(tlog):
    _open(tlog)
    _rolled_back(lambda conn: tlog.record_plan_fill("p1", 101.0, conn=conn))
    assert _trade(tlog)["entry"] == 100.0


def test_a_fill_commits_and_returns_the_trade_id(tlog):
    trade_id = _open(tlog)
    with transaction() as conn:
        assert tlog.record_plan_fill("p1", 101.0, conn=conn) == trade_id
    assert _trade(tlog)["entry"] == 101.0


def test_a_placeholder_discard_rolls_back_with_the_callers_transaction(tlog):
    _open(tlog)
    _rolled_back(lambda conn: tlog.discard_plan_placeholder("p1", conn=conn))
    assert _trade(tlog)["status"] == "open"


def test_a_placeholder_discard_commits(tlog):
    _open(tlog)
    with transaction() as conn:
        assert tlog.discard_plan_placeholder("p1", conn=conn) is True
    assert _trade(tlog) is None


def test_writers_on_a_connection_take_no_process_local_lock(tlog, monkeypatch):
    _open(tlog)

    class _Exploding:
        def __enter__(self):
            raise AssertionError("a conn= write must not hold TradeLog._LOCK")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(performance, "_LOCK", _Exploding())
    with transaction() as conn:
        tlog.append_leg_by_plan("p1", TP1_LEG, conn=conn)
        assert tlog.record_plan_fill("p1", 101.0, conn=conn) is not None


# --- the terminal close and its balance point ----------------------------------------

def test_a_rolled_back_close_leaves_no_trade_change_and_no_balance_point(tlog):
    _open(tlog)
    before = _history_len()
    _rolled_back(lambda conn: tlog.close_plan_trade("p1", WIN_LEG, "win", conn=conn,
                                                    after_commit=[]))
    trade = _trade(tlog)
    assert trade["status"] == "open" and trade.get("realized_pnl_amount") is None
    assert _history_len() == before


def test_a_committed_close_writes_one_balance_point_with_todays_arithmetic(tlog):
    _open(tlog)
    shares = _trade(tlog)["shares"]
    expected_pnl = round(shares * (110.0 - 100.0), 2)
    base = account_module.load_account_config()["balance"]
    before = _history_len()

    with transaction() as conn:
        closed = tlog.close_plan_trade("p1", WIN_LEG, "win", conn=conn, after_commit=[])

    assert closed["status"] == "win"
    assert closed["realized_pnl_amount"] == expected_pnl
    assert closed["account_balance_after"] == round(base + expected_pnl, 2)
    history = account_repo().history()
    assert len(history) == before + 1
    assert history[-1]["balance"] == round(base + expected_pnl, 2)
    # No double count: once the trade row is saved, the recomputed balance agrees.
    assert account_module.load_account_config()["balance"] == round(base + expected_pnl, 2)


def test_close_reason_is_written_when_given(tlog):
    _open(tlog)
    with transaction() as conn:
        closed = tlog.close_plan_trade("p1", WIN_LEG, "closed", conn=conn,
                                       close_reason="scratch", after_commit=[])
    assert closed["close_reason"] == "scratch"
    assert _trade(tlog)["close_reason"] == "scratch"


def test_close_without_an_open_trade_returns_none(tlog):
    with transaction() as conn:
        assert tlog.close_plan_trade("nope", WIN_LEG, "win", conn=conn, after_commit=[]) is None


def test_a_failed_balance_write_inside_the_transaction_rolls_the_close_back(tlog, monkeypatch):
    _open(tlog)

    def refuse(*_args, **_kwargs):
        raise RuntimeError("account store down")

    monkeypatch.setattr(performance.account_module, "apply_realized_pnl", refuse)
    with pytest.raises(RuntimeError, match="account store down"):
        with transaction() as conn:
            tlog.close_plan_trade("p1", WIN_LEG, "win", conn=conn, after_commit=[])
    assert _trade(tlog)["status"] == "open"


def test_without_a_connection_a_failed_balance_write_is_still_swallowed(tlog, monkeypatch, caplog):
    _open(tlog)

    def refuse(*_args, **_kwargs):
        raise RuntimeError("account store down")

    monkeypatch.setattr(performance.account_module, "apply_realized_pnl", refuse)
    caplog.set_level(logging.WARNING, logger=performance.log.name)
    closed = tlog.close_plan_trade("p1", WIN_LEG, "win")
    assert closed["status"] == "win" and closed.get("realized_pnl_amount") is None
    assert "account settlement failed" in caplog.text


# --- hooks after commit ----------------------------------------------------------------

def _record_hooks(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(performance, "_after_close", lambda trade: calls.append(("journal", trade["id"])))
    monkeypatch.setattr(performance, "_refresh_snapshot_safely", lambda: calls.append(("snapshot", None)))
    return calls


def test_hooks_wait_for_the_commit_when_the_caller_collects_them(tlog, monkeypatch):
    trade_id = _open(tlog)
    calls = _record_hooks(monkeypatch)
    callbacks: list = []
    with transaction() as conn:
        tlog.close_plan_trade("p1", WIN_LEG, "win", conn=conn, after_commit=callbacks)
        assert calls == []                      # nothing ran inside the transaction
    run_after_commit(callbacks)
    assert calls == [("journal", trade_id), ("snapshot", None)]


def test_without_a_collector_the_hooks_run_at_once_as_today(tlog, monkeypatch):
    trade_id = _open(tlog)
    calls = _record_hooks(monkeypatch)
    tlog.close_plan_trade("p1", WIN_LEG, "win")
    assert calls == [("journal", trade_id), ("snapshot", None)]


def test_run_after_commit_logs_a_failure_and_keeps_going(caplog):
    ran: list = []

    def broken():
        raise RuntimeError("journal down")

    caplog.set_level(logging.WARNING, logger=performance.log.name)
    run_after_commit([broken, lambda: ran.append("snapshot")])
    assert ran == ["snapshot"]
    assert "after-commit hook" in caplog.text


def test_run_after_commit_of_nothing_is_a_no_op():
    run_after_commit([])


# --- account functions on a connection ---------------------------------------------------

def test_apply_realized_pnl_on_a_connection_rolls_back_with_it(tlog):
    before = _history_len()
    _rolled_back(lambda conn: account_module.apply_realized_pnl(50.0, {"trade_id": "x"}, conn=conn))
    assert _history_len() == before


def test_load_account_config_reads_on_the_callers_connection(tlog):
    with transaction() as conn:
        cfg = account_module.load_account_config(conn=conn)
    assert cfg["balance"] == account_module.load_account_config()["balance"]
