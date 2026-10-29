from datetime import date

import numpy as np
import pandas as pd
import pytest

import swingbot.admin.app  # initialize the API package as existing admin fixtures do
from swingbot.admin.api_v1 import risk_read_model as model
from swingbot.core.marketdata import fx

DAY = date(2026, 10, 28)


def position(ticker="AAA", direction="bullish", entry=100.0, shares=1.0):
    return {"ticker": ticker, "direction": direction, "entry": entry, "shares": shares}


@pytest.fixture
def currency(monkeypatch):
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: "EUR")
    monkeypatch.setattr(fx, "fx_rate", lambda source, target, on: 1.0)


@pytest.mark.parametrize("rows, expected", [
    ([position()], {"AAA": 1.0}),
    ([position(direction="bearish")], {"AAA": -1.0}),
    ([position(shares=3), position("BBB", "bearish")], {"AAA": 0.75, "BBB": -0.25}),
    ([position(), position(direction="bearish")], {"AAA": 0.0}),
    ([position(shares=3), position(direction="bearish")], {"AAA": 0.5}),
    ([], {}),
])
def test_gross_weights_preserve_direction_and_netting(currency, rows, expected):
    weights, reason = model.signed_weights(rows, on=DAY)
    assert reason is None
    assert weights == pytest.approx(expected)


def test_cross_currency_weights_share_one_valuation_date(currency, monkeypatch):
    calls = []
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: "USD" if ticker == "AAA" else "EUR")
    def rate(source, target, on):
        calls.append((source, target, on))
        return 2.0 if source == "USD" else 1.0
    monkeypatch.setattr(fx, "fx_rate", rate)
    weights, reason = model.signed_weights([position(shares=2), position("BBB", "bearish")], on=DAY)
    assert reason is None
    assert weights == pytest.approx({"AAA": 0.8, "BBB": -0.2})
    assert calls == [("USD", "EUR", DAY), ("EUR", "EUR", DAY)]


@pytest.mark.parametrize("field,value,reason", [
    ("direction", None, "invalid_direction"), ("direction", "long", "invalid_direction"),
    ("entry", 0, "invalid_position"), ("entry", float("nan"), "invalid_position"),
    ("shares", -1, "invalid_position"), ("shares", float("inf"), "invalid_position"),
    ("shares", "bad", "invalid_position"), ("ticker", "", "invalid_position"),
    ("entry", True, "invalid_position"), ("shares", False, "invalid_position"),
])
def test_invalid_exposure_never_becomes_a_partial_normalized_book(currency, field, value, reason):
    bad = {**position("BBB"), field: value}
    assert model.signed_weights([position(), bad], on=DAY) == ({}, reason)


@pytest.mark.parametrize("rate,reason", [(None, "missing_fx"), (0, "invalid_fx"),
                                        (-1, "invalid_fx"), (float("nan"), "invalid_fx"),
                                        (float("inf"), "invalid_fx"), (True, "invalid_fx")])
def test_bad_fx_is_not_parity(currency, monkeypatch, rate, reason):
    monkeypatch.setattr(fx, "fx_rate", lambda *args: rate)
    assert model.signed_weights([position()], on=DAY) == ({}, reason)


def test_missing_quote_currency_is_unavailable(currency, monkeypatch):
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: None)
    assert model.signed_weights([position()], on=DAY) == ({}, "missing_quote_currency")


def test_short_quote_returns_have_negative_beta(currency):
    from swingbot.core.analytics import risk_metrics as rm
    closes = 100 * np.cumprod(1 + 0.01 * np.sin(np.arange(100)))
    frame = pd.DataFrame({"Close": closes}, index=pd.date_range("2026-01-01", periods=100))
    weights, _ = model.signed_weights([position(direction="bearish")], on=DAY)
    returns = rm.portfolio_returns(weights, {"AAA": frame})
    benchmark = rm.portfolio_returns({"AAA": 1.0}, {"AAA": frame})
    assert rm.beta_vs(returns, benchmark) == pytest.approx(-1.0)


def test_bar_coverage_requires_zero_net_names_too():
    frame = pd.DataFrame({"Close": [100.0, 101.0]})
    assert model.complete_bars(["AAA", "BBB"], {"AAA": frame}) is False
    assert model.complete_bars(["AAA"], {"AAA": frame}) is True
    assert model.complete_bars(["AAA"], {"AAA": pd.DataFrame({"Close": [100.0, np.nan]})}) is False


def test_minor_units_use_shared_fx_scaling(currency, monkeypatch):
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: "GBp" if ticker == "AAA" else "GBP")
    monkeypatch.setattr(fx, "fx_rate", lambda source, target, on: 0.01 if source == "GBp" else 1.0)
    weights, reason = model.signed_weights(
        [position(entry=100), position("BBB", "bearish", entry=1)], on=DAY, account="GBP")
    assert reason is None
    assert weights == pytest.approx({"AAA": 0.5, "BBB": -0.5})


@pytest.mark.parametrize("lookup,reason", [("quote_currency_code", "missing_quote_currency"),
                                          ("fx_rate", "missing_fx")])
def test_lookup_errors_have_sanitized_reasons(currency, monkeypatch, lookup, reason):
    def fail(*args):
        raise OSError("private provider diagnostic")
    monkeypatch.setattr(fx, lookup, fail)
    assert model.signed_weights([position()], on=DAY) == ({}, reason)


def test_explicit_account_and_normalized_ticker(currency, monkeypatch):
    calls = []
    monkeypatch.setattr(fx, "fx_rate", lambda source, target, on: calls.append((source, target, on)) or 1.0)
    assert model.signed_weights([position(" aaa ")], on=DAY, account="USD") == ({"AAA": 1.0}, None)
    assert calls == [("EUR", "USD", DAY)]


@pytest.mark.parametrize("frame", [None, pd.DataFrame(), pd.DataFrame({"Open": [100]}),
                                   pd.DataFrame({"Close": [0.0]}),
                                   pd.DataFrame({"Close": [float("inf")]}),
                                   pd.DataFrame({"Close": ["bad"]})])
def test_invalid_bars_never_count_as_complete(frame):
    assert model.complete_bars(["AAA"], {"AAA": frame}) is False


def test_empty_population_needs_no_bars():
    assert model.complete_bars([], {}) is True

