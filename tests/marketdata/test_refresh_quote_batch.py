"""v201: the refresher's batched quote call -- tier 5, always fetches, capped yfinance."""
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import side_engine
from swingbot.core.marketdata import data
from swingbot.core.marketdata.shared import layer
from swingbot.core.marketdata.shared.kinds import Asker, DataKind, QuoteDetail

NOW = datetime.now(timezone.utc)


def _q(sym, source="alpaca-iex", price=10.0):
    return QuoteDetail(sym, price, NOW, None, None, NOW, source)


@pytest.fixture
def shared(db_committed, db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    side_engine.reset()
    yield db_committed
    side_engine.reset()


@pytest.fixture
def provider(monkeypatch):
    calls = {"latest": [], "yf": []}

    def latest(tickers, yf_fetch):           # Alpaca answers nothing: every symbol falls back
        calls["latest"].append(list(tickers))
        got = yf_fetch(list(tickers))
        return {t: got.get(t) or (_q(t, "gold-api") if t == "XAUUSD" else None) for t in tickers}

    def yf(tickers):
        calls["yf"].append(list(tickers))
        return {t: _q(t, "yfinance-1m") for t in tickers}
    monkeypatch.setattr(data.router, "latest_quotes", latest)
    monkeypatch.setattr(data, "_yf_quote_details", yf)
    return calls


def test_refresh_always_fetches_and_writes_the_shared_cache(shared, provider):
    data.refresh_quote_batch(["aapl"], yf_limit=5)
    got = data.refresh_quote_batch(["AAPL"], yf_limit=5)
    assert len(provider["latest"]) == 2 and got["AAPL"].price == 10.0
    assert layer.last_cached(DataKind.QUOTE, ["AAPL"])["AAPL"].value["price"] == 10.0


def test_yfinance_fallback_is_capped_and_zero_skips_it(shared, provider):
    got = data.refresh_quote_batch(["A", "B", "C"], yf_limit=2)
    assert provider["yf"] == [["A", "B"]] and set(got) == {"A", "B"}
    provider["yf"].clear()
    assert data.refresh_quote_batch(["A", "B"], yf_limit=0) == {} and provider["yf"] == []


def test_spot_metals_are_written_for_the_never_fetch_read(shared, provider):
    got = data.refresh_quote_batch(["XAUUSD"], yf_limit=0)
    assert got["XAUUSD"].source == "gold-api"
    assert layer.last_cached(DataKind.QUOTE, ["XAUUSD"])["XAUUSD"].value["source"] == "gold-api"


def test_stop_monitor_still_fetches_past_its_window_after_a_refresher_write(shared, provider):
    data.refresh_quote_batch(["AAPL"], yf_limit=5)
    shared.execute(sa.text("UPDATE market_cache SET fetched_at = now() - interval '20 seconds'"))
    shared.commit()
    data.get_quote_batch(["AAPL"], asker=Asker.STOP_MONITOR)      # window 15 s
    assert len(provider["latest"]) == 2
