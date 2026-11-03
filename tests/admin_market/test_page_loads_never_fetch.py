"""v201 Goal 1: with the refresher on, no page-load handler reaches a market or FX provider.

Handlers swallow exceptions, so a raising fake alone proves nothing: every
forbidden call is recorded, and the test asserts the record is empty."""
import importlib

import pytest

from swingbot.core.marketdata.shared.kinds import DataKind
from tests.admin.test_api_v1_trades import _open_pair
from tests.store_seed import seed_store

PAGE_LOAD_ENDPOINTS: list[str] = [
    "/api/v1/dashboard?mode=today",
    "/api/v1/dashboard?mode=all",
    "/api/v1/market/tape?symbols=MSFT,NEWX,%5EGSPC",
    "/api/v1/watchlist/tickers",
]

FORBIDDEN: list[tuple[str, str]] = [
    ("swingbot.core.marketdata.data", "get_quote_batch"),
    ("swingbot.core.marketdata.data", "get_current_price"),
    ("swingbot.core.marketdata.data", "get_current_price_detail"),
    ("swingbot.core.marketdata.data", "get_current_price_batch"),
    ("swingbot.core.marketdata.data", "prefetch_prices"),
    ("swingbot.core.marketdata.data", "get_daily_data_batch"),
    ("swingbot.core.marketdata.data", "_provider_currency_code"),
    ("swingbot.core.marketdata.data", "warm_batch_price_cache_background"),
    ("swingbot.core.marketdata.data_refresh", "refresh_symbol"),
    ("swingbot.core.marketdata.fx", "_refreshed_frame"),
    ("swingbot.core.marketdata.yf_safe", "download"),
    ("swingbot.core.marketdata.shared.tape", "refresh_tape"),
    ("swingbot.core.analytics.snapshots", "refresh_snapshot"),
    ("swingbot.core.edge.portfolio_state", "collect_portfolio_state"),
    ("swingbot.admin.freshness", "page_quotes"),
    ("swingbot.admin.freshness", "page_daily"),
    ("swingbot.admin.freshness", "warm_quotes_background"),
    ("swingbot.admin.tape_cache", "prices"),
    ("swingbot.admin.tape_cache", "daily_frames"),
    # Imported by name (brief 0.12): patching `data` alone would miss these.
    ("swingbot.admin.dashboard", "get_current_price"),
    ("swingbot.admin.dashboard", "prefetch_prices"),
    ("swingbot.admin.watchlist_rows", "get_daily_data_batch"),
    ("swingbot.admin.watchlist_rows", "warm_batch_price_cache_background"),
]


@pytest.fixture
def network_forbidden(monkeypatch):
    calls: list[str] = []
    for module, name in FORBIDDEN:
        def boom(*args, _name=f"{module}.{name}", **kwargs):
            calls.append(_name)
            raise AssertionError(f"network call on a page load: {_name}")
        monkeypatch.setattr(importlib.import_module(module), name, boom)
    return calls


@pytest.fixture
def book(on_client, market):
    plan, trade = _open_pair(ticker="MSFT")
    seed_store("plans", [plan])
    seed_store("trades", [trade])
    seed_store("watchlist", ["MSFT", "NVDA"])
    market.quote("MSFT", 110.0, age_s=5)
    market.quote("^GSPC", 5000.0, age_s=5, kind=DataKind.INDEX_QUOTE)
    return on_client


@pytest.mark.parametrize("endpoint", PAGE_LOAD_ENDPOINTS)
def test_page_load_makes_no_network_call(book, network_forbidden, endpoint):
    resp = book.get(endpoint)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert network_forbidden == []
