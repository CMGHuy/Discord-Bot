"""v204: /market/updates reports snapshot changes; /market/refresh queues snapshot keys."""
from datetime import datetime, timedelta, timezone

import pytest

import swingbot.admin.app  # noqa: F401  (app first: api_v1 modules import under it)
from swingbot.admin.api_v1 import market_updates
from swingbot.core.marketdata.shared.admin_refresh import PRIORITY_USER, QUEUE_KIND_SNAPSHOT
from tests.admin_market.conftest import (  # noqa: F401
    _clear_login_limiter, admin_app, auth, client, market, on_client, session_is)
from tests.admin_market.test_page_loads_never_fetch import network_forbidden  # noqa: F401
from tests.admin_snapshots.test_snapshot_door import snapshot_row, snapshot_store  # noqa: F401

NOW = datetime.now(timezone.utc)
SINCE = {"since": (NOW - timedelta(minutes=1)).isoformat()}


@pytest.fixture
def changes(monkeypatch):
    monkeypatch.setattr(market_updates, "_cache_changes", lambda since: [])


def test_without_since_snapshots_are_empty_and_status_carries_the_threshold(on_client, market,
                                                                            snapshot_store, changes,
                                                                            session_is):
    body = on_client.get("/api/v1/market/updates").get_json()
    assert body["snapshots"] == [] and body["status"]["stale_snapshot_s"] == 600.0
    session_is("closed")
    assert on_client.get("/api/v1/market/updates").get_json()["status"]["stale_snapshot_s"] is None


def test_since_lists_changed_rows_and_snapshot_marks(on_client, market, snapshot_store, changes,
                                                     network_forbidden):
    row = snapshot_row("risk", {"heat": {}}, age_s=30, stale=True)
    snapshot_store.rows["risk"] = row
    snapshot_store.changed.append({k: row[k] for k in ("key", "computed_at", "stale_inputs", "updated_at")})
    market.marks.in_flight.add("snapshot:analytics.snapshot")
    market.marks.changed += [
        {"key": "snapshot:analytics.snapshot", "in_flight": True, "error": None, "updated_at": NOW},
        {"key": "quote:NVDA", "in_flight": True, "error": None, "updated_at": NOW}]
    body = on_client.get("/api/v1/market/updates", query_string=SINCE).get_json()
    assert body["snapshots"] == [
        {"key": "analytics.snapshot", "computed_at": None, "stale_inputs": False,
         "refreshing": True, "error": None},
        {"key": "risk", "computed_at": row["computed_at"].isoformat(), "stale_inputs": True,
         "refreshing": False, "error": None}]
    assert market.queue.pending == {}                   # the updates read never enqueues
    assert network_forbidden == []


def test_snapshot_mark_error_reaches_updates(on_client, market, snapshot_store, changes):
    market.marks.errors_by_key["snapshot:risk"] = "DailyCacheUnavailable: not mounted"
    market.marks.changed.append({"key": "snapshot:risk", "in_flight": False,
                                 "error": "DailyCacheUnavailable: not mounted", "updated_at": NOW})
    [item] = on_client.get("/api/v1/market/updates", query_string=SINCE).get_json()["snapshots"]
    assert item["key"] == "risk" and item["error"] == "DailyCacheUnavailable: not mounted"


def test_snapshot_store_failure_fails_open(on_client, market, snapshot_store, changes):
    snapshot_store.broken = True
    resp = on_client.get("/api/v1/market/updates", query_string=SINCE)
    assert resp.status_code == 200 and resp.get_json()["snapshots"] == []


@pytest.mark.parametrize("body, queued", [({"snapshots": ["risk"]}, 1),
                                          ({"symbols": ["msft"], "snapshots": ["risk"]}, 2)])
def test_refresh_accepts_snapshot_keys(on_client, market, body, queued):
    resp = on_client.post("/api/v1/market/refresh", json=body)
    assert resp.status_code == 202 and resp.get_json() == {"queued": queued}
    assert market.queue.pending[(QUEUE_KIND_SNAPSHOT, "risk")] == PRIORITY_USER


@pytest.mark.parametrize("body", [
    {"snapshots": "risk"},
    {"snapshots": [1]},
    {"snapshots": ["prices"]},
    {"symbols": [], "snapshots": []},
    {"symbols": ["MSFT"], "snapshots": ["bogus"]},
])
def test_refresh_rejects_bad_snapshot_bodies(on_client, market, body):
    resp = on_client.post("/api/v1/market/refresh", json=body)
    assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "invalid"
    assert market.queue.pending == {}
