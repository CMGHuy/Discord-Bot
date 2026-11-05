"""v201: quote-currency codes persisted by the refresher; requests never fetch FX."""
import contextlib
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import fx, fx_convert, fx_daily
from swingbot.core.marketdata.shared.kinds import Asker
from tests.marketdata.test_fx import FakeRates, stored

T0 = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)
FRAME = pd.DataFrame({"Close": [0.9]}, index=pd.to_datetime(["2026-10-27"]))


class FakeCodes:
    def __init__(self):
        self.rows = {}

    def get_many(self, symbols, *, conn=None):
        return {s: self.rows[s] for s in symbols if s in self.rows}

    def put(self, symbol, code, outcome, *, checked_at, retry_after=None, conn=None):
        self.rows[symbol] = {"symbol": symbol, "code": code, "outcome": outcome,
                             "checked_at": checked_at, "retry_after": retry_after}

    def due(self, symbols, now, *, conn=None):
        return [s for s in symbols if s not in self.rows or (
            self.rows[s]["outcome"] == "unknown" and self.rows[s]["retry_after"] <= now)]


def _boom(*_a, **_k):
    raise AssertionError("network call on a never-fetch path")


@pytest.fixture
def table(monkeypatch):
    """An empty fx_daily_rates; a test adds rows before its first fx_rate call."""
    rates = FakeRates()
    monkeypatch.setattr(fx_daily, "fx_daily_rate_repo", lambda: rates)
    fx_daily.reset_memo()
    yield rates
    fx_daily.reset_memo()


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, table):
    monkeypatch.setattr(fx, "_frames", {})
    monkeypatch.setattr(fx, "_quote_codes", {})
    monkeypatch.setattr(fx, "_unknown_until", {})
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")


@pytest.fixture
def codes(monkeypatch):
    repo = FakeCodes()
    monkeypatch.setattr(fx, "quote_currency_repo", lambda: repo)
    return repo


@pytest.fixture
def provider(monkeypatch):
    calls = []
    answers = {"AAPL": ("USD", True), "ZZZ": (None, True), "DOWN": (None, False)}

    def fake(key):
        calls.append(key)
        if key == "BOOM":
            raise RuntimeError("provider down")
        return answers[key]
    monkeypatch.setattr(fx.data, "_provider_currency_code", fake)
    return calls


@pytest.fixture
def no_network(monkeypatch):
    monkeypatch.setattr(fx.data, "_provider_currency_code", _boom)
    monkeypatch.setattr(fx.data_refresh, "refresh_symbol", _boom)
    monkeypatch.setattr(fx.data_store, "load_normalized", lambda pair, kind: FRAME)


def test_never_fetch_read_is_memo_then_store_then_none(codes, no_network):
    codes.put("AAPL", "USD", "known", checked_at=T0)
    codes.put("ZZZ", None, "unknown", checked_at=T0, retry_after=T0)
    assert fx.quote_currency_code("aapl", fetch=False) == "USD"
    assert fx.quote_currency_code("ZZZ", fetch=False) is None
    assert fx.quote_currency_code("NEW", fetch=False) is None
    codes.rows.clear()
    assert fx.quote_currency_code("AAPL", fetch=False) == "USD"      # memoised


def test_store_error_reads_as_none(monkeypatch, no_network):
    def down():
        raise RuntimeError("db down")
    monkeypatch.setattr(fx, "quote_currency_repo", down)
    assert fx.quote_currency_code("AAPL", fetch=False) is None


def test_refresh_persists_known_and_unknown_and_skips_unanswered(codes, provider):
    assert fx.refresh_quote_codes(["aapl", "ZZZ", "DOWN", "BOOM"], now=T0) == {"AAPL": "USD", "ZZZ": None}
    assert codes.rows["AAPL"]["outcome"] == "known"
    assert codes.rows["ZZZ"]["retry_after"] == T0 + timedelta(seconds=21600)
    assert "DOWN" not in codes.rows and "BOOM" not in codes.rows


def test_unknown_code_is_persisted_and_not_retried_before_backoff(codes, provider):
    fx.refresh_quote_codes(["ZZZ"], now=T0)
    fx.refresh_quote_codes(["ZZZ"], now=T0 + timedelta(hours=5))
    assert provider == ["ZZZ"]
    fx.refresh_quote_codes(["ZZZ"], now=T0 + timedelta(hours=6))
    assert provider == ["ZZZ", "ZZZ"]


def test_refresh_runs_at_the_refresher_tier(codes, provider, monkeypatch):
    scopes = []

    @contextlib.contextmanager
    def scope(asker):
        scopes.append(asker)
        yield
    monkeypatch.setattr(fx.router, "asker_scope", scope)
    fx.refresh_quote_codes(["AAPL"], now=T0)
    assert scopes == [Asker.ADMIN_REFRESH]


def test_rate_without_refresh_reads_the_table_only(no_network, table, monkeypatch):
    monkeypatch.setattr(fx.data_store, "load_normalized", _boom)        # never a file
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 28), refresh=False) is None
    table.rows.append(stored("USD", "EUR", date(2026, 10, 28), 0.9, date(2026, 10, 27)))
    fx_daily.reset_memo()
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 28), refresh=False) == pytest.approx(0.9)


def test_refresh_pair_frames_skips_the_account_currency(monkeypatch):
    refreshed = []
    monkeypatch.setattr(fx.data_refresh, "refresh_symbol", lambda pair, kind: refreshed.append(pair))
    monkeypatch.setattr(fx.data_store, "load_normalized",
                        lambda pair, kind: None if pair == "ILSEUR=X" else FRAME)
    assert fx.refresh_pair_frames(["USD", "EUR", "GBp", "USD", None, "ILA"]) == ["GBPEUR=X", "USDEUR=X"]
    assert refreshed == ["GBPEUR=X", "ILSEUR=X", "USDEUR=X"]


def _row(ticker, amount):
    return {"ticker": ticker, "realized_pnl_amount": amount, "closed_at": "2026-10-28"}


def test_convert_without_fetch_flags_unknown_never_zero(codes, no_network, table):
    table.rows.append(stored("USD", "EUR", date(2026, 10, 28), 0.9, date(2026, 10, 27)))
    codes.put("AAPL", "USD", "known", checked_at=T0)
    rows = fx_convert.to_account_currency([_row("AAPL", 10.0), _row("NEW", 5.0)], fetch=False)
    assert (rows[0]["realized_pnl_amount"], rows[0]["fx_missing"]) == (9.0, False)
    assert (rows[1]["realized_pnl_amount"], rows[1]["fx_missing"]) == (None, True)
    assert fx_convert.missing_count(rows) == 1
    assert fx_convert.convert_amount(10.0, "AAPL", date(2026, 10, 28), fetch=False) == (9.0, False)


@pytest.mark.parametrize("admin,fetch", [("on", False), ("off", True)])
def test_money_wrapper_passes_fetch_from_the_kill_switch(monkeypatch, admin, fetch):
    from swingbot.admin.api_v1 import money
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(config, "ADMIN_REFRESHER", admin)
    seen = []
    monkeypatch.setattr(fx_convert, "to_account_currency",
                        lambda rows, *, account=None, fetch=True: seen.append(fetch) or rows)
    money.to_account_currency([])
    assert seen == [fetch]


def test_risk_weights_never_fetch_with_the_refresher_on(codes, no_network, monkeypatch, table):
    table.rows.append(stored("USD", "EUR", date(2026, 10, 28), 0.9, date(2026, 10, 27)))
    from swingbot.admin.api_v1 import risk_read_model
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    codes.put("AAPL", "USD", "known", checked_at=T0)
    trade = {"ticker": "AAPL", "direction": "bullish", "entry": 100.0, "shares": 2}
    weights, error = risk_read_model.signed_weights([trade], on=date(2026, 10, 28))
    assert error is None and weights == {"AAPL": pytest.approx(1.0)}
