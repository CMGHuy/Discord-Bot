"""v171 D2 admin rules: reload means fresh, navigation means reuse, ages shown."""
import base64
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.admin import dashboard, freshness, watchlist_rows
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.kinds import Asker, Entry, QuoteDetail
from tests.admin.test_api_v1_trades import _open_pair
from tests.helpers import make_ohlcv
from tests.store_seed import seed_store

def _now():
    return datetime.now(timezone.utc)


def _q(sym, price, age=12.0, source="alpaca-iex"):
    at = _now() - timedelta(seconds=age)
    return QuoteDetail(symbol=sym, price=price, trade_at=at, bid=None, ask=None,
                       quote_at=None, source=source)


@pytest.fixture
def client(admin_app):
    c = admin_app.test_client()
    token = base64.b64encode(b"admin:admin").decode("ascii")
    c.environ_base["HTTP_AUTHORIZATION"] = f"Basic {token}"
    plan, trade = _open_pair(ticker="MSFT")
    seed_store("plans", [plan])
    seed_store("trades", [trade])
    return c


def _row(client, **headers):
    return client.get("/api/v1/trades?status=open", headers=headers).get_json()["items"][0]


def test_the_fresh_header_marks_only_its_own_request(admin_app):
    with admin_app.test_request_context("/api/v1/trades", headers={freshness.FRESH_HEADER: "1"}):
        admin_app.preprocess_request()
        assert kinds.is_fresh_request() is True
        admin_app.do_teardown_request()
    assert kinds.is_fresh_request() is False
    with admin_app.test_request_context("/api/v1/trades"):
        admin_app.preprocess_request()
        assert kinds.is_fresh_request() is False


def test_trade_rows_price_through_one_page_batch_with_their_age(client, layer_quotes):
    layer_quotes["quotes"]["MSFT"] = _q("MSFT", 110.0, age=12.0)
    row = _row(client)
    assert row["current_price"] == 110.0 and row["current_price_stale"] is False
    assert 11.0 <= row["price_age_s"] <= 15.0 and row["price_as_of"].startswith(str(_now().year))
    assert layer_quotes["calls"] == [(["MSFT"], Asker.ADMIN_PAGE, False)]


def test_the_dashboard_referrer_selects_the_15_s_asker(client, layer_quotes):
    layer_quotes["quotes"]["MSFT"] = _q("MSFT", 110.0)
    _row(client, Referer="http://localhost/dashboard")
    assert layer_quotes["calls"][0][1] is Asker.ADMIN_DASHBOARD


def test_a_reload_runs_fresh_and_still_at_tier_5(client, layer_quotes):
    layer_quotes["quotes"]["MSFT"] = _q("MSFT", 110.0)
    _row(client, **{freshness.FRESH_HEADER: "1"})
    (tickers, asker, fresh) = layer_quotes["calls"][0]
    assert fresh is True
    with kinds.fresh_request():
        resolved = kinds.resolve_asker(asker)
    assert resolved is Asker.ADMIN_FRESH and resolved.priority == 5


def test_empty_cache_and_short_budget_render_todays_failure_value(client, layer_quotes):
    resp = client.get("/api/v1/trades?status=open")
    row = resp.get_json()["items"][0]
    assert resp.status_code == 200 and row["current_price"] is None
    assert row["price_age_s"] is None and row["price_as_of"] is None
    assert row["progress_pct"] is None and row["status_label"]


def test_layer_off_keeps_todays_prefetch_path(client, monkeypatch):
    from swingbot.core.marketdata import data
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(data, "get_quote_batch", lambda *a, **k: pytest.fail("layer used"))
    monkeypatch.setattr(data, "prefetch_prices", lambda tickers: None)
    monkeypatch.setattr(data, "get_current_price_detail", lambda t: data.PriceQuote(110.0, False))
    row = _row(client)
    assert row["current_price"] == 110.0 and row["price_age_s"] is None


def test_the_dashboard_summary_prices_at_the_dashboard_tier(admin_app, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    seen = []
    monkeypatch.setattr(freshness, "page_quotes",
                        lambda t, *, dashboard=False: seen.append((list(t), dashboard)) or {"MSFT": _q("MSFT", 110.0)})
    monkeypatch.setattr(dashboard, "prefetch_prices", lambda t: pytest.fail("legacy prefetch"))
    monkeypatch.setattr(dashboard, "compute_position_size", lambda **k: None)
    trade = {"id": "t1", "ticker": "MSFT", "direction": "bullish", "entry": 100.0,
             "stop_loss": 90.0, "take_profit": 120.0, "opened_at": _now().isoformat()}
    views = dashboard.build_open_trade_views([trade], {})
    assert views["price"]["t1"] == 110.0 and seen == [(["MSFT"], True)]


@pytest.fixture
def overlay(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(watchlist_rows, "is_us_market_active", lambda: True)
    monkeypatch.setattr(watchlist_rows, "_cached_daily", lambda t: make_ohlcv([100.0, 101.0]))
    entry = Entry(_q("AAPL", 190.0, age=3.0), _now() - timedelta(seconds=3), "alpaca", "hit")
    monkeypatch.setattr(freshness, "cached_quotes", lambda t: {"AAPL": entry})
    warmed = []
    monkeypatch.setattr(freshness, "warm_quotes_background",
                        lambda t, **k: warmed.append(list(t)))
    return warmed


def test_the_watchlist_reads_the_shared_cache_and_warms_the_rest(overlay):
    rows = watchlist_rows.build_market_rows(["AAPL", "MSFT"])
    assert rows["AAPL"]["price"] == 190.0 and rows["AAPL"]["price_source"] == "alpaca"
    assert 2.0 <= rows["AAPL"]["price_age_s"] <= 6.0
    assert rows["MSFT"]["price"] == 101.0 and rows["MSFT"]["price_age_s"] is None
    assert overlay == [["MSFT"]]


def test_a_fresh_reload_warms_every_watchlist_symbol(overlay):
    with kinds.fresh_request():
        watchlist_rows.build_market_rows(["AAPL", "MSFT"])
    assert overlay == [["AAPL", "MSFT"]]


def test_quote_age_reads_the_trade_then_the_quote_time():
    assert freshness.quote_age(None) == (None, None)
    age, as_of = freshness.quote_age(_q("X", 1.0, age=20.0))
    assert 19.0 <= age <= 22.0 and as_of.endswith("+00:00")
    q = QuoteDetail("X", None, None, 1.0, 1.1, _now() - timedelta(seconds=5), "alpaca-iex")
    assert 4.0 <= freshness.quote_age(q)[0] <= 7.0
