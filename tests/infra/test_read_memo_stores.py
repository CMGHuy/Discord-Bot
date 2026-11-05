"""v205 V205-7: TradeLog, PlanStore and the account's realized-P&L sum read through the
read memo -- once per scope and key, today's direct read outside a scope, and never for
a call inside a transaction."""
import copy
from datetime import datetime, timezone

import pytest

from swingbot.core.infra import read_memo
from swingbot.core.planning import account
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog


def _trade(trade_id, ticker, status, opened, *, pnl=None, legs=()):
    return {"trade_id": trade_id, "horizon": "2w", "ticker": ticker, "strategy": "RSI",
            "direction": "bullish", "status": status, "entry": 100.0, "stop_loss": 95.0,
            "shares": 2, "opened_at": opened, "closed_at": None,
            "realized_pnl_amount": pnl, "legs": list(legs)}


TRADES = [
    _trade("T1", "AAPL", "win", "2026-01-02T15:00:00+00:00", pnl=50.0),
    # settled from its legs: 2 shares x 1.0 x (95 - 100) = -10.0
    _trade("T2", "MSFT", "loss", "2026-01-03T15:00:00+00:00", legs=[{"fraction": 1.0, "exit_price": 95.0}]),
    _trade("T3", "NVDA", "open", "2026-01-04T15:00:00+00:00"),
]
PLANS = [
    {"plan_id": "P1", "ticker": "AAPL", "status": "ACTIVE", "status_history": [],
     "created_at": datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc)},
    {"plan_id": "P2", "ticker": "MSFT", "status": "PENDING", "status_history": [],
     "created_at": datetime(2026, 1, 3, 8, 0, tzinfo=timezone.utc)},
]
REALIZED = 40.0          # 50.0 + (-10.0); T3 is open


class _Repo:
    """A repository double: fresh nested rows per call, each call's kwargs recorded."""

    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def list_all(self, **kwargs):
        self.calls.append(kwargs)
        return copy.deepcopy(self.rows)


@pytest.fixture
def trades(monkeypatch):
    repo = _Repo(TRADES)
    monkeypatch.setattr("swingbot.core.db.repositories.trades.trades_repo", lambda: repo)
    return repo


@pytest.fixture
def plans(monkeypatch):
    repo = _Repo(PLANS)
    monkeypatch.setattr("swingbot.core.db.repositories.plans.plans_repo", lambda: repo)
    return repo


def test_outside_a_scope_every_read_is_a_fresh_query(trades, plans):
    TradeLog()._all()
    TradeLog().get_trades(status=None, limit=None)
    assert account._sum_realized_pnl() == REALIZED
    assert account._sum_realized_pnl() == REALIZED
    PlanStore().records()
    PlanStore().get_record("P1")
    assert trades.calls == [{}, {}, {}, {}]           # list_all() with no arguments, as today
    assert plans.calls == [{}, {}]


def test_inside_a_scope_each_key_loads_once(trades, plans):
    with read_memo.scope():
        TradeLog()._all()
        TradeLog().get_trades(status=None, limit=None)
        TradeLog().get_trades(status="win", limit=None)
        assert len(trades.calls) == 1
        assert account._sum_realized_pnl() == REALIZED
        assert account._sum_realized_pnl() == REALIZED
        assert len(trades.calls) == 2                  # TRADE_ROWS is its own key
        PlanStore().records()
        PlanStore().get_record("P1")
        assert PlanStore().get_record("missing") is None
        assert len(plans.calls) == 1


def test_scoped_reads_equal_direct_reads(trades, plans):
    direct = (TradeLog()._all(), PlanStore()._all(), account._sum_realized_pnl())
    with read_memo.scope():
        for _ in range(2):
            assert (TradeLog()._all(), PlanStore()._all(), account._sum_realized_pnl()) == direct


def test_each_caller_owns_the_top_level_of_its_records(trades, plans):
    with read_memo.scope():
        first = TradeLog()._all()
        first[0]["status"] = "changed"
        first.pop()
        again = TradeLog()._all()
        assert [t["status"] for t in again] == ["win", "loss", "open"]
        record = PlanStore().get_record("P1")
        record["status"] = "CLOSED"
        assert PlanStore().get_record("P1")["status"] == "ACTIVE"


def test_a_transaction_never_reads_through_the_memo(trades):
    conn = object()
    with read_memo.scope():
        assert account._sum_realized_pnl(conn=conn) == REALIZED
        assert account._sum_realized_pnl(conn=conn) == REALIZED
        assert read_memo.peek(read_memo.TRADE_ROWS) is None
        assert account._sum_realized_pnl() == REALIZED
        assert read_memo.peek(read_memo.TRADE_ROWS) is not None
    assert trades.calls == [{"conn": conn}, {"conn": conn}, {}]


def test_the_memo_holds_each_stores_parsed_shape(trades, plans):
    with read_memo.scope():
        TradeLog()._all()
        PlanStore().records()
        account._sum_realized_pnl()
        assert [t["id"] for t in read_memo.peek(read_memo.TRADES)] == ["T1", "T2", "T3"]
        assert "trade_id" not in read_memo.peek(read_memo.TRADES)[0]
        assert read_memo.peek(read_memo.PLANS)["P1"]["created_at"] == "2026-01-02T08:00:00+00:00"
        assert read_memo.peek(read_memo.TRADE_ROWS)[0]["trade_id"] == "T1"


def test_the_stores_call_the_memo_through_its_module(trades, plans, monkeypatch):
    seen = []
    real_records, real_mapping = read_memo.records, read_memo.mapping
    monkeypatch.setattr(read_memo, "records", lambda key, loader: seen.append(key) or real_records(key, loader))
    monkeypatch.setattr(read_memo, "mapping", lambda key, loader: seen.append(key) or real_mapping(key, loader))
    TradeLog()._all()
    account._sum_realized_pnl()
    PlanStore().records()
    assert seen == [read_memo.TRADES, read_memo.TRADE_ROWS, read_memo.PLANS]
