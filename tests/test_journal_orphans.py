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


def _ids(log):
    return [t["id"] for t in log.get_trades(status="all", limit=None)]


def _log_one(log, ticker="AAPL"):
    return log.log_trade(
        ticker=ticker, strategy="RSI", horizon_key="4w", direction="bullish",
        confidence_level=3, confidence_label="Moderate",
        entry=100.0, stop_loss=95.0, take_profit=110.0)


def test_deleting_a_journaled_trade_is_what_creates_an_orphan(tmp_path, monkeypatch):
    """The mechanism, demonstrated end to end against the real TradeLog:
    delete_trade removes the trade row and journal.json keeps its entry, so
    the two halves go out of sync. This is the asymmetry V45's three live
    orphans fit -- not a broken close/journal handoff.

    **Updated 2026-08-05:** the deletion is now *stamped* (`trade_deleted_at`)
    rather than left dangling, so it no longer counts as an orphan. The
    asymmetry this test names is unchanged -- the trade row goes, the entry
    stays -- but it is now explained at the point it happens instead of
    resurfacing as an integrity warning at every startup forever.
    """
    s = JournalStore(path=str(tmp_path / "journal.json"))
    monkeypatch.setattr(journal, "JournalStore", lambda *a, **k: s)

    log = TradeLog(path=str(tmp_path / "trades.json"))
    trade_id = _log_one(log)
    s.add(_entry(trade_id))
    assert journal.orphan_entries(_ids(log)) == []

    assert log.delete_trade(trade_id) is True
    # The entry survived the delete -- the learning record is not collateral
    # damage of tidying the book -- and it is stamped, so it is no longer an
    # *unexplained* orphan.
    entry = s.get(trade_id)
    assert entry is not None
    assert entry["trade_deleted_at"]
    assert journal.orphan_entries(_ids(log)) == []


def test_an_unexplained_orphan_is_still_reported(store):
    """The marker must not swallow the case V45 exists for. An entry whose
    trade vanished without any delete path stamping it -- the real
    data-integrity signature -- still counts."""
    store.add(_entry("vanished"))
    assert [e["trade_id"] for e in journal.orphan_entries(["other"])] == ["vanished"]


def test_clear_open_and_clear_history_both_stamp(tmp_path, monkeypatch):
    """Both bulk paths, not just the single delete -- clear_open is the one
    an operator reaches for most, and it took the same silent shortcut."""
    s = JournalStore(path=str(tmp_path / "journal.json"))
    monkeypatch.setattr(journal, "JournalStore", lambda *a, **k: s)
    log = TradeLog(path=str(tmp_path / "trades.json"))

    open_id = _log_one(log, "AAPL")
    s.add(_entry(open_id))
    assert log.clear_open() == 1
    assert s.get(open_id)["trade_deleted_at"]
    assert journal.orphan_entries(_ids(log)) == []

    closed_id = _log_one(log, "TSLA")
    # Flip the status directly rather than going through close_trade_manual,
    # which reaches for a live price -- what is under test here is the delete
    # path, not the close path.
    for t in log._trades:
        if t["id"] == closed_id:
            t["status"] = "win"
    log._save()
    s.add(_entry(closed_id, ticker="TSLA"))
    assert log.clear_history() == 1
    assert s.get(closed_id)["trade_deleted_at"]
    assert journal.orphan_entries(_ids(log)) == []


def test_clear_all_stamps_every_entry(tmp_path, monkeypatch):
    s = JournalStore(path=str(tmp_path / "journal.json"))
    monkeypatch.setattr(journal, "JournalStore", lambda *a, **k: s)
    log = TradeLog(path=str(tmp_path / "trades.json"))
    ids = [_log_one(log, t) for t in ("AAPL", "TSLA", "MSFT")]
    for i in ids:
        s.add(_entry(i))

    assert log.clear_all() == 3
    assert all(s.get(i)["trade_deleted_at"] for i in ids)
    assert journal.orphan_entries([]) == []


def test_the_stamp_records_the_first_deletion_not_the_latest(store):
    """Re-running a delete (or a later bulk clear that re-lists the same id)
    must not rewrite when the row actually went away."""
    store.add(_entry("t1"))
    assert store.mark_deleted(["t1"]) == 1
    first = store.get("t1")["trade_deleted_at"]
    assert store.mark_deleted(["t1"]) == 0          # already stamped
    assert store.get("t1")["trade_deleted_at"] == first


def test_a_journal_failure_can_never_break_a_delete(tmp_path, monkeypatch):
    """Same contract as _journal_close_safely: bookkeeping is not allowed to
    surface as a broken trade delete."""
    monkeypatch.setattr(journal, "JournalStore",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("journal is a directory")))
    log = TradeLog(path=str(tmp_path / "trades.json"))
    trade_id = _log_one(log)
    assert log.delete_trade(trade_id) is True       # must not raise
    assert _ids(log) == []
