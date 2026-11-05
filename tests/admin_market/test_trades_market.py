"""v201 V201-9: the Trades list and detail price from the cache with an oldest-input as_of."""
import pytest

from swingbot import config
from swingbot.core.marketdata import data
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.admin_market.test_page_loads_never_fetch import network_forbidden  # noqa: F401
from tests.store_seed import seed_store

ROW_QUOTE_FIELDS = {"current_price", "current_price_stale", "price_as_of", "price_age_s",
                    "price_refreshing", "price_error"}


def _pair(n, ticker, entry=100.0):
    plan = _plan(f"2222222{n}-2222-4222-8222-222222222222", ticker=ticker, status="ACTIVE")
    plan.update({"direction": "bullish", "entry_price": entry, "stop_loss": 90.0, "tp1": 120.0})
    trade = _trade(f"t-open-{n}", plan_id=plan["plan_id"], ticker=ticker, status="open")
    trade.update({"entry": entry, "stop_loss": 90.0, "take_profit": 120.0})
    return plan, trade


@pytest.fixture
def two_open(on_client):
    (p1, t1), (p2, t2) = _pair(1, "MSFT"), _pair(2, "NVDA")
    seed_store("plans", [p1, p2])
    seed_store("trades", [t1, t2])
    return on_client


def _items(client, query="status=open"):
    body = client.get(f"/api/v1/trades?{query}").get_json()
    return body, {r["ticker"]: r for r in body["items"]}


def test_list_rows_carry_cached_quotes_and_the_oldest_as_of(two_open, market,
                                                            network_forbidden):
    market.quote("MSFT", 110.0, age_s=10)
    market.quote("NVDA", 95.0, age_s=100)
    body, rows = _items(two_open)
    assert ROW_QUOTE_FIELDS <= set(rows["MSFT"])
    assert rows["MSFT"]["current_price"] == 110.0 and rows["MSFT"]["price_refreshing"] is False
    assert body["prices_as_of"] == rows["NVDA"]["price_as_of"]          # the older of the two
    assert body["market_meta"]["as_of"] == rows["NVDA"]["price_as_of"]
    assert body["market_meta"]["missing_count"] == 0
    assert network_forbidden == []


def test_unpriced_position_makes_the_page_incomplete(two_open, market):
    market.quote("MSFT", 110.0, age_s=10)
    body, rows = _items(two_open)
    assert rows["NVDA"]["current_price"] is None and rows["NVDA"]["price_refreshing"] is True
    assert body["market_meta"]["missing_count"] == 1 and body["market_meta"]["incomplete"] is True
    assert body["prices_as_of"] == rows["MSFT"]["price_as_of"]


def test_no_priced_row_means_no_prices_as_of(two_open, market):
    body, _ = _items(two_open)
    assert body["prices_as_of"] is None and body["market_meta"]["as_of"] is None


# `progress_pct` is sorted through its public alias `status` (`_SORT_ALIASES`).
@pytest.mark.parametrize("field", ["pnl_pct", "status", "r_multiple"])
def test_priced_sort_orders_on_cached_prices_without_a_fetch(two_open, market,
                                                             network_forbidden, field):
    market.quote("MSFT", 110.0, age_s=10)     # +10 %
    market.quote("NVDA", 115.0, age_s=10)     # +15 %
    body, _ = _items(two_open, f"status=open&sort=-{field}")
    assert [r["ticker"] for r in body["items"]] == ["NVDA", "MSFT"]
    assert network_forbidden == []


def test_trade_detail_carries_row_quote_fields_and_meta(two_open, market):
    market.quote("MSFT", 110.0, age_s=10)
    row = two_open.get("/api/v1/trades/22222221-2222-4222-8222-222222222222").get_json()
    assert ROW_QUOTE_FIELDS <= set(row) and row["current_price"] == 110.0
    assert row["market_meta"]["missing_count"] == 0 and row["market_meta"]["as_of"]


def test_refresher_off_keeps_the_now_stamp(client, auth, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(data, "prefetch_prices", lambda tickers: None)
    monkeypatch.setattr(data, "get_current_price_detail", lambda t: type(
        "D", (), {"price": 110.0, "stale": False})())
    plan, trade = _pair(1, "MSFT")
    seed_store("plans", [plan])
    seed_store("trades", [trade])
    body = client.get("/api/v1/trades?status=open", headers=auth).get_json()
    assert body["items"][0]["current_price"] == 110.0
    assert body["prices_as_of"] is not None                     # today's behaviour
    assert set(body["market_meta"]) >= {"as_of", "missing_count", "incomplete"}
