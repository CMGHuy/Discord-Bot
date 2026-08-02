"""Plan v8 Task V47: close_plan_trade must journal like every other close.

Found while executing V45. `close_plan_trade` is the path PlanManager takes
for every v2 plan, and it was the one close path in TradeLog that never
called the journal hook. With PLAN_ENGINE_V2=on and the intraday manager
running, that means the journal recorded the legacy cohort faithfully and
silently omitted the entire v2 one -- and the journal is what the
retrospective, the weekly digest and the journal browsers read.
"""
import os

import pytest

from swingbot.core.analytics import journal
from swingbot.core.performance import TradeLog


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = journal.JournalStore(path=str(tmp_path / "journal.json"))
    monkeypatch.setattr(journal, "JournalStore", lambda *a, **k: s)
    # The journal's own bars lookup is not what's under test here.
    monkeypatch.setattr(journal, "bars_for_journal", lambda trade: None)
    return s


@pytest.fixture
def log(tmp_path):
    return TradeLog(path=str(tmp_path / "trades.json"))


def _open_plan_trade(log, plan_id="p1"):
    return log.log_trade(
        ticker="AAPL", strategy="RSI", horizon_key="4w", direction="bullish",
        confidence_level=3, confidence_label="Moderate",
        entry=100.0, stop_loss=95.0, take_profit=110.0,
        plan_id=plan_id, tier="B", badge="WEAK", source="confluence")


def test_a_plan_close_is_journaled(store, log):
    trade_id = _open_plan_trade(log)
    log.close_plan_trade("p1", {"fraction": 1.0, "exit_price": 110.0,
                                "r": 2.0, "reason": "tp1_runner"}, "win")

    assert log.get_trade_by_id(trade_id)["status"] == "win"
    entry = store.get(trade_id)
    assert entry is not None, "the v2 cohort must reach the journal too"
    assert entry["ticker"] == "AAPL"
    assert entry["outcome"] == "win"


def test_a_plan_loss_is_journaled_too(store, log):
    trade_id = _open_plan_trade(log, plan_id="p2")
    log.close_plan_trade("p2", {"fraction": 1.0, "exit_price": 95.0,
                                "r": -1.0, "reason": "loss"}, "loss")
    entry = store.get(trade_id)
    assert entry is not None
    assert entry["outcome"] == "loss"


def test_journaling_exactly_once_per_close(store, log):
    """The second call finds no open trade and must not write a duplicate."""
    _open_plan_trade(log, plan_id="p3")
    leg = {"fraction": 1.0, "exit_price": 110.0, "r": 2.0, "reason": "tp1_runner"}
    log.close_plan_trade("p3", leg, "win")
    log.close_plan_trade("p3", leg, "win")
    assert len(store.entries()) == 1


def test_no_matching_open_plan_writes_nothing(store, log):
    log.close_plan_trade("does-not-exist", None, "win")
    assert store.entries() == []


def test_a_journal_failure_never_un_closes_the_trade(log, monkeypatch, tmp_path):
    """Same guarantee the other four close paths already have: bookkeeping
    layered on top of a close that has already been persisted."""
    trade_id = _open_plan_trade(log, plan_id="p4")

    def _boom(*a, **k):
        raise RuntimeError("journal disk full")
    monkeypatch.setattr(journal, "journal_trade_close", _boom)

    log.close_plan_trade("p4", {"fraction": 1.0, "exit_price": 110.0,
                                "r": 2.0, "reason": "tp1_runner"}, "win")
    assert log.get_trade_by_id(trade_id)["status"] == "win"
