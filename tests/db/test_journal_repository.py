"""JournalRepository filters match JournalStore.entries."""
import pytest

from swingbot.core.db.repositories.journal import JournalRepository


@pytest.fixture
def repo():
    return JournalRepository()


def _entry(trade_id, **overrides):
    entry = dict(trade_id=trade_id, strategy="RSI", outcome="win",
                 closed_at="2026-01-09T15:00:00+00:00",
                 created_at="2026-01-09T16:00:00+00:00",
                 tags=["clean-entry"], note="", lesson="held to TP1")
    entry.update(overrides)
    return entry


def test_entries_are_newest_first_by_closed_at(repo, db_conn):
    repo.upsert(_entry("OLD", closed_at="2026-01-01T00:00:00+00:00"), conn=db_conn)
    repo.upsert(_entry("NEW", closed_at="2026-01-09T00:00:00+00:00"), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(conn=db_conn)] == ["NEW", "OLD"]


def test_filter_by_strategy_and_outcome(repo, db_conn):
    repo.upsert(_entry("T1", strategy="RSI", outcome="win"), conn=db_conn)
    repo.upsert(_entry("T2", strategy="MACD", outcome="loss"), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(strategy="MACD", conn=db_conn)] == ["T2"]
    assert [entry["trade_id"] for entry in repo.entries(outcome="loss", conn=db_conn)] == ["T2"]


def test_filter_by_tag_uses_jsonb_containment(repo, db_conn):
    repo.upsert(_entry("T1", tags=["clean-entry", "runner"]), conn=db_conn)
    repo.upsert(_entry("T2", tags=["chased"]), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(tag="runner", conn=db_conn)] == ["T1"]


def test_filter_by_since_is_inclusive(repo, db_conn):
    repo.upsert(_entry("T1", closed_at="2026-01-01T00:00:00+00:00"), conn=db_conn)
    repo.upsert(_entry("T2", closed_at="2026-01-09T00:00:00+00:00"), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(
        since="2026-01-09T00:00:00+00:00", conn=db_conn)] == ["T2"]


def test_filter_by_has_note_trims_whitespace(repo, db_conn):
    repo.upsert(_entry("T1", note="  "), conn=db_conn)
    repo.upsert(_entry("T2", note="real note"), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(has_note=True, conn=db_conn)] == ["T2"]
    assert [entry["trade_id"] for entry in repo.entries(has_note=False, conn=db_conn)] == ["T1"]


def test_filters_are_and_combined_and_upserts_replace(repo, db_conn):
    repo.upsert(_entry("T1", strategy="RSI", outcome="win", lesson="first"), conn=db_conn)
    repo.upsert(_entry("T2", strategy="RSI", outcome="loss"), conn=db_conn)
    repo.upsert(_entry("T1", strategy="RSI", outcome="win", lesson="second"), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(
        strategy="RSI", outcome="loss", conn=db_conn)] == ["T2"]
    assert repo.count(conn=db_conn) == 2
    assert repo.get("T1", conn=db_conn)["lesson"] == "second"


FINER_THAN_5MIN = ("15min", "hourly", "daily", None)   # coarser_sources("5min") in V228-2
FINER_THAN_HOURLY = ("daily", None)                     # coarser_sources("hourly")


def test_patch_if_coarser_upgrades_a_daily_row_and_keeps_the_note(repo, db_conn):
    repo.upsert(_entry("T1", excursion_source="daily", mfe_r=1.24, note="partner note"), conn=db_conn)
    out = repo.patch_if_coarser("T1", {"mfe_r": 0.31, "excursion_source": "5min"},
                                coarser=FINER_THAN_5MIN, conn=db_conn)
    assert (out["excursion_source"], out["mfe_r"], out["note"]) == ("5min", 0.31, "partner note")
    assert out["tags"] == ["clean-entry"] and out["lesson"] == "held to TP1"


def test_a_coarser_write_after_a_finer_one_is_a_no_op(repo, db_conn):
    repo.upsert(_entry("T1", excursion_source="daily", mfe_r=1.24), conn=db_conn)
    assert repo.patch_if_coarser("T1", {"mfe_r": 0.31, "excursion_source": "5min"},
                                 coarser=FINER_THAN_5MIN, conn=db_conn) is not None
    assert repo.patch_if_coarser("T1", {"mfe_r": 0.5, "excursion_source": "hourly"},
                                 coarser=FINER_THAN_HOURLY, conn=db_conn) is None
    row = repo.get("T1", conn=db_conn)
    assert (row["excursion_source"], row["mfe_r"]) == ("5min", 0.31)


@pytest.mark.parametrize("stored", [{}, {"excursion_source": None}])
def test_a_missing_or_null_source_counts_as_none(repo, db_conn, stored):
    repo.upsert(_entry("T1", **stored), conn=db_conn)
    out = repo.patch_if_coarser("T1", {"excursion_source": "daily", "mfe_r": 1.0},
                                coarser=(None,), conn=db_conn)
    assert out["excursion_source"] == "daily"


def test_an_equal_source_is_not_rewritten(repo, db_conn):
    repo.upsert(_entry("T1", excursion_source="hourly", mfe_r=0.9), conn=db_conn)
    assert repo.patch_if_coarser("T1", {"excursion_source": "hourly", "mfe_r": 0.1},
                                 coarser=FINER_THAN_HOURLY, conn=db_conn) is None
    assert repo.get("T1", conn=db_conn)["mfe_r"] == 0.9


def test_a_missing_row_and_an_empty_coarser_set_never_match(repo, db_conn):
    assert repo.patch_if_coarser("nope", {"excursion_source": "5min"},
                                 coarser=FINER_THAN_5MIN, conn=db_conn) is None
    repo.upsert(_entry("T1", excursion_source="daily"), conn=db_conn)
    assert repo.patch_if_coarser("T1", {"excursion_source": "5min"},
                                 coarser=(), conn=db_conn) is None


def test_patch_if_coarser_never_reads_before_writing(repo, db_conn, monkeypatch):
    repo.upsert(_entry("T1", excursion_source="daily"), conn=db_conn)

    def no_read(*args, **kwargs):
        raise AssertionError("patch_if_coarser must not read-then-write")

    monkeypatch.setattr(repo, "get", no_read)
    monkeypatch.setattr(repo, "get_for_update", no_read)
    assert repo.patch_if_coarser("T1", {"excursion_source": "5min"},
                                 coarser=FINER_THAN_5MIN, conn=db_conn) is not None
