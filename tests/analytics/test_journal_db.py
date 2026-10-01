"""JournalStore reads and writes the journal table."""
from swingbot.core.analytics.journal import JournalStore


def _entry(trade_id="T1", **overrides):
    entry = dict(trade_id=trade_id, strategy="RSI", outcome="win",
                 closed_at="2026-01-09T15:00:00+00:00", tags=["runner"],
                 note="", lesson="held to TP1")
    entry.update(overrides)
    return entry


def test_reads_rows():
    store = JournalStore()
    store.add(_entry("T1"))
    store.add(_entry("T2", outcome="loss"))
    assert {entry["trade_id"] for entry in store.entries()} == {"T1", "T2"}
    assert [entry["trade_id"] for entry in store.entries(outcome="loss")] == ["T2"]


def test_add_stamps_created_at_every_time():
    store = JournalStore()
    first = store.add(_entry())
    second = store.add(_entry(lesson="revised"))
    assert second["created_at"] >= first["created_at"]
    assert store.get("T1")["lesson"] == "revised"


def test_add_returns_stamped_entry_and_missing_get_is_none():
    out = JournalStore().add(_entry())
    assert "created_at" in out and out["trade_id"] == "T1"
    assert JournalStore().get("nope") is None


def test_set_note_on_a_row():
    store = JournalStore()
    store.add(_entry("T1"))
    assert store.set_note("T1", "lesson") is True
    assert store.get("T1")["note"] == "lesson"
    assert store.set_note("MISSING", "x") is False
