"""v204 V204-14: default Analytics and Calendar views read their snapshot; every other view
computes on request and never fetches; both carry market_meta. SNAPSHOT_ROUTES is patched,
so both V204-2 outcomes are tested whatever the measured verdict was."""
import pytest

import swingbot.admin.app  # noqa: F401  (app first: api_v1 modules import under it)
from swingbot.admin import market_values
from swingbot.admin.api_v1 import analytics as analytics_api
from swingbot.admin.api_v1 import calendar as calendar_api
from swingbot.core.analytics import admin_snapshots
from swingbot.core.marketdata.daily_readonly import DailyCacheUnavailable
from swingbot.core.marketdata.shared import admin_refresh as ar
from tests.admin_snapshots.golden_book import (  # noqa: F401
    GOLDEN_MONTH, _clear_login_limiter, admin_app, assert_matches_golden, client, golden_book)
from tests.admin_snapshots.test_sparkline_and_snapshot_route import (  # noqa: F401
    logged_in, snapshot_rows, stored)

ALL_ROUTES = frozenset({"analytics.performance", "analytics.equity_curve", "calendar.pnl"})
CURRENT, PREVIOUS = ar.calendar_months()


@pytest.fixture
def all_snapshotted(monkeypatch, snapshot_rows):
    monkeypatch.setattr(admin_snapshots, "SNAPSHOT_ROUTES", ALL_ROUTES)
    return snapshot_rows


@pytest.fixture
def no_compute(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("request-time body computed for a stored default view")
    monkeypatch.setattr(analytics_api, "_performance_body", boom)
    monkeypatch.setattr(analytics_api, "_equity_curve_body", boom)
    monkeypatch.setattr(calendar_api, "_calendar_body", boom)


@pytest.fixture
def fx_known(monkeypatch):
    monkeypatch.setattr(admin_snapshots, "_fx_inputs", lambda tickers, *, on: (
        {"EUR": {"rate": 1.1, "as_of": "2026-10-27"}}, []))


@pytest.mark.parametrize("path, key", [
    ("/api/v1/analytics/performance", "analytics.performance:main"),
    ("/api/v1/analytics/performance?ledger=weak", "analytics.performance:weak"),
    ("/api/v1/analytics/equity-curve?ledger=both", "analytics.equity_curve:both"),
    (f"/api/v1/calendar/pnl?month={CURRENT}", f"calendar.pnl:{CURRENT}"),
    (f"/api/v1/calendar/pnl?month={PREVIOUS}", f"calendar.pnl:{PREVIOUS}"),
])
def test_default_view_serves_its_stored_row(logged_in, all_snapshotted, no_compute, path, key):
    all_snapshotted.rows[key] = stored(key, {"sentinel": key}, fx_as_of="2026-10-28")
    body = logged_in.get(path).get_json()
    meta = body.pop("market_meta")
    assert body == {"sentinel": key}
    assert meta["source"] == "snapshot" and meta["as_of"] == "2026-10-28"
    assert all_snapshotted.reads == [key]


def test_equity_snapshot_omits_legacy_benchmark(logged_in, all_snapshotted, no_compute):
    key = "analytics.equity_curve:main"
    all_snapshotted.rows[key] = stored(key, {"points": [], "benchmark": {"spy_indexed": []}})
    body = logged_in.get("/api/v1/analytics/equity-curve").get_json()
    assert body["points"] == []
    assert "benchmark" not in body


@pytest.mark.parametrize("path", [
    "/api/v1/analytics/performance?ledger=main&strategy=Fibonacci",
    "/api/v1/analytics/equity-curve?from=2026-01-01",
    "/api/v1/calendar/pnl?month=2025-01",
    f"/api/v1/calendar/pnl?month={CURRENT}&strategy=Fibonacci",
])
def test_filtered_or_older_view_computes_on_request(logged_in, all_snapshotted, fx_known, path):
    resp = logged_in.get(path)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    meta = resp.get_json()["market_meta"]
    assert all_snapshotted.reads == []
    assert meta["source"] == "request" and meta["as_of"] == "2026-10-27"
    assert meta["refreshing"] is False


def test_route_not_marked_snapshot_never_reads_a_row(logged_in, snapshot_rows, fx_known, monkeypatch):
    monkeypatch.setattr(admin_snapshots, "SNAPSHOT_ROUTES", frozenset())
    body = logged_in.get("/api/v1/analytics/performance").get_json()
    assert snapshot_rows.reads == []
    assert "totals" in body and body["market_meta"]["source"] == "request"


def test_absent_row_serves_the_request_body_refreshing(logged_in, all_snapshotted, fx_known):
    body = logged_in.get("/api/v1/analytics/performance").get_json()
    assert all_snapshotted.reads == ["analytics.performance:main"]
    assert "totals" in body                                   # the real body, never zeros
    assert body["market_meta"]["source"] == "request"
    assert body["market_meta"]["refreshing"] is True


def test_request_meta_counts_unconverted_rows_never_zero(logged_in, snapshot_rows, fx_known,
                                                          monkeypatch):
    monkeypatch.setattr(admin_snapshots, "SNAPSHOT_ROUTES", frozenset())
    monkeypatch.setattr(analytics_api, "_performance_body", lambda scope: {"fx_missing_count": 2})
    meta = logged_in.get("/api/v1/analytics/performance?strategy=Fibonacci").get_json()["market_meta"]
    assert meta["missing_count"] == 2 and meta["incomplete"] is True


def test_unmounted_bar_cache_leaves_the_fx_as_of_unknown(logged_in, snapshot_rows, monkeypatch):
    def unmounted(tickers, *, on):
        raise DailyCacheUnavailable("daily bar cache /data/market_data is not mounted")
    monkeypatch.setattr(admin_snapshots, "_fx_inputs", unmounted)
    resp = logged_in.get("/api/v1/calendar/pnl?month=2025-01")
    assert resp.status_code == 200 and resp.get_json()["market_meta"]["as_of"] is None


@pytest.mark.parametrize("name, path", [
    ("performance_main", "/api/v1/analytics/performance?ledger=main"),
    ("equity_curve_main", "/api/v1/analytics/equity-curve?ledger=main"),
    ("calendar_pnl", f"/api/v1/calendar/pnl?month={GOLDEN_MONTH}"),
])
def test_kill_switch_off_serves_today_bodies_with_a_request_meta(golden_book, monkeypatch, name, path):
    monkeypatch.setattr(admin_snapshots, "SNAPSHOT_ROUTES", ALL_ROUTES)
    reads = []
    monkeypatch.setattr(market_values, "read_snapshot", lambda key, **k: reads.append(key))
    body = golden_book.client.get(path).get_json()
    assert_matches_golden(name, body)
    assert body["market_meta"]["source"] == "request"
    assert reads == []
