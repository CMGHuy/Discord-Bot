"""Plan v8 Task V45: journal entries with no matching trade record.

3 of 345 live entries referenced a trade_id present nowhere in trades.json
or plans.json. The write ordering is NOT the cause -- every
_journal_close_safely call site in performance.py saves the trade before
journaling it -- so what these tests pin is the detection, plus the
deletion asymmetry that actually produces orphans.
"""
import pytest

from swingbot.core.analytics import journal
from swingbot.core.analytics.journal import JournalStore
from swingbot.core.performance import TradeLog


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = JournalStore(path=str(tmp_path / "journal.json"))
    monkeypatch.setattr(journal, "JournalStore", lambda *a, **k: s)
    return s


def _entry(trade_id, ticker="AAPL"):
    return {"trade_id": trade_id, "ticker": ticker, "strategy": "RSI",
            "outcome": "win", "closed_at": "2026-07-30T12:00:00+00:00"}


def test_no_orphans_when_every_entry_has_its_trade(store):
    store.add(_entry("t1"))
    store.add(_entry("t2"))
    assert journal.orphan_entries(["t1", "t2", "t3"]) == []


def test_an_entry_with_no_trade_is_an_orphan(store):
    store.add(_entry("t1"))
    store.add(_entry("gone", ticker="TSLA"))
    orphans = journal.orphan_entries(["t1"])
    assert [e["trade_id"] for e in orphans] == ["gone"]


def test_the_check_reports_and_never_raises(store, caplog):
    caplog.set_level("WARNING")
    store.add(_entry("gone"))
    assert journal.log_orphan_check(["other"]) == 1
    assert "Journal integrity" in caplog.text
    assert "gone" in caplog.text


def test_the_check_survives_an_unreadable_journal(monkeypatch, caplog):
    """A bookkeeping audit must never be able to stop the bot from starting."""
    def _boom(*a, **k):
        raise OSError("journal.json is a directory")
    monkeypatch.setattr(journal, "JournalStore", _boom)
    assert journal.log_orphan_check(["t1"]) == 0        # must not raise


def test_it_accepts_a_generator_not_just_a_list(store):
    """The startup call site passes a generator over TradeLog rows."""
    store.add(_entry("gone"))
    store.add(_entry("kept"))
    orphans = journal.orphan_entries(tid for tid in ["kept"])
    assert [e["trade_id"] for e in orphans] == ["gone"]


def test_deleting_a_journaled_trade_is_what_creates_an_orphan(tmp_path, monkeypatch):
    """The mechanism, demonstrated end to end against the real TradeLog:
    delete_trade removes the trade row and does not touch journal.json, so
    the entry it was written for becomes an orphan. This is the asymmetry
    V45's three live orphans fit -- not a broken close/journal handoff."""
    s = JournalStore(path=str(tmp_path / "journal.json"))
    monkeypatch.setattr(journal, "JournalStore", lambda *a, **k: s)

    log = TradeLog(path=str(tmp_path / "trades.json"))
    trade_id = log.log_trade(
        ticker="AAPL", strategy="RSI", horizon_key="4w", direction="bullish",
        confidence_level=3, confidence_label="Moderate",
        entry=100.0, stop_loss=95.0, take_profit=110.0)
    s.add(_entry(trade_id))
    assert journal.orphan_entries([t["id"] for t in log.get_trades(status="all", limit=None)]) == []

    assert log.delete_trade(trade_id) is True
    orphans = journal.orphan_entries([t["id"] for t in log.get_trades(status="all", limit=None)])
    assert [e["trade_id"] for e in orphans] == [trade_id]
    # And the entry itself survived the delete -- which is the point: the
    # learning record is not collateral damage of tidying the book.
    assert s.get(trade_id) is not None
