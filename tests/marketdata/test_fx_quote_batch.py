"""v205 L1-b: quote codes for one conversion in one query; unknowns memoised for 5 minutes."""
from datetime import date, datetime, timezone

import pytest

from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata import fx, fx_convert

T0 = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)


class CountingCodes:
    def __init__(self):
        self.rows = {}
        self.calls: list[list[str]] = []
        self.fail = False

    def get_many(self, symbols, *, conn=None):
        wanted = [s.upper() for s in symbols]
        self.calls.append(wanted)
        if self.fail:
            raise RuntimeError("db down")
        return {s: self.rows[s] for s in wanted if s in self.rows}

    def known(self, symbol, code):
        self.rows[symbol] = {"symbol": symbol, "code": code, "outcome": "known",
                             "checked_at": T0, "retry_after": None}

    def unknown(self, symbol):
        self.rows[symbol] = {"symbol": symbol, "code": None, "outcome": "unknown",
                             "checked_at": T0, "retry_after": T0}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(fx, "_frames", {})
    monkeypatch.setattr(fx, "_quote_codes", {})
    monkeypatch.setattr(fx, "_unknown_until", {})
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")


@pytest.fixture
def codes(monkeypatch):
    repo = CountingCodes()
    monkeypatch.setattr(fx, "quote_currency_repo", lambda: repo)
    return repo


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(fx, "_clock", c)
    return c


@pytest.fixture
def flat_rate(monkeypatch):
    """Every pair at 0.5, so a converted amount shows whether its quote resolved."""
    monkeypatch.setattr(fx, "fx_rate", lambda from_code, to_code, on, *, refresh=True: 0.5)


def _row(ticker, amount=10.0):
    return {"ticker": ticker, "realized_pnl_amount": amount, "closed_at": "2026-10-28"}


def test_one_conversion_call_asks_the_store_once(codes, clock, flat_rate):
    codes.known("AAPL", "USD")
    codes.known("SAP.DE", "EUR")
    rows = fx_convert.to_account_currency(
        [_row("aapl"), _row("SAP.DE"), _row("AAPL"), _row("NEW"), _row(None)], fetch=False)
    assert codes.calls == [["AAPL", "SAP.DE", "NEW"]]
    assert [(r["realized_pnl_amount"], r["fx_missing"]) for r in rows] == [
        (5.0, False), (10.0, False), (5.0, False), (None, True), (None, True)]


def test_known_codes_are_remembered_for_the_process(codes, clock):
    codes.known("AAPL", "USD")
    assert fx.stored_codes(["AAPL"]) == {"AAPL": "USD"}
    codes.rows.clear()
    clock.now += 10 * fx.UNKNOWN_MEMO_S
    assert fx.stored_codes(["AAPL"]) == {"AAPL": "USD"}
    assert codes.calls == [["AAPL"]]
    assert fx._quote_codes["AAPL"] == "USD"


def test_an_unknown_code_is_remembered_for_five_minutes_then_asked_again(codes, clock):
    codes.unknown("ZZZ")
    assert fx.stored_codes(["ZZZ", "NEW"]) == {"ZZZ": None, "NEW": None}
    codes.known("ZZZ", "USD")                       # the refresher resolves it meanwhile
    clock.now += fx.UNKNOWN_MEMO_S - 1
    assert fx.stored_codes(["ZZZ", "NEW"]) == {"ZZZ": None, "NEW": None}
    assert codes.calls == [["ZZZ", "NEW"]]          # inside the memo: no query
    clock.now += 2
    assert fx.stored_codes(["ZZZ", "NEW"]) == {"ZZZ": "USD", "NEW": None}
    assert codes.calls == [["ZZZ", "NEW"], ["ZZZ", "NEW"]]


def test_the_single_ticker_path_shares_the_negative_memo(codes, clock):
    assert fx.quote_currency_code("NEW", fetch=False) is None
    assert fx.quote_currency_code("new", fetch=False) is None
    assert codes.calls == [["NEW"]]


def test_a_store_error_is_all_none_swallowed_and_not_memoised(codes, clock):
    before = sw.snapshot().get("marketdata.fx.stored_code", {}).get("count", 0)
    codes.fail = True
    assert fx.stored_codes(["AAPL", "ZZZ"]) == {"AAPL": None, "ZZZ": None}
    assert sw.snapshot()["marketdata.fx.stored_code"]["count"] == before + 1
    assert fx._unknown_until == {} and fx._quote_codes == {}
    codes.fail = False
    codes.known("AAPL", "USD")
    assert fx.stored_codes(["AAPL"]) == {"AAPL": "USD"}          # asked again at once


def test_no_keys_means_no_query(codes, clock):
    assert fx.stored_codes([]) == {}
    assert fx.stored_codes(["", None, "  "]) == {}
    assert codes.calls == []


def test_fetch_true_keeps_the_one_argument_seam(monkeypatch, codes, flat_rate):
    seen = []
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: seen.append(ticker) or "USD")
    monkeypatch.setattr(fx, "stored_codes", lambda keys: pytest.fail("fetch=True must not batch"))
    rows = fx_convert.to_account_currency([_row("AAPL"), _row("MSFT")])
    assert seen == ["AAPL", "MSFT"]
    assert [r["realized_pnl_amount"] for r in rows] == [5.0, 5.0]
    assert codes.calls == []


def test_convert_amount_without_fetch_still_resolves_its_one_ticker(codes, clock, flat_rate):
    codes.known("AAPL", "USD")
    assert fx_convert.convert_amount(10.0, "AAPL", date(2026, 10, 28), fetch=False) == (5.0, False)
    assert codes.calls == [["AAPL"]]
