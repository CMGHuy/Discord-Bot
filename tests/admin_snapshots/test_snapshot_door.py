"""v204: the request door serves snapshot rows, never builds, and only enqueues."""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot.admin import market_values as mv
from swingbot.core.db.repositories import admin_snapshots as snapshot_repos
from swingbot.core.market import session
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.admin_refresh import (
    PRIORITY_FRESH_HINT, PRIORITY_MISSING, PRIORITY_USER, QUEUE_KIND_QUOTE, QUEUE_KIND_SNAPSHOT)
from tests.admin_market.conftest import market, session_is  # noqa: F401

META_KEYS = {"as_of", "refreshing", "stale_count", "missing_count", "incomplete",
             "computed_at", "stale_inputs", "source", "error"}


def utcnow():
    return datetime.now(timezone.utc)


def snapshot_row(key, doc, *, age_s, stale=False, inputs=None):
    at = utcnow() - timedelta(seconds=age_s)
    return {"key": key, "doc": doc, "inputs": inputs or {"computed_at": at.isoformat()},
            "computed_at": at, "stale_inputs": stale, "updated_at": at}


class FakeSnapshots:
    def __init__(self):
        self.rows, self.changed, self.broken = {}, [], False

    def read(self, key):
        if self.broken:
            raise RuntimeError("db down")
        return self.rows.get(key)

    def read_many(self, keys):
        return {k: self.rows[k] for k in keys if k in self.rows}

    def changed_since(self, since):
        if self.broken:
            raise RuntimeError("db down")
        return list(self.changed)


@pytest.fixture
def snapshot_store(monkeypatch):
    fake = FakeSnapshots()
    monkeypatch.setattr(snapshot_repos, "admin_snapshot_repo", lambda: fake)
    return fake


def test_absent_snapshot_is_refreshing_and_enqueued_once(market, session_is, snapshot_store):
    first = mv.read_snapshot("risk")
    mv.read_snapshot("risk")
    assert (first["doc"], first["computed_at"], first["refreshing"]) == (None, None, True)
    assert market.queue.pending == {(QUEUE_KIND_SNAPSHOT, "risk"): PRIORITY_MISSING}


def test_fresh_row_is_served_as_stored_without_enqueue(market, session_is, snapshot_store):
    snapshot_store.rows["risk"] = snapshot_row("risk", {"heat": {"open_pct": 1.2}}, age_s=180)
    snap = mv.read_snapshot("risk")
    assert snap["doc"] == {"heat": {"open_pct": 1.2}} and snap["refreshing"] is False
    assert datetime.fromisoformat(snap["computed_at"]).tzinfo is not None
    assert market.queue.pending == {}


def test_stale_row_is_enqueued_unless_in_flight(market, session_is, snapshot_store):
    snapshot_store.rows["risk"] = snapshot_row("risk", {}, age_s=660)          # regular: stale after 600 s
    assert mv.read_snapshot("risk")["refreshing"] is False
    assert market.queue.pending == {(QUEUE_KIND_SNAPSHOT, "risk"): PRIORITY_MISSING}
    market.queue.pending.clear()
    market.marks.in_flight.add("snapshot:risk")
    assert mv.read_snapshot("risk")["refreshing"] is True
    assert market.queue.pending == {}


@pytest.mark.parametrize("built_hours_after_close, enqueued", [(-1, True), (1, False)])
def test_closed_market_row_built_before_the_last_close_is_stale(market, session_is, snapshot_store,
                                                                monkeypatch, built_hours_after_close,
                                                                enqueued):
    session_is("closed")
    close = utcnow() - timedelta(hours=3)
    monkeypatch.setattr(session, "last_regular_close", lambda now=None: close)
    row = snapshot_row("risk", {}, age_s=0)
    row["computed_at"] = close + timedelta(hours=built_hours_after_close)
    snapshot_store.rows["risk"] = row
    mv.read_snapshot("risk")
    assert ((QUEUE_KIND_SNAPSHOT, "risk") in market.queue.pending) is enqueued


def test_stale_inputs_alone_never_enqueues(market, session_is, snapshot_store):
    snapshot_store.rows["risk"] = snapshot_row("risk", {}, age_s=60, stale=True)
    assert mv.read_snapshot("risk")["stale_inputs"] is True
    assert market.queue.pending == {}


def test_mark_error_is_reported(market, session_is, snapshot_store):
    snapshot_store.rows["risk"] = snapshot_row("risk", {}, age_s=60)
    market.marks.errors_by_key["snapshot:risk"] = "budget exceeded after 90s"
    assert mv.read_snapshot("risk")["error"] == "budget exceeded after 90s"


def test_fresh_hint_enqueues_at_fresh_priority(market, session_is, snapshot_store):
    snapshot_store.rows["analytics.snapshot"] = snapshot_row("analytics.snapshot", {}, age_s=5)
    with kinds.fresh_request():
        mv.read_snapshot("analytics.snapshot")
    assert market.queue.pending == {(QUEUE_KIND_SNAPSHOT, "analytics.snapshot"): PRIORITY_FRESH_HINT}


def test_store_failure_fails_open(market, session_is, snapshot_store):
    snapshot_store.broken = True
    snap = mv.read_snapshot("risk")
    assert snap["doc"] is None and snap["error"] == "snapshot store unavailable"


def test_read_snapshot_rejects_unknown_keys(market, session_is, snapshot_store):
    with pytest.raises(ValueError):
        mv.read_snapshot("prices")


def test_snapshot_meta_counts_unique_missing_symbols_and_takes_the_oldest_input():
    inputs = {"oldest_quote_as_of": "2026-10-30T14:58:00+00:00", "oldest_fx_as_of": "2026-10-29",
              "missing": {"quotes": ["NEWX"], "fx": ["SAP.DE"],
                          "bars": {"SAP.DE": "no_file", "XAUUSD": "spot_metal"}}}
    snap = {"key": "risk", "doc": {}, "inputs": inputs, "computed_at": "2026-10-30T15:00:00+00:00",
            "stale_inputs": True, "refreshing": False, "error": None}
    meta = mv.snapshot_meta(snap, extra_missing=1)
    assert set(meta) == META_KEYS
    assert (meta["missing_count"], meta["incomplete"], meta["stale_count"]) == (4, True, 0)
    assert meta["as_of"] == "2026-10-29" and meta["source"] == "snapshot"
    assert (meta["computed_at"], meta["stale_inputs"]) == ("2026-10-30T15:00:00+00:00", True)


def test_snapshot_meta_without_inputs_falls_back_to_computed_at():
    snap = {"key": "risk", "doc": {}, "inputs": {"missing": {"quotes": [], "fx": [], "bars": {}}},
            "computed_at": "2026-10-30T15:00:00+00:00", "stale_inputs": False, "refreshing": False,
            "error": None}
    assert mv.snapshot_meta(snap)["as_of"] == "2026-10-30T15:00:00+00:00"


def test_snapshot_meta_of_an_absent_row():
    snap = {"key": "risk", "doc": None, "inputs": None, "computed_at": None, "stale_inputs": False,
            "refreshing": True, "error": None}
    meta = mv.snapshot_meta(snap)
    assert (meta["as_of"], meta["missing_count"], meta["refreshing"]) == (None, 0, True)


def test_request_refresh_enqueues_snapshot_keys(market):
    assert mv.request_refresh(["msft"], snapshots=["risk", "risk", "calendar.pnl:2026-10"]) == 3
    assert market.queue.pending == {(QUEUE_KIND_QUOTE, "MSFT"): PRIORITY_USER,
                                    (QUEUE_KIND_SNAPSHOT, "risk"): PRIORITY_USER,
                                    (QUEUE_KIND_SNAPSHOT, "calendar.pnl:2026-10"): PRIORITY_USER}


def test_request_refresh_rejects_an_unknown_key_before_enqueueing(market):
    with pytest.raises(ValueError):
        mv.request_refresh(["MSFT"], snapshots=["risk", "prices"])
    assert market.queue.pending == {}
