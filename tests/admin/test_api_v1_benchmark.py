# tests/admin/test_api_v1_benchmark.py
"""v208: GET /api/v1/analytics/benchmark -- params, clamp, capture, paging, empty state."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from swingbot.admin.api_v1 import benchmark as benchmark_api
from swingbot.core.db.repositories.benchmark_bars import benchmark_bars_repo
from swingbot.core.db.repositories.equity_samples import EquitySampleRepository
from tests.admin.api_v1_contract import NULLABLE_STR, assert_error, assert_shape
from tests.store_seed import seed_store

URL = "/api/v1/analytics/benchmark"
BASE = 10000.0
# Fri 2026-10-16, 17:00 New York: the session is closed and final.
NOW = datetime(2026, 10, 16, 21, 0, tzinfo=timezone.utc)
SESSIONS = [date(2026, 10, 12) + timedelta(days=i) for i in range(5)]   # Mon..Fri
SYMBOLS = ("SPY", "QQQ", "^IXIC", "^DJI")

BODY = {"range": dict, "as_of": str, "session_state": str, "account_currency": str,
        "mixed_tickers": list, "benchmarks_status": str, "benchmarks_last_session": NULLABLE_STR,
        "today": (dict, type(None)), "series": list, "markers": list, "exposure": list,
        "stats": dict, "vs": dict, "capture": dict, "daily": list, "daily_has_more": bool}


@pytest.fixture
def logged_in(client):
    from swingbot.admin import app

    response = client.post("/api/v1/session", json={
        "username": app.ADMIN_USERNAME, "password": app.ADMIN_PASSWORD})
    assert response.status_code == 200
    return client


@pytest.fixture
def frozen(admin_app, monkeypatch):
    seed_store("account", {"base_balance": BASE, "balance": BASE, "risk_pct": 1.0,
                           "max_position_pct": 20.0, "sizing_mode": "risk_pct",
                           "balance_history": []})
    monkeypatch.setattr(benchmark_api, "_now", lambda: NOW)
    monkeypatch.setattr(benchmark_api, "_trades", lambda: [])


def _sample(day: date, hour: int, minute: int, value: float) -> dict:
    return {"at": datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc),
            "realized_balance": Decimal(str(BASE)),
            "unrealized_pnl": Decimal(str(value - BASE)), "equity": Decimal(str(value)),
            "open_n": 1, "skipped_n": 0, "source": "live", "kind": "point", "backfill_run": None}


def _seed_week():
    rows = []
    for i, day in enumerate(SESSIONS):
        rows += [_sample(day, 13, 35, BASE + 10 * i), _sample(day, 19, 55, BASE + 20 * i)]
    EquitySampleRepository().upsert_many(rows)
    benchmark_bars_repo().upsert_bars([
        {"symbol": s, "session": day, "close": 100.0 + i, "adj_close": 100.0 + i,
         "day_pct": 0.002 * (1 if i % 2 else -1), "source_symbol": s, "final": True,
         "as_of": NOW}
        for s in SYMBOLS for i, day in enumerate(SESSIONS)])


def test_the_route_requires_auth(client):
    assert_error(client.get(URL), "auth", 401)


@pytest.mark.parametrize("query, message", [
    ("ledger=main", "unknown parameter 'ledger'; allowed: ['from', 'to', 'capture', 'limit', 'before']"),
    ("strategy=RSI", "unknown parameter 'strategy'"),
    ("currency=usd", "unknown parameter 'currency'"),
    ("from=2026-13-01", "from must be a YYYY-MM-DD date"),
    ("before=yesterday", "before must be a YYYY-MM-DD date"),
    ("from=2026-10-15&to=2026-10-13", "from must be on or before to"),
    ("capture=DIA", "capture must be one of SPY, QQQ, ^IXIC, ^DJI"),
    ("limit=0", "limit must be one of 1..500"),
    ("limit=501", "limit must be one of 1..500"),
])
def test_bad_params_are_a_400(frozen, logged_in, query, message):
    response = logged_in.get(f"{URL}?{query}")
    assert_error(response, "invalid", 400)
    assert message in response.get_json()["error"]["message"]


def test_an_empty_book_is_a_200_that_says_no_data_never_zeros(frozen, logged_in):
    body = logged_in.get(URL).get_json()
    assert_shape(body, BODY)
    assert body["benchmarks_status"] == "empty"
    assert body["daily"] == [] and body["daily_has_more"] is False


def test_a_range_before_the_live_book_clamps_to_live_since(frozen, logged_in):
    _seed_week()
    body = logged_in.get(f"{URL}?from=2026-09-01").get_json()
    assert_shape(body, BODY)
    assert body["range"]["live_since"] == "2026-10-12"
    assert body["range"]["from"] == "2026-10-12"
    assert body["range"]["clamped"] is True
    assert body["session_state"] == "closed"
    assert {s["key"] for s in body["series"]} == {"bot_account", "bot_deployed", *SYMBOLS}


def test_the_capture_param_picks_the_index(frozen, logged_in):
    _seed_week()
    assert logged_in.get(URL).get_json()["capture"]["index"] == "SPY"
    assert logged_in.get(f"{URL}?capture=QQQ").get_json()["capture"]["index"] == "QQQ"


def test_daily_pages_newest_first_with_before(frozen, logged_in):
    _seed_week()
    full = logged_in.get(f"{URL}?limit=500").get_json()["daily"]
    assert len(full) >= 3
    dates = [row["date"] for row in full]
    assert dates == sorted(dates, reverse=True)
    first = logged_in.get(f"{URL}?limit=2").get_json()
    assert first["daily"] == full[:2] and first["daily_has_more"] is True
    second = logged_in.get(f"{URL}?limit=2&before={full[1]['date']}").get_json()
    assert second["daily"] == full[2:4]
    assert second["daily_has_more"] is (len(full) > 4)


def test_page_daily_keeps_rows_strictly_before_the_cursor():
    rows = [{"date": d} for d in ("2026-10-16", "2026-10-15", "2026-10-14")]
    assert benchmark_api._page_daily(rows, None, 2) == (rows[:2], True)
    assert benchmark_api._page_daily(rows, date(2026, 10, 15), 2) == (rows[2:], False)
    assert benchmark_api._page_daily([], None, 120) == ([], False)


def test_a_non_usd_account_and_a_non_usd_ticker_reach_the_response(frozen, logged_in, monkeypatch):
    _seed_week()
    trades = [{"id": "a" * 16, "ticker": "SAP.DE", "status": "open", "ledger": "main"},
              {"id": "b" * 16, "ticker": "AAPL", "status": "open", "ledger": "main"}]
    monkeypatch.setattr(benchmark_api, "_trades", lambda: trades)
    monkeypatch.setattr(benchmark_api.fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(benchmark_api.fx, "quote_currency_code",
                        lambda t, **_kw: "EUR" if t == "SAP.DE" else "USD")
    body = logged_in.get(URL).get_json()
    assert body["account_currency"] == "EUR"
    assert body["mixed_tickers"] == ["SAP.DE"]


def test_mixed_tickers_skip_unknown_codes_and_old_closed_trades(monkeypatch):
    monkeypatch.setattr(benchmark_api.fx, "quote_currency_code",
                        lambda t, **_kw: {"BMW.DE": "EUR", "VOD.L": "GBp"}.get(t))
    trades = [{"ticker": "BMW.DE", "status": "win", "closed_at": "2026-09-01T15:00:00+00:00"},
              {"ticker": "VOD.L", "status": "loss", "closed_at": "2026-10-14T15:00:00+00:00"},
              {"ticker": "XYZ", "status": "open"}]
    assert benchmark_api._mixed_tickers(trades, date(2026, 10, 12)) == ["VOD.L"]


def test_a_viewer_can_read_the_benchmark(frozen, viewer_client):
    client, _row = viewer_client
    assert client.get(URL).status_code == 200
