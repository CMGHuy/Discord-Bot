"""v173 §1: close_trade_manual(exit_price=) settles at the price the plan's
override stamp recorded, so the stamp and the trade never disagree. Without
it, today's own live fetch is unchanged."""
from __future__ import annotations

import pytest

from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog


def _open(trade_id="t1", legs=None):
    return {"id": trade_id, "ticker": "AAPL", "status": "open", "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "legs": legs or []}


@pytest.fixture
def book(monkeypatch):
    """`rows` is the whole table; `upserts` every write; `fetches` every live fetch."""
    state = {"rows": [_open()], "upserts": [], "fetches": [], "quote": 111.0}

    def fetch(ticker, *args, **kwargs):
        state["fetches"].append((ticker, kwargs.get("allow_stale")))
        return state["quote"]

    monkeypatch.setattr(TradeLog, "_all", lambda self: state["rows"])
    monkeypatch.setattr(TradeLog, "_db_upsert",
                        staticmethod(lambda trade, conn=None: state["upserts"].append(dict(trade))))
    monkeypatch.setattr(TradeLog, "_settle_account_balance", lambda self, trade: None)
    monkeypatch.setattr(perf, "_after_close", lambda trade: None)
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: None)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", fetch)
    return state


def test_a_given_exit_price_is_used_and_nothing_is_fetched(book):
    assert TradeLog().close_trade_manual("t1", reason="manual (plan close, admin UI)",
                                         exit_price=123.45) is True
    trade = book["rows"][0]
    assert trade["exit_price"] == pytest.approx(123.45)
    assert trade["status"] == "closed"
    assert trade["close_reason"] == "manual (plan close, admin UI)"
    assert book["fetches"] == []
    assert len(book["upserts"]) == 1


def test_without_an_exit_price_the_live_fetch_is_unchanged(book):
    assert TradeLog().close_trade_manual("t1") is True
    assert book["fetches"] == [("AAPL", False)]
    assert book["rows"][0]["exit_price"] == pytest.approx(111.0)


def test_a_failed_fetch_still_closes_without_a_price(book, monkeypatch):
    def boom(*args, **kwargs):
        raise TimeoutError("down")

    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", boom)
    assert TradeLog().close_trade_manual("t1") is True
    assert book["rows"][0]["status"] == "closed"
    assert book["rows"][0].get("exit_price") is None


def test_a_partial_trade_banks_its_remainder_at_the_given_price(book):
    book["rows"] = [_open(legs=[{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}])]
    TradeLog().close_trade_manual("t1", exit_price=105.0)
    legs = book["rows"][0]["legs"]
    assert [leg["fraction"] for leg in legs] == [0.5, 0.5]
    assert legs[-1]["exit_price"] == pytest.approx(105.0)
    assert legs[-1]["r"] == pytest.approx(1.0)
    assert book["fetches"] == []


def test_an_already_closed_trade_is_not_touched(book):
    book["rows"][0]["status"] = "closed"
    assert TradeLog().close_trade_manual("t1", exit_price=123.45) is False
    assert book["upserts"] == []
