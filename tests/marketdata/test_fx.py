"""v194 B7: the FX rate provider behind the admin's account-currency money.

Every test isolates the module's two per-process memos and replaces the
cache writer/reader, so nothing here touches the network or `market_data/`.
"""
from datetime import date, datetime

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import fx


def _frame(closes: dict[str, float]) -> pd.DataFrame:
    index = pd.DatetimeIndex(list(closes))
    values = list(closes.values())
    return pd.DataFrame({"Open": values, "High": values, "Low": values,
                         "Close": values, "Volume": [0] * len(values)}, index=index)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(fx, "_frames", {})
    monkeypatch.setattr(fx, "_quote_codes", {})


@pytest.fixture
def cache(monkeypatch):
    """The pair files a test puts here are what `load_normalized` returns;
    `refreshed` records every `refresh_symbol` call."""
    frames: dict[str, pd.DataFrame] = {}
    refreshed: list[tuple[str, str]] = []

    def refresh(symbol, timeframe, *args, **kwargs):
        refreshed.append((symbol, timeframe))
        return {"status": "fresh"}

    monkeypatch.setattr(fx.data_refresh, "refresh_symbol", refresh)
    monkeypatch.setattr(fx.data_store, "load_normalized", lambda symbol, interval, *a, **k: frames.get(symbol))
    return frames, refreshed


# -- fx_rate ----------------------------------------------------------------

def test_same_currency_is_identity_with_no_fetch(cache):
    _, refreshed = cache
    assert fx.fx_rate("EUR", "EUR", date(2026, 10, 20)) == 1.0
    assert fx.fx_rate("usd", "USD", date(2026, 10, 20)) == 1.0
    assert refreshed == []


def test_converts_at_the_exit_dates_close(cache):
    frames, refreshed = cache
    frames["USDEUR=X"] = _frame({"2026-10-19": 0.91, "2026-10-20": 0.92, "2026-10-21": 0.93})
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) == pytest.approx(0.92)
    assert refreshed == [("USDEUR=X", "daily")]


def test_falls_back_to_the_last_prior_trading_days_close(cache):
    frames, _ = cache
    frames["USDEUR=X"] = _frame({"2026-10-16": 0.90, "2026-10-19": 0.91})
    # Sunday 2026-10-18 has no bar: Friday's close stands.
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 18)) == pytest.approx(0.90)


def test_never_reaches_past_the_fallback_window(cache):
    frames, _ = cache
    frames["USDEUR=X"] = _frame({"2026-10-01": 0.90})
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 1 + fx.FALLBACK_DAYS)) == pytest.approx(0.90)
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 2 + fx.FALLBACK_DAYS)) is None


def test_never_uses_a_later_close(cache):
    frames, _ = cache
    frames["USDEUR=X"] = _frame({"2026-10-21": 0.93})
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) is None


def test_a_missing_pair_is_none_never_one(cache):
    _, refreshed = cache
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) is None
    # The miss is remembered: a page of 200 rows asks the cache once.
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 21)) is None
    assert refreshed == [("USDEUR=X", "daily")]


@pytest.mark.parametrize("closes", [
    {},
    {"2026-10-20": float("nan")},
    {"2026-10-20": 0.0},
    {"2026-10-20": -1.0},
])
def test_an_unusable_close_is_none(cache, closes):
    frames, _ = cache
    frames["USDEUR=X"] = _frame(closes)
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) is None


@pytest.mark.parametrize("src,dst", [("", "EUR"), ("USD", ""), (None, "EUR"), ("USD", None)])
def test_an_unknown_code_is_none(cache, src, dst):
    assert fx.fx_rate(src, dst, date(2026, 10, 20)) is None


def test_minor_units_scale_to_their_major_currency(cache):
    frames, _ = cache
    frames["GBPEUR=X"] = _frame({"2026-10-20": 1.15})
    assert fx.fx_rate("GBp", "GBP", date(2026, 10, 20)) == pytest.approx(0.01)
    assert fx.fx_rate("GBp", "EUR", date(2026, 10, 20)) == pytest.approx(0.0115)


def test_a_datetime_is_read_as_its_date(cache):
    frames, _ = cache
    frames["USDEUR=X"] = _frame({"2026-10-20": 0.92})
    assert fx.fx_rate("USD", "EUR", datetime(2026, 10, 20, 21, 5)) == pytest.approx(0.92)


def test_a_failed_refresh_still_reads_what_the_cache_has(cache, monkeypatch):
    frames, _ = cache
    frames["USDEUR=X"] = _frame({"2026-10-20": 0.92})

    def boom(*args, **kwargs):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(fx.data_refresh, "refresh_symbol", boom)
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) == pytest.approx(0.92)


def test_a_loaded_pair_is_reused_within_the_ttl(cache, monkeypatch):
    frames, refreshed = cache
    frames["USDEUR=X"] = _frame({"2026-10-20": 0.92})
    clock = iter([1000.0, 1000.0 + fx.FRAME_TTL_S - 1, 1000.0 + fx.FRAME_TTL_S + 1])
    monkeypatch.setattr(fx, "_clock", lambda: next(clock))
    for _ in range(3):
        fx.fx_rate("USD", "EUR", date(2026, 10, 20))
    assert len(refreshed) == 2


# -- account_currency_code ----------------------------------------------------

@pytest.mark.parametrize("symbol,code", [
    ("€", "EUR"), ("$", "USD"), ("£", "GBP"), ("¥", "JPY"), ("CHF", "CHF"),
    ("USD", "USD"), (" € ", "EUR"), ("?", "EUR"), ("", "EUR"), ("GBp", "EUR"),
])
def test_account_currency_code_inverts_the_symbol_table(monkeypatch, symbol, code):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", symbol)
    assert fx.account_currency_code() == code


# -- quote_currency_code ------------------------------------------------------

def test_quote_currency_code_is_the_tickers_own_and_memoised(monkeypatch):
    calls = []

    def lookup(key):
        calls.append(key)
        return {"AAPL": ("USD", True), "ASML.AS": ("EUR", True), "VOD.L": ("GBp", True)}[key]

    monkeypatch.setattr(fx.data, "_provider_currency_code", lookup)
    assert fx.quote_currency_code(" aapl ") == "USD"
    assert fx.quote_currency_code("ASML.AS") == "EUR"
    assert fx.quote_currency_code("VOD.L") == "GBp"
    assert fx.quote_currency_code("AAPL") == "USD"
    assert calls == ["AAPL", "ASML.AS", "VOD.L"]


@pytest.mark.parametrize("reply", [(None, True), ("", True), ("USD", False), (None, False)])
def test_quote_currency_code_is_none_when_unknown_and_not_remembered(monkeypatch, reply):
    calls = []
    monkeypatch.setattr(fx.data, "_provider_currency_code", lambda key: calls.append(key) or reply)
    assert fx.quote_currency_code("XYZ") is None
    assert fx.quote_currency_code("XYZ") is None
    assert calls == ["XYZ", "XYZ"]


def test_quote_currency_code_survives_a_failed_lookup(monkeypatch):
    def boom(key):
        raise RuntimeError("metadata down")

    monkeypatch.setattr(fx.data, "_provider_currency_code", boom)
    assert fx.quote_currency_code("AAPL") is None
    assert fx.quote_currency_code("") is None
    assert fx.quote_currency_code(None) is None


def test_a_pence_quoted_ticker_converts_at_one_hundredth_of_the_pound(cache, monkeypatch):
    frames, _ = cache
    frames["GBPEUR=X"] = _frame({"2026-10-20": 1.15})
    monkeypatch.setattr(fx.data, "_provider_currency_code", lambda key: ("GBp", True))
    code = fx.quote_currency_code("VOD.L")
    assert code == "GBp"
    assert fx.fx_rate(code, "EUR", date(2026, 10, 20)) == pytest.approx(0.0115)
