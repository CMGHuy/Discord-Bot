"""v171 D1/D2: the data.py quote API goes through the shared layer at the
caller's asker; trading callers stay fresh-only; off mode is pre-v171."""
import time
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata import data
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared import layer
from swingbot.core.marketdata.shared.kinds import (PROVIDER_ALPACA, Asker, DataKind,
                                                   Entry, QuoteDetail)

NOW = datetime.now(timezone.utc)


def _q(sym, price=190.0, age=1.0, bid=None, ask=None, source="alpaca-iex"):
    at = NOW - timedelta(seconds=age)
    return QuoteDetail(symbol=sym, price=price, trade_at=at if price else None,
                       bid=bid, ask=ask, quote_at=at if bid else None, source=source)


def _entry(q, outcome="fetched", age=0.0):
    return Entry(value=q, fetched_at=datetime.now(timezone.utc) - timedelta(seconds=age),
                 source=q.source, outcome=outcome)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(config, "QUOTE_MAX_AGE_MONITOR_S", 15)
    data._last_good_batch_price.clear()
    data._price_cache.clear()
    yield
    data._last_good_batch_price.clear()
    data._price_cache.clear()


@pytest.fixture
def mode(monkeypatch):
    def set_mode(value):
        monkeypatch.setattr(config, "MARKETDATA_LAYER", value)
    return set_mode


@pytest.fixture
def fake_layer(monkeypatch):
    rec = {"calls": [], "entries": {}}

    def get(kind, symbols, fetch, **kw):
        rec["calls"].append({"kind": kind, "symbols": list(symbols), "fetch": fetch,
                             "scoped": router.current_asker(), **kw})
        return {s: rec["entries"][s] for s in symbols if s in rec["entries"]}
    monkeypatch.setattr(layer, "get", get)
    return rec


def test_off_mode_price_batch_is_the_pre_v171_function(mode, fake_layer, monkeypatch):
    mode("off")
    seen = []
    monkeypatch.setattr(data, "_price_batch_legacy",
                        lambda tickers, *, allow_stale: seen.append((tickers, allow_stale)) or {"AAPL": 1.0})
    assert data.get_current_price_batch(["AAPL"], allow_stale=False) == {"AAPL": 1.0}
    assert seen == [(["AAPL"], False)] and fake_layer["calls"] == []


def test_quote_batch_asks_the_layer_once_at_the_asker(mode, fake_layer):
    mode("on")
    fake_layer["entries"]["AAPL"] = _entry(_q("AAPL"))
    out = data.get_quote_batch(["aapl", " AAPL"], asker=Asker.STOP_MONITOR)
    assert out == {"AAPL": fake_layer["entries"]["AAPL"].value}
    [call] = fake_layer["calls"]
    assert call["kind"] is DataKind.QUOTE and call["symbols"] == ["AAPL"]
    assert call["asker"] is Asker.STOP_MONITOR and call["provider"] == PROVIDER_ALPACA
    assert call["scoped"] is Asker.STOP_MONITOR          # inside router.asker_scope
    assert call["encode"] == QuoteDetail.to_doc and call["decode"] == QuoteDetail.from_doc


def test_layer_fetch_is_router_latest_quotes_with_the_yf_minute_fallback(mode, fake_layer, monkeypatch):
    mode("on")
    seen = []
    monkeypatch.setattr(router, "latest_quotes",
                        lambda syms, yf_fetch: seen.append((syms, yf_fetch)) or {})
    data.get_quote_batch(["AAPL"], asker=Asker.SCAN)
    fake_layer["calls"][0]["fetch"](["AAPL"])
    assert seen == [(["AAPL"], data._yf_quote_details)]


def test_spot_metal_never_reaches_the_layer(mode, fake_layer, monkeypatch):
    mode("on")
    spot = _q("XAUUSD", 2400.0, source="spot")
    direct = []
    monkeypatch.setattr(router, "latest_quotes",
                        lambda syms, yf_fetch: direct.append(list(syms)) or {"XAUUSD": spot})
    fake_layer["entries"]["AAPL"] = _entry(_q("AAPL"))
    out = data.get_quote_batch(["XAUUSD", "AAPL"], asker=Asker.STOP_MONITOR)
    assert fake_layer["calls"][0]["symbols"] == ["AAPL"]
    assert direct == [["XAUUSD"]] and out["XAUUSD"] is spot


def test_fresh_only_drops_deferred_and_over_window_entries(mode, fake_layer):
    mode("on")
    fake_layer["entries"].update({
        "AAPL": _entry(_q("AAPL"), "fetched", age=1.0),
        "MSFT": _entry(_q("MSFT"), "budget-deferred", age=1.0),
        "NVDA": _entry(_q("NVDA"), "hit", age=40.0),
    })
    syms = ["AAPL", "MSFT", "NVDA"]
    assert set(data.get_quote_batch(syms, asker=Asker.STOP_MONITOR, fresh_only=True)) == {"AAPL"}
    assert set(data.get_quote_batch(syms, asker=Asker.STOP_MONITOR)) == set(syms)


def test_explicit_max_age_sets_the_fresh_only_window(mode, fake_layer):
    mode("on")
    fake_layer["entries"]["AAPL"] = _entry(_q("AAPL"), "hit", age=7.0)
    assert data.get_quote_batch(["AAPL"], asker=Asker.REQUOTE, max_age_s=5, fresh_only=True) == {}
    assert fake_layer["calls"][0]["max_age_s"] == 5


@pytest.fixture
def quotes(monkeypatch):
    """Fakes the layer read the price paths share: rec["out"] maps a ticker
    to a QuoteDetail (fresh) or a (QuoteDetail, fresh) pair."""
    rec = {"calls": [], "out": {}}

    def fake(tickers, *, asker, max_age_s=None):
        rec["calls"].append({"tickers": list(tickers), "asker": asker})
        return {t: v if isinstance(v, tuple) else (v, True) for t, v in rec["out"].items()}
    monkeypatch.setattr(data, "_marked_quotes", fake)
    return rec


def test_trading_batch_is_fresh_only_with_no_last_good_fallback(mode, quotes):
    mode("on")
    quotes["out"] = {"AAPL": (_q("AAPL", 191.0), False)}
    data._last_good_batch_price["AAPL"] = (190.0, time.monotonic())
    assert data.get_current_price_batch(["AAPL"], allow_stale=False) == {}


def test_display_batch_falls_back_to_last_good(mode, quotes):
    mode("on")
    data._last_good_batch_price["AAPL"] = (190.0, time.monotonic() - 60)
    assert data.get_current_price_batch(["AAPL"]) == {"AAPL": 190.0}


def test_display_batch_serves_a_non_fresh_layer_value_without_caching_it(mode, quotes):
    mode("on")
    quotes["out"] = {"AAPL": (_q("AAPL", 191.0), False)}
    assert data.get_current_price_batch(["AAPL"]) == {"AAPL": 191.0}
    assert "AAPL" not in data._last_good_batch_price


def test_batch_skips_quotes_without_a_trade_price(mode, quotes):
    mode("on")
    quotes["out"] = {"AAPL": _q("AAPL", None, bid=189.0, ask=191.0), "MSFT": _q("MSFT", 410.0)}
    assert data.get_current_price_batch(["AAPL", "MSFT"], allow_stale=False) == {"MSFT": 410.0}
    assert data._last_good_batch_price["MSFT"][0] == 410.0


def test_batch_forwards_its_asker(mode, quotes):
    mode("on")
    data.get_current_price_batch(["AAPL"], asker=Asker.BACKGROUND)
    assert quotes["calls"][0]["asker"] is Asker.BACKGROUND


def test_count_mode_keeps_the_in_process_display_short_circuit(mode, quotes):
    mode("count")
    data._last_good_batch_price["AAPL"] = (190.0, time.monotonic())
    assert data.get_current_price_batch(["AAPL"]) == {"AAPL": 190.0}
    assert quotes["calls"] == []
    mode("on")
    data.get_current_price_batch(["AAPL"])
    assert len(quotes["calls"]) == 1


def test_price_detail_carries_as_of_and_age(mode, quotes):
    mode("on")
    q = _q("AAPL", 190.0, age=3.0)
    quotes["out"] = {"AAPL": q}
    detail = data.get_current_price_detail("AAPL")
    assert (detail.price, detail.stale, detail.as_of) == (190.0, False, q.trade_at)
    assert 2.5 < detail.age_s < 30
    assert quotes["calls"][0]["asker"] is Asker.ADMIN_PAGE


def test_get_current_price_forwards_asker_and_fresh_only(mode, quotes, monkeypatch):
    mode("on")
    monkeypatch.setattr(data, "_detail_from_yfinance",
                        lambda key, cached, now, allow_stale: None)
    quotes["out"] = {"AAPL": _q("AAPL", 190.0)}
    assert data.get_current_price("AAPL", allow_stale=False, asker=Asker.STOP_MONITOR) == 190.0
    assert quotes["calls"][0]["asker"] is Asker.STOP_MONITOR
    quotes["out"] = {"AAPL": (_q("AAPL", 190.0), False)}
    assert data.get_current_price("AAPL", allow_stale=False, asker=Asker.STOP_MONITOR) is None


def test_price_detail_layer_miss_falls_back_to_the_yfinance_history_path(mode, quotes, monkeypatch):
    mode("on")
    monkeypatch.setattr(data, "_detail_from_yfinance",
                        lambda key, cached, now, allow_stale: data.PriceQuote(5.0, True))
    assert data.get_current_price_detail("SAP.DE") == data.PriceQuote(5.0, True)


def test_price_detail_off_mode_is_the_pre_v171_function(mode, quotes, monkeypatch):
    mode("off")
    monkeypatch.setattr(data, "_price_detail_legacy",
                        lambda ticker, ttl_seconds, allow_stale: data.PriceQuote(1.0, False))
    assert data.get_current_price_detail("AAPL") == data.PriceQuote(1.0, False)
    assert quotes["calls"] == []


@pytest.mark.parametrize("outcome, age", [("budget-deferred", 1.0), ("hit", 40.0)])
def test_price_detail_flags_a_deferred_or_over_window_layer_value_stale(mode, fake_layer, outcome, age):
    mode("on")
    fake_layer["entries"]["AAPL"] = _entry(_q("AAPL", 190.0), outcome, age=age)
    detail = data.get_current_price_detail("AAPL", asker=Asker.STOP_MONITOR)
    assert (detail.price, detail.stale) == (190.0, True)
    assert "AAPL" not in data._price_cache          # never re-stamped as a fresh observation


def test_price_detail_fresh_layer_value_is_live_and_cached(mode, fake_layer):
    mode("on")
    fake_layer["entries"]["AAPL"] = _entry(_q("AAPL", 190.0), "hit", age=1.0)
    detail = data.get_current_price_detail("AAPL", asker=Asker.STOP_MONITOR)
    assert (detail.price, detail.stale) == (190.0, False)
    assert data._price_cache["AAPL"][0] == 190.0


def test_display_batch_never_restamps_a_deferred_value_as_last_good(mode, fake_layer):
    mode("on")
    fake_layer["entries"]["AAPL"] = _entry(_q("AAPL", 190.0), "budget-deferred", age=600.0)
    assert data.get_current_price_batch(["AAPL"], asker=Asker.ADMIN_PAGE) == {"AAPL": 190.0}
    assert "AAPL" not in data._last_good_batch_price


def test_admin_fresh_request_counts_a_just_fetched_value_as_fresh(mode, fake_layer):
    from swingbot.core.marketdata.shared.kinds import fresh_request
    mode("on")
    fake_layer["entries"]["AAPL"] = _entry(_q("AAPL", 190.0), "fetched", age=0.01)
    with fresh_request():
        detail = data.get_current_price_detail("AAPL")
        assert set(data.get_quote_batch(["AAPL"], asker=Asker.ADMIN_PAGE, fresh_only=True)) == {"AAPL"}
    assert detail.stale is False


def test_price_detail_count_mode_cache_hit_never_asks_the_layer(mode, quotes):
    mode("count")
    data._price_cache["AAPL"] = (190.0, time.monotonic(), False)
    assert data.get_current_price_detail("AAPL") == data.PriceQuote(190.0, False)
    assert quotes["calls"] == []


def test_price_detail_spot_metal_takes_the_spot_path_in_on_mode(mode, quotes, monkeypatch):
    mode("on")
    seen = []
    monkeypatch.setattr(data, "_spot_price_detail",
                        lambda key, cached, now, allow_stale: seen.append(key) or data.PriceQuote(2400.0, False))
    assert data.get_current_price_detail("xauusd") == data.PriceQuote(2400.0, False)
    assert seen == ["XAUUSD"] and quotes["calls"] == []
