"""v208 V208-5: benchmark bar rows -- day_pct only, proxies change-% only, no lookahead."""
import math
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import benchmarks

NOW = datetime(2026, 11, 4, 22, 0, tzinfo=timezone.utc)
OCT30, NOV2, NOV3, NOV4 = date(2026, 10, 30), date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)
SESSIONS = [NOV2, NOV3]


def _frame(rows):
    """rows: [(date, close, adj_close)] -> a yfinance-shaped daily frame."""
    index = pd.DatetimeIndex([pd.Timestamp(d) for d, _, _ in rows])
    return pd.DataFrame({"Close": [c for _, c, _ in rows], "Adj Close": [a for _, _, a in rows]},
                        index=index)


SPY = _frame([(OCT30, 100.0, 98.0), (NOV2, 101.0, 99.96), (NOV3, 102.0, 100.5)])


def _rows(symbol, frame, source=None, sessions=SESSIONS, final_through=NOV3):
    return benchmarks.history_rows(symbol, frame, source_symbol=source or symbol,
                                   sessions=sessions, final_through=final_through, now=NOW)


def test_the_symbol_set_and_total_return_pair():
    assert benchmarks.BENCHMARK_SYMBOLS == ("SPY", "QQQ", "^IXIC", "^DJI")
    assert benchmarks.TOTAL_RETURN == frozenset({"SPY", "QQQ"})


def test_total_return_symbols_take_day_pct_from_adj_close():
    rows = _rows("SPY", SPY)
    assert [r["session"] for r in rows] == [NOV2, NOV3]
    first = rows[0]
    assert set(first) == {"symbol", "session", "close", "adj_close", "day_pct",
                          "source_symbol", "final", "as_of"}
    assert first["day_pct"] == pytest.approx(99.96 / 98.0 - 1)
    assert (first["close"], first["adj_close"]) == (101.0, 99.96)
    assert (first["source_symbol"], first["final"], first["as_of"]) == ("SPY", True, NOW)


def test_price_indexes_take_day_pct_from_close():
    rows = _rows("^DJI", SPY)
    assert rows[0]["day_pct"] == pytest.approx(0.01)


def test_a_proxy_row_stores_only_the_proxys_own_day_pct():
    dia = _frame([(OCT30, 400.0, 390.0), (NOV2, 404.0, 393.0), (NOV3, 402.0, 391.0)])
    rows = _rows("^DJI", dia, source="DIA")
    assert rows[0]["day_pct"] == pytest.approx(0.01)
    assert rows[1]["day_pct"] == pytest.approx(402.0 / 404.0 - 1)
    assert all(r["close"] is None and r["adj_close"] is None for r in rows)
    assert all(r["source_symbol"] == "DIA" and r["symbol"] == "^DJI" for r in rows)


def test_a_row_after_final_through_is_never_written():
    with_today = _frame([(OCT30, 100.0, 98.0), (NOV2, 101.0, 99.96), (NOV3, 102.0, 100.5),
                         (NOV4, 103.0, 101.0)])
    rows = _rows("SPY", with_today, sessions=[NOV2, NOV3, NOV4], final_through=NOV3)
    assert [r["session"] for r in rows] == [NOV2, NOV3]
    assert rows == _rows("SPY", with_today.loc[:str(NOV3)])


def test_a_missing_previous_session_leaves_day_pct_none_not_a_two_day_return():
    gap = _frame([(OCT30, 100.0, 98.0), (NOV2, math.nan, math.nan), (NOV3, 102.0, 100.5)])
    rows = _rows("SPY", gap)
    assert [r["session"] for r in rows] == [NOV3]
    assert rows[0]["day_pct"] is None


def test_a_total_return_symbol_without_adj_close_is_blank():
    assert _rows("SPY", SPY.drop(columns=["Adj Close"])) == []


def test_proxy_map_parses_on_the_last_equals(monkeypatch):
    monkeypatch.setattr(config, "BENCHMARK_PROXY_SYMBOLS", " ^ixic=oneq , ^DJI=DIA,bad,=X", raising=False)
    assert benchmarks.benchmark_proxy_map() == {"^IXIC": "ONEQ", "^DJI": "DIA"}


def test_fallback_uses_the_proxy_only_when_yahoo_is_blank(monkeypatch):
    monkeypatch.setattr(config, "BENCHMARK_PROXY_SYMBOLS", "^DJI=DIA", raising=False)
    calls = []

    def fetch(symbols, start):
        calls.append(list(symbols))
        return {"DIA": SPY} if list(symbols) == ["DIA"] else {}

    rows = benchmarks.history_with_fallback("^DJI", OCT30, sessions=SESSIONS, final_through=NOV3,
                                            now=NOW, fetch=fetch)
    assert calls == [["^DJI"], ["DIA"]]
    assert {r["source_symbol"] for r in rows} == {"DIA"}

    calls.clear()
    rows = benchmarks.history_with_fallback(
        "SPY", OCT30, sessions=SESSIONS, final_through=NOV3, now=NOW,
        fetch=lambda symbols, start: calls.append(list(symbols)) or {"SPY": SPY})
    assert calls == [["SPY"]]
    assert {r["source_symbol"] for r in rows} == {"SPY"}


def test_fallback_without_a_proxy_is_empty(monkeypatch):
    monkeypatch.setattr(config, "BENCHMARK_PROXY_SYMBOLS", "", raising=False)
    assert benchmarks.history_with_fallback("^IXIC", OCT30, sessions=SESSIONS, final_through=NOV3,
                                            now=NOW, fetch=lambda symbols, start: {}) == []


@pytest.mark.parametrize("multi", [True, False])
def test_fetch_history_downloads_raw_and_adjusted(monkeypatch, multi):
    seen = {}

    def download(tickers, **kwargs):
        seen.update(kwargs, tickers=tickers)
        if not multi:
            return SPY
        blank = pd.DataFrame({"Close": [math.nan], "Adj Close": [math.nan]},
                             index=pd.DatetimeIndex([pd.Timestamp(NOV2)]))
        return pd.concat({"SPY": SPY, "^DJI": blank}, axis=1)

    monkeypatch.setattr(benchmarks.yf_safe, "download", download)
    symbols = ["SPY", "^DJI"] if multi else ["SPY"]
    got = benchmarks.fetch_history(symbols, OCT30)
    assert seen["auto_adjust"] is False and seen["interval"] == "1d"
    assert seen["start"] == "2026-10-30" and seen["tickers"] == " ".join(symbols)
    assert list(got) == ["SPY"]
    assert list(got["SPY"]["Adj Close"]) == [98.0, 99.96, 100.5]


PREV = {"symbol": "SPY", "session": NOV3, "close": 102.0, "adj_close": 100.5, "day_pct": 0.01,
        "source_symbol": "SPY", "final": True, "as_of": NOW}


def test_intraday_row_is_not_final_and_uses_the_raw_previous_close():
    row = benchmarks.intraday_row("SPY", PREV, 103.02, NOV4, NOW)
    assert row["day_pct"] == pytest.approx(0.01)
    assert (row["final"], row["close"], row["adj_close"], row["source_symbol"]) == (False, 103.02, None, "SPY")
    assert row["session"] == NOV4


@pytest.mark.parametrize("prev, price", [
    (None, 103.0),
    (PREV, None),
    (PREV, 0.0),
    ({**PREV, "final": False}, 103.0),
    ({**PREV, "close": None, "source_symbol": "DIA"}, 103.0),
    ({**PREV, "session": NOV2}, 103.0),
])
def test_intraday_row_is_skipped_rather_than_computed_from_nothing(prev, price):
    assert benchmarks.intraday_row("SPY", prev, price, NOV4, NOW) is None


def test_latest_prices_never_take_a_stale_price(monkeypatch):
    seen = {}

    def batch(tickers, *, allow_stale=True):
        seen.update(tickers=tickers, allow_stale=allow_stale)
        return {"SPY": 680.5, "^DJI": 0.0, "QQQ": None}

    monkeypatch.setattr(benchmarks.data, "get_current_price_batch", batch)
    assert benchmarks.latest_benchmark_prices(["SPY", "QQQ", "^DJI"]) == {"SPY": 680.5}
    assert seen == {"tickers": ["SPY", "QQQ", "^DJI"], "allow_stale": False}
