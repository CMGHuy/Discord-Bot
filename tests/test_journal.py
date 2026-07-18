from unittest.mock import patch

from tests.conftest import make_ohlcv
from swingbot.core.analytics.journal import JournalStore, build_entry, journal_trade_close


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


def _base_trade(**kw):
    base = {"id": "t1", "ticker": "AAPL", "strategy": "Fibonacci", "horizon_key": "4w",
            "direction": "bullish", "tier": "A", "badge": "VALIDATED", "quality_score": 80,
            "entry": 100.0, "stop_loss": 96.0,
            "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-05T15:00:00+00:00"}
    base.update(kw)
    return base


def test_build_entry_rule1_loss_stopped_after_running():
    # mae_r <= 0.3 and mfe_r >= 1.0 -- ran to +1R+ then reversed and stopped out.
    # NOTE: the brief's original fixture [100, 104, 95] was verified (by hand
    # and with real compute_mfe_mae) to produce mae_r=1.25 (not <= 0.3), which
    # would NOT hit rule 1 -- it would fall through to the fallback message.
    # [100, 104, 99] (shallow pullback to 99, still above entry) genuinely
    # produces mfe_r=1.0, mae_r=0.25, satisfying rule 1's condition.
    df = make_ohlcv([100, 104, 99], spread_pct=0.0, start="2026-03-02")
    t = _base_trade(status="loss", exit_price=96.0)
    e = build_entry(t, df)
    assert e["auto_lesson"] == ("Trade went 1.0R in favor before stopping out — exit management, "
                                "not entry, cost this one.")
    assert e["trade_id"] == "t1" and e["tier"] == "A" and e["badge"] == "VALIDATED"


def test_build_entry_rule2_win_clean_capture():
    df = make_ohlcv([100, 104], spread_pct=0.0, start="2026-03-02")
    t = _base_trade(status="win", exit_price=104.0, closed_at="2026-03-03T15:00:00+00:00")
    e = build_entry(t, df)
    assert e["auto_lesson"] == "Clean capture: banked 100% of the available move."


def test_build_entry_rule4_scratch_no_followthrough():
    df = make_ohlcv([100, 100], spread_pct=0.0, start="2026-03-02")
    t = _base_trade(status="closed", close_reason="scratch", exit_price=100.0,
                    closed_at="2026-03-03T15:00:00+00:00")
    e = build_entry(t, df)
    assert e["outcome"] == "scratch"
    assert e["auto_lesson"] == "No follow-through within the horizon — count it as rent, not error."


def test_build_entry_fallback_and_df_none_is_safe():
    t = _base_trade(status="loss", exit_price=97.0)
    e = build_entry(t, None)
    assert e["mfe_r"] is None and e["mae_r"] is None and e["exit_efficiency"] is None
    assert e["auto_lesson"] == f"Outcome loss at {e['r_realized']:+.2f}R."
    assert e["note"] == "" and e["tags"] == []


def _closed_trade():
    return {"id": "t1", "ticker": "AAPL", "strategy": "Fibonacci", "horizon_key": "4w",
            "direction": "bullish", "entry": 100.0, "stop_loss": 96.0, "status": "win",
            "exit_price": 104.0, "opened_at": "2026-03-02T15:00:00+00:00",
            "closed_at": "2026-03-05T15:00:00+00:00"}


def test_journal_trade_close_adds_entry(tmp_path, monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    df = make_ohlcv([100, 108, 98, 104], spread_pct=0.0, start="2026-03-02")
    with patch("swingbot.core.data.get_daily_data", return_value=df):
        journal_trade_close(_closed_trade())
    store = JournalStore(path=str(tmp_path / "journal.json"))
    assert store.get("t1") is not None


def test_journal_trade_close_never_raises_on_fetch_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    with patch("swingbot.core.data.get_daily_data", side_effect=ValueError("no data")):
        journal_trade_close(_closed_trade())  # must not raise
    store = JournalStore(path=str(tmp_path / "journal.json"))
    # Entry still gets added -- just with df=None (all MFE/MAE fields None) --
    # a data-fetch failure degrades the entry, it does not skip it.
    assert store.get("t1") is not None
    assert store.get("t1")["mfe_r"] is None


def test_set_note_false_for_missing_trade_id(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    assert store.set_note("missing", "x") is False


def test_has_note_filter(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add(_entry("t1"))
    store.add(_entry("t2"))
    store.set_note("t1", "worth remembering")
    result = store.entries(has_note=True)
    assert [e["trade_id"] for e in result] == ["t1"]
    assert [e["trade_id"] for e in store.entries(has_note=False)] == ["t2"]


from scripts.backfill_journal import backfill


def test_backfill_skips_already_journaled(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add(_entry("already"))
    trades = [
        {"id": "already", "ticker": "AAPL", "status": "win", "entry": 100.0, "stop_loss": 96.0,
         "exit_price": 104.0, "opened_at": "2026-03-01T00:00:00+00:00", "closed_at": "2026-03-02T00:00:00+00:00"},
        {"id": "new1", "ticker": "MSFT", "status": "loss", "entry": 50.0, "stop_loss": 52.0,
         "exit_price": 52.0, "opened_at": "2026-03-01T00:00:00+00:00", "closed_at": "2026-03-02T00:00:00+00:00"},
        {"id": "open1", "ticker": "TSLA", "status": "open", "entry": 200.0, "stop_loss": 190.0},
    ]

    def fetch(ticker):
        return None  # no bars available in this test -- backfill must still succeed with degraded entries

    backfilled, skipped = backfill(trades, store, fetch)
    assert backfilled == 1  # "new1" only -- "already" is already journaled, "open1" isn't closed
    # The plan's Step-1 draft asserted skipped==1, but backfill()'s own docstring
    # defines `skipped` as trades that are not-closed OR already-journaled -- both
    # "already" (journaled) and "open1" (still open) count, so skipped==2. Production
    # logic matches its documented contract; the draft assertion was the miscount.
    assert skipped == 2
    assert store.get("new1") is not None
