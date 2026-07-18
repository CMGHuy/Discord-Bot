from swingbot.core.analytics.journal import JournalStore


def _entry(trade_id, strategy="Fibonacci", tags=None, outcome="win", closed_at="2026-03-10T10:00:00+00:00"):
    return {"trade_id": trade_id, "ticker": "AAPL", "strategy": strategy,
            "outcome": outcome, "tags": tags or [], "note": "", "closed_at": closed_at}


def test_add_stamps_created_at_and_get_roundtrips(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    saved = store.add(_entry("t1"))
    assert "created_at" in saved
    assert store.get("t1")["ticker"] == "AAPL"
    assert store.get("nope") is None


def test_re_add_same_trade_id_replaces_not_duplicates(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add(_entry("t1", outcome="win"))
    store.add(_entry("t1", outcome="loss"))
    all_entries = store.entries()
    assert len(all_entries) == 1 and all_entries[0]["outcome"] == "loss"


def test_entries_filters_by_strategy_and_tag_newest_first(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add(_entry("t1", strategy="Fibonacci", tags=["fast_win"], closed_at="2026-03-01T00:00:00+00:00"))
    store.add(_entry("t2", strategy="EMA Crossover", tags=["slow_burn"], closed_at="2026-03-02T00:00:00+00:00"))
    store.add(_entry("t3", strategy="Fibonacci", tags=["fast_win"], closed_at="2026-03-03T00:00:00+00:00"))

    by_strategy = store.entries(strategy="Fibonacci")
    assert [e["trade_id"] for e in by_strategy] == ["t3", "t1"]  # newest first

    by_tag = store.entries(tag="slow_burn")
    assert [e["trade_id"] for e in by_tag] == ["t2"]


def test_entries_filters_by_outcome_and_since(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add(_entry("t1", outcome="win", closed_at="2026-03-01T00:00:00+00:00"))
    store.add(_entry("t2", outcome="loss", closed_at="2026-03-05T00:00:00+00:00"))
    assert [e["trade_id"] for e in store.entries(outcome="loss")] == ["t2"]
    assert [e["trade_id"] for e in store.entries(since="2026-03-03")] == ["t2"]


def test_set_note_roundtrips_through_a_fresh_store_instance(tmp_path):
    path = str(tmp_path / "journal.json")
    store = JournalStore(path=path)
    store.add(_entry("t1"))
    assert store.set_note("t1", "Should have trailed further.") is True

    fresh = JournalStore(path=path)  # forces a real disk read, not shared in-memory state
    assert fresh.get("t1")["note"] == "Should have trailed further."
