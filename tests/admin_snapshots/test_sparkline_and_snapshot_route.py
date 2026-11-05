"""v204 V204-13: the sparkline, /analytics/snapshot and the registry read the analytics.snapshot row."""
from types import SimpleNamespace

import pytest

import swingbot.admin.app  # noqa: F401  (app first: api_v1 modules import under it)
from swingbot import config
from swingbot.admin import market_values, queries
from swingbot.admin.api_v1 import dashboard as dashboard_api
from swingbot.core.marketdata.shared import admin_refresh as ar
from tests.admin.test_badge_decay_surface import _reg
from tests.admin_snapshots.golden_book import (  # noqa: F401
    _clear_login_limiter, admin_app, assert_matches_golden, client, golden_payload)

COMPUTED = "2026-10-29T14:30:00+00:00"
LOGIN = {"username": "admin", "password": "admin"}
REBUILDERS = (
    "swingbot.core.analytics.snapshots.refresh_snapshot",
    "swingbot.core.analytics.snapshots.compute_snapshot",
    "swingbot.core.analytics.snapshots.load_snapshot",
    "swingbot.admin.queries.refresh_snapshot",
    "swingbot.admin.queries.load_snapshot",
)


def stored(key, doc, *, computed_at=COMPUTED, refreshing=False, error=None, fx_as_of=None):
    """A row as V204-11's read_snapshot returns it. V204-14 imports this helper."""
    return {"key": key, "doc": doc, "computed_at": computed_at, "stale_inputs": False,
            "refreshing": refreshing, "error": error,
            "inputs": {"computed_at": computed_at, "oldest_quote_as_of": None, "oldest_fx_as_of": fx_as_of,
                       "missing": {"quotes": [], "fx": [], "bars": {}}}}


@pytest.fixture
def snapshot_rows(monkeypatch):
    """A fake door with the refresher on: rows by key, every read and refresh recorded.
    V204-14 imports this fixture together with `stored`."""
    rows, reads, refreshes = {}, [], []

    def read(key, *, now=None):
        reads.append(key)
        return rows.get(key) or {"key": key, "doc": None, "inputs": None, "computed_at": None,
                                 "stale_inputs": False, "refreshing": True, "error": None}

    def refresh(symbols, *, snapshots=(), priority=0):
        refreshes.append((list(symbols), list(snapshots)))
        return len(list(snapshots))

    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")  # refresher_on() needs both
    monkeypatch.setattr(market_values, "read_snapshot", read)
    monkeypatch.setattr(market_values, "request_refresh", refresh)
    return SimpleNamespace(rows=rows, reads=reads, refreshes=refreshes)


@pytest.fixture
def no_rebuild(monkeypatch):
    calls = []
    for target in REBUILDERS:
        monkeypatch.setattr(target, lambda *a, _t=target, **k: calls.append(_t))
    return calls


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=LOGIN)
    return client


def test_sparkline_reads_the_stored_row_and_matches_golden(snapshot_rows, no_rebuild):
    snapshot_rows.rows[ar.SNAPSHOT_ANALYTICS] = stored(
        ar.SNAPSHOT_ANALYTICS, golden_payload("analytics_snapshot"))
    body = dashboard_api._equity_30d()
    assert_matches_golden("sparkline", body)
    assert body["market_meta"]["source"] == "snapshot"
    assert body["market_meta"]["computed_at"] == COMPUTED
    assert no_rebuild == []


def test_sparkline_without_a_row_is_empty_and_refreshing_never_rebuilt(snapshot_rows, no_rebuild):
    body = dashboard_api._equity_30d()
    assert body["points"] == [] and body["change_pct"] is None
    assert body["market_meta"]["refreshing"] is True
    assert snapshot_rows.reads == [ar.SNAPSHOT_ANALYTICS]
    assert no_rebuild == []


def test_snapshot_route_forwards_the_row_with_its_meta(logged_in, snapshot_rows, no_rebuild):
    doc = {"overall": {"n": 3}, "equity_curve": {"points": []}}
    snapshot_rows.rows[ar.SNAPSHOT_ANALYTICS] = stored(ar.SNAPSHOT_ANALYTICS, doc)
    body = logged_in.get("/api/v1/analytics/snapshot").get_json()
    meta = body.pop("market_meta")
    assert body == doc
    assert meta["source"] == "snapshot" and meta["refreshing"] is False
    assert no_rebuild == []


def test_snapshot_route_with_no_row_is_empty_and_refreshing(logged_in, snapshot_rows, no_rebuild):
    body = logged_in.get("/api/v1/analytics/snapshot").get_json()
    assert set(body) == {"market_meta"} and body["market_meta"]["refreshing"] is True
    assert no_rebuild == []


def test_fresh_enqueues_the_snapshot_and_never_rebuilds(logged_in, snapshot_rows, no_rebuild):
    assert logged_in.get("/api/v1/analytics/snapshot?fresh=1").status_code == 200
    assert snapshot_rows.refreshes == [([], [ar.SNAPSHOT_ANALYTICS])]
    assert no_rebuild == []


def test_registry_rows_read_the_stored_row(snapshot_rows, no_rebuild, monkeypatch):
    monkeypatch.setattr(queries, "load_registry", lambda: _reg("2019-01-01"))
    snapshot_rows.rows[ar.SNAPSHOT_ANALYTICS] = stored(ar.SNAPSHOT_ANALYTICS, {
        "by": {"strategy": [{"key": "Fibonacci", "n": 7, "win_rate": 80.0}]},
        "calibration": {"drift": []}})
    rows = queries._registry_rows()
    assert rows[0]["live_n"] == 7 and rows[0]["live_wr"] == 80.0
    assert no_rebuild == []


def test_kill_switch_off_keeps_the_file_path_and_adds_a_request_meta(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    calls = []
    monkeypatch.setattr(queries, "load_snapshot", lambda max_age_seconds=3600: None)
    monkeypatch.setattr(queries, "refresh_snapshot", lambda: calls.append("refresh"))
    body = dashboard_api._equity_30d()
    assert calls == ["refresh"]                      # today's request-time rebuild, behind the flag
    assert body["points"] == [] and body["market_meta"]["source"] == "request"


def test_kill_switch_off_meta_carries_the_file_build_time(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    built = "2026-10-29T13:00:00+00:00"
    monkeypatch.setattr(queries, "load_snapshot",
                        lambda max_age_seconds=3600: {"built_at": built, "overall": {}})
    doc, meta = queries.analytics_snapshot_read()
    assert doc["built_at"] == built
    assert meta["computed_at"] == built and meta["as_of"] == built
    assert meta["source"] == "request" and meta["refreshing"] is False
