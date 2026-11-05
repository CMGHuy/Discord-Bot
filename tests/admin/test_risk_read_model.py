from datetime import date, datetime, timezone

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


def closed_row(trade_id, closed_at, value, opened_at="2026-01-01"):
    return {"id": trade_id, "closed_at": closed_at, "value": value,
            "opened_at": opened_at}


def test_close_order_ignores_input_and_opening_order():
    rows = [closed_row("late", "2026-03-03T10:00:00Z", 1, "2026-01-01"),
            closed_row("first", "2026-03-01T11:00:00+01:00", -1, "2026-02-20"),
            closed_row("middle", "2026-03-02T10:00:00", -1, "2026-02-10")]
    ordered, counts = model.chronological_records(rows, outcome=lambda row: row["value"])
    reversed_order, _ = model.chronological_records(list(reversed(rows)), outcome=lambda row: row["value"])
    assert [row["id"] for row in ordered] == ["first", "middle", "late"]
    assert ordered == reversed_order
    assert counts == {"excluded_count": 0, "invalid_date_count": 0, "invalid_outcome_count": 0}
    from swingbot.core.analytics.risk_metrics import max_drawdown_r
    assert max_drawdown_r([row["value"] for row in ordered]) == 2


def test_equal_instants_use_stable_trade_id():
    rows = [closed_row("b", "2026-03-01T11:00:00+01:00", -1),
            closed_row("a", "2026-03-01T10:00:00Z", 1)]
    ordered, _ = model.chronological_records(rows, outcome=lambda row: row["value"])
    assert [row["id"] for row in ordered] == ["a", "b"]


def test_exclusion_reasons_are_nonoverlapping_and_date_first():
    seen = []
    rows = [closed_row("both_bad", "not-a-date", float("nan")),
            closed_row("missing_date", None, 1),
            closed_row("bad_value", "2026-03-01", float("inf")),
            closed_row("missing_value", "2026-03-02", None),
            closed_row("good", "2026-03-03", -1)]
    def outcome(row):
        seen.append(row["id"])
        return row["value"]
    ordered, counts = model.chronological_records(rows, outcome=outcome)
    assert [row["id"] for row in ordered] == ["good"]
    assert counts == {"excluded_count": 4, "invalid_date_count": 2, "invalid_outcome_count": 2}
    assert seen == ["bad_value", "missing_value", "good"]


def test_outcome_exception_is_counted_without_blanking_other_records():
    rows = [closed_row("bad", "2026-03-01", None), closed_row("good", "2026-03-02", 1)]
    ordered, counts = model.chronological_records(rows, outcome=lambda row: 1 / row["value"])
    assert [row["id"] for row in ordered] == ["good"]
    assert counts["invalid_outcome_count"] == 1


def test_money_selection_filters_dates_before_outcome_or_fx_work():
    rows = [closed_row("unknown_amount", "2026-03-01", None), closed_row("bad_date", None, 1)]
    ordered, counts = model.chronological_records(rows)
    assert [row["id"] for row in ordered] == ["unknown_amount"]
    assert counts == {"excluded_count": 1, "invalid_date_count": 1, "invalid_outcome_count": 0}
    assert model.chronological_records([]) == ([], {"excluded_count": 0, "invalid_date_count": 0,
                                                  "invalid_outcome_count": 0})


def test_datetime_values_keep_original_records_unchanged():
    first = closed_row(2, datetime(2026, 3, 1), 1)
    last = closed_row(10, datetime(2026, 3, 1, tzinfo=timezone.utc), 1)
    rows = [first, last]
    snapshots = [dict(row) for row in rows]
    ordered, counts = model.chronological_records(rows)
    assert ordered[0] is last
    assert ordered[1] is first
    assert rows == snapshots
    assert counts["excluded_count"] == 0


@pytest.mark.parametrize("value", [True, False, float("nan"), float("-inf"), "bad"])
def test_invalid_outcome_values_are_excluded(value):
    ordered, counts = model.chronological_records(
        [closed_row("bad", "2026-03-01", value)], outcome=lambda row: row["value"])
    assert ordered == []
    assert counts == {"excluded_count": 1, "invalid_date_count": 0, "invalid_outcome_count": 1}


@pytest.mark.parametrize("row", [None, [], {}, {"closed_at": 42}, {"closed_at": "9999-12-31T23:00:00-02:00"}])
def test_invalid_date_records_are_excluded(row):
    ordered, counts = model.chronological_records([row])
    assert ordered == []
    assert counts == {"excluded_count": 1, "invalid_date_count": 1, "invalid_outcome_count": 0}

