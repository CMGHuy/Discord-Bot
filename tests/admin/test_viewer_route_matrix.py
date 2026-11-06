"""v207: the viewer route matrix (spec § Testing).

- Every viewer-classified GET answers a viewer 2xx with fixture data, and the
  same status the admin gets for the same URL.
- Every admin-classified rule x method answers a viewer 403 forbidden, and a
  sweep of viewer writes leaves the book untouched.
- /dashboard and /live: the viewer's payload has the admin's keys and none
  naming users or credentials.
- Viewer credentials over HTTP Basic are 401 (Decision 7); a viewer session
  plus an admin Basic header is still the viewer.

GET side-effect audit (2026-11-05, V207-7): /market/chart/<ticker> backfills a
stored trendline fit (idempotent cache fill), /market/tape records demand and
refreshes stale quotes (cache warming), /market/updates reads with
enqueue=False, /live only reads. None changes the book, settings or the
watchlist, so all stay "viewer" in tests/admin/access_expectations.py.
"""
import base64

import numpy as np
import pandas as pd
import pytest
from tests.admin.access_expectations import EXPECTATIONS, SAMPLE_PATHS
from tests.admin.api_v1_contract import assert_error
from tests.store_seed import seed_store

from swingbot.admin import api_v1 as v1  # noqa: F401  (reload-safe import idiom)

#: SSE never ends; V207-8 covers /events (tests/admin/test_event_stream.py).
STREAMING = {"/api/v1/events"}

#: Query strings a GET needs to answer 2xx (tests/admin/test_api_v1_*.py use the same).
QUERIES = {
    "/api/v1/analytics/by-dimension": "?dim=strategy",
    "/api/v1/analytics/cohort": "?origin=next_session",
    "/api/v1/analytics/soak": "?strategy=RSI%20Divergence",
    "/api/v1/calendar/pnl/day": "?date=2026-08-04",
    "/api/v1/calendar/pnl/day/sparklines": "?date=2026-08-04",
    "/api/v1/market/tape": "?symbols=AAPL",
    "/api/v1/watchlist/suggest": "?q=AA",
}

#: Keys that would mean a Users or session secret leaked into a read payload.
LEAK_KEYS = {"password_hash", "credential_version", "pw_hash", "admin_authed", "users", "user_id"}

VIEWER_GETS = sorted(rule for (rule, method), kind in EXPECTATIONS.items()
                     if kind == "viewer" and method == "GET" and rule not in STREAMING)
ADMIN_CASES = sorted(key for key, kind in EXPECTATIONS.items() if kind == "admin")
WRITE_METHODS = {"POST", "PUT", "PATCH"}


def _trade(trade_id: str) -> dict:
    """One closed AAPL trade -- the shape tests/admin/test_api_v1_trades.py seeds."""
    return {
        "id": trade_id, "plan_id": None, "ticker": "AAPL", "strategy": "RSI Divergence",
        "horizon_key": "1m", "direction": "bullish", "confidence_level": 4,
        "confidence_label": "High", "confidence_score": 81.0, "entry": 101.0,
        "stop_loss": 95.0, "take_profit": 110.0, "target2": None, "risk_reward_ratio": 1.8,
        "tier": "A", "badge": "VALIDATED", "quality_score": 72, "source": "strategy",
        "legs": [], "opened_at": "2026-08-01T10:00:00+00:00", "status": "win",
        "closed_at": "2026-08-04T15:00:00+00:00", "exit_price": 108.0,
        "realized_pnl_amount": 70.0, "shares": 10, "position_value": 1010.0,
        "target_sources": [], "stop_sources": [], "target2_sources": [],
        "confirmed_by": [], "explanation": None, "confidence_breakdown": None,
    }


def _frame(n: int = 300) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=n)
    close = pd.Series(50 + np.cumsum(np.random.default_rng(3).normal(0, .5, n)), index=idx)
    return pd.DataFrame({"Open": close, "High": close + .5, "Low": close - .5,
                         "Close": close, "Volume": 9_999}, index=idx)


@pytest.fixture
def _book(admin_app):
    """Trade "t1" and watchlist ticker "AAPL": the ids SAMPLE_PATHS names."""
    seed_store("trades", [_trade("t1")])
    seed_store("watchlist", ["AAPL"])


@pytest.fixture
def _offline(monkeypatch):
    """Every network edge the readable GETs touch, stubbed as their own tests do."""
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda ticker: _frame())
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data_batch", lambda syms: {})
    monkeypatch.setattr("swingbot.core.marketdata.data.get_company_name", lambda t: f"{t} Inc.")
    monkeypatch.setattr("swingbot.core.market.events.get_next_earnings_datetime", lambda t: None)
    monkeypatch.setattr("swingbot.admin.watchlist_rows.get_daily_data_batch",
                        lambda tickers, period="6mo": {})
    monkeypatch.setattr("swingbot.admin.watchlist_rows.is_us_market_active", lambda: False)
    monkeypatch.setattr("swingbot.core.marketdata.backtest_cache.ensure_cached_background",
                        lambda t: None)


@pytest.fixture
def admin_get(admin_app, auth):
    """The admin on a SECOND client: the viewer's cookie would win over Basic."""
    other = admin_app.test_client()
    return lambda url: other.get(url, headers=auth)


def _url(rule: str) -> str:
    return SAMPLE_PATHS.get(rule, rule) + QUERIES.get(rule, "")


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def _basic(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_the_matrix_is_not_empty():
    assert len(VIEWER_GETS) >= 40 and len(ADMIN_CASES) >= 40


@pytest.mark.parametrize("rule", VIEWER_GETS)
def test_a_viewer_reads_every_viewer_get_with_data(viewer_client, admin_get, _book, _offline, rule):
    client, _row = viewer_client
    url = _url(rule)
    theirs = admin_get(url)
    assert 200 <= theirs.status_code < 300, f"fixture gap for {url}: admin got {theirs.status_code}"
    mine = client.get(url)
    assert mine.status_code == theirs.status_code, (url, mine.get_data(as_text=True)[:200])


@pytest.mark.parametrize("rule,method", ADMIN_CASES)
def test_a_viewer_is_refused_every_admin_rule(viewer_client, rule, method):
    client, _row = viewer_client
    body = {} if method in WRITE_METHODS else None
    assert_error(client.open(SAMPLE_PATHS.get(rule, rule), method=method, json=body),
                 "forbidden", 403)


def test_a_sweep_of_viewer_writes_changes_nothing(viewer_client, admin_get, _book, _offline):
    client, _row = viewer_client
    for rule, method in ADMIN_CASES:
        if method != "GET":
            client.open(SAMPLE_PATHS.get(rule, rule), method=method,
                        json={} if method in WRITE_METHODS else None)
    assert admin_get("/api/v1/trades/t1").status_code == 200
    tickers = admin_get("/api/v1/watchlist/tickers").get_json()
    assert "AAPL" in str(tickers)


@pytest.mark.parametrize("path", ["/api/v1/dashboard", "/api/v1/live"])
def test_viewer_payloads_carry_the_admins_keys_and_no_secrets(viewer_client, admin_get,
                                                              _book, _offline, path):
    client, _row = viewer_client
    mine, theirs = client.get(path), admin_get(path)
    assert mine.status_code == theirs.status_code == 200
    assert _keys(mine.get_json()) == _keys(theirs.get_json())
    assert not _keys(mine.get_json()) & LEAK_KEYS


def test_viewer_credentials_over_basic_are_401(admin_app, viewer_client):
    fresh = admin_app.test_client()
    r = fresh.get("/api/v1/dashboard", headers=_basic("viewer1", "viewer-password-1"))
    assert_error(r, "auth", 401)


def test_a_viewer_session_with_an_admin_basic_header_is_still_the_viewer(viewer_client, auth):
    client, _row = viewer_client
    assert_error(client.get("/api/v1/system/settings", headers=auth), "forbidden", 403)
    assert client.get("/api/v1/session").get_json()["role"] == "viewer"
