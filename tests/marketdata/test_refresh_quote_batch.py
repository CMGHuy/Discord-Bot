"""v201: the refresher's batched quote call -- tier 5, always fetches, capped yfinance."""
from datetime import datetime, timezone

import pandas as pd
import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import side_engine
from swingbot.core.marketdata import data
from swingbot.core.marketdata import yf_backoff
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


# -- v248 § 4: both callers honour one shared backoff -------------------------------

@pytest.fixture
def yahoo(monkeypatch):
    """Alpaca answers only ALP; every other symbol reaches the real _yf_quote_details,
    whose download comes back empty (DOCU before the open). Returns the calls."""
    calls = {"latest": [], "download": []}

    def latest(tickers, yf_fetch):
        tickers = list(tickers)
        calls["latest"].append(tickers)
        out = {t: _q(t) for t in tickers if t == "ALP"}
        out.update(yf_fetch([t for t in tickers if t != "ALP"]) or {})
        return out

    def download(symbols, *a, **k):
        calls["download"].append(symbols)
        return pd.DataFrame()
    monkeypatch.setattr(data.router, "latest_quotes", latest)
    monkeypatch.setattr(data.yf_safe, "download", download)
    monkeypatch.setattr(yf_backoff, "held_symbols", lambda now=None: frozenset())
    yf_backoff._reset_for_tests()
    return calls


def test_refresher_batch_stops_asking_yahoo_after_three_misses(shared, yahoo):
    for _ in range(3):
        assert data.refresh_quote_batch(["DOCU"], yf_limit=5) == {}
    assert yahoo["download"] == ["DOCU"] * 3
    assert data.refresh_quote_batch(["DOCU"], yf_limit=5) == {}
    assert yahoo["download"] == ["DOCU"] * 3                      # 4th cycle: skipped


def test_bot_quote_read_honours_the_refresher_backoff(shared, yahoo):
    for _ in range(3):
        data.refresh_quote_batch(["DOCU"], yf_limit=5)
    side_engine.reset()                                           # the bot is another client
    got = data.get_quote_batch(["DOCU"], asker=Asker.STOP_MONITOR, max_age_s=0)
    assert ["DOCU"] in yahoo["latest"][3:]                        # the bot path did ask
    assert got == {} and yahoo["download"] == ["DOCU"] * 3        # ...but never reached Yahoo


def test_alpaca_is_never_skipped_by_the_yahoo_backoff(shared, yahoo):
    for _ in range(3):
        yf_backoff.record(yf_backoff.partition(["ALP"]), [])
    assert yf_backoff.partition(["ALP"]).skipped == ["ALP"]
    got = data.refresh_quote_batch(["ALP"], yf_limit=5)
    assert got["ALP"].price == 10.0 and yahoo["download"] == []
