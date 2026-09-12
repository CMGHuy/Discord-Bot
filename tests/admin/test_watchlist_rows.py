import pandas as pd
import pytest

from swingbot.admin.watchlist_rows import build_market_rows


def _frame(closes: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({"Close": closes}, index=idx)


@pytest.fixture
def bars(monkeypatch):
    """Install a canned batch so no test here touches the network."""
    store: dict[str, pd.DataFrame] = {}

    def fake_batch(tickers, period="2y"):
        return {t: store[t] for t in tickers if t in store}

    monkeypatch.setattr("swingbot.admin.watchlist_rows.get_daily_data_batch", fake_batch)
    monkeypatch.setattr("swingbot.admin.watchlist_rows.is_us_market_active", lambda: False)
    return store


def test_price_is_the_last_close_when_the_market_is_shut(bars):
    bars["AAPL"] = _frame([100.0] * 25 + [171.5])
    assert build_market_rows(["AAPL"])["AAPL"]["price"] == pytest.approx(171.5)


def test_as_of_is_the_bar_date_not_today(bars):
    bars["AAPL"] = _frame([100.0] * 26, start="2026-01-01")
    row = build_market_rows(["AAPL"])["AAPL"]
    assert row["as_of"].startswith("2026-02")  # the 26th business day, not today


def test_one_day_change_is_last_close_over_previous(bars):
    bars["AAPL"] = _frame([100.0] * 25 + [110.0])
    assert build_market_rows(["AAPL"])["AAPL"]["change_1d_pct"] == pytest.approx(10.0)


def test_week_and_month_changes_use_five_and_twenty_one_bars(bars):
    bars["AAPL"] = _frame(list(range(100, 130)))  # 30 rising bars
    row = build_market_rows(["AAPL"])["AAPL"]
    assert row["change_1w_pct"] > 0
    assert row["change_1m_pct"] > row["change_1w_pct"]


def test_a_short_history_yields_null_for_the_windows_it_cannot_fill(bars):
    bars["NEW"] = _frame([100.0, 101.0, 102.0])
    row = build_market_rows(["NEW"])["NEW"]
    assert row["change_1d_pct"] is not None
    assert row["change_1w_pct"] is None
    assert row["change_1m_pct"] is None


def test_a_symbol_with_no_bars_yields_a_row_of_nulls_not_an_omission(bars):
    row = build_market_rows(["GHOST"])["GHOST"]
    assert row["price"] is None
    assert row["as_of"] is None
    assert row["spark"] == []


def test_one_bad_symbol_does_not_lose_the_others(bars):
    bars["AAPL"] = _frame([100.0] * 26)
    rows = build_market_rows(["AAPL", "GHOST"])
    assert rows["AAPL"]["price"] is not None
    assert rows["GHOST"]["price"] is None


def test_the_sparkline_is_the_last_thirty_closes(bars):
    bars["AAPL"] = _frame([float(i) for i in range(60)])
    spark = build_market_rows(["AAPL"])["AAPL"]["spark"]
    assert len(spark) == 30
    assert spark[-1] == pytest.approx(59.0)


def test_an_intraday_quote_overrides_the_close_while_the_market_is_open(bars, monkeypatch):
    bars["AAPL"] = _frame([100.0] * 26)
    monkeypatch.setattr("swingbot.admin.watchlist_rows.is_us_market_active", lambda: True)
    monkeypatch.setattr(
        "swingbot.admin.watchlist_rows.get_current_price_batch", lambda t: {"AAPL": 173.25}
    )
    assert build_market_rows(["AAPL"])["AAPL"]["price"] == pytest.approx(173.25)


def test_an_empty_watchlist_makes_no_batch_call(bars, monkeypatch):
    called = []
    monkeypatch.setattr(
        "swingbot.admin.watchlist_rows.get_daily_data_batch",
        lambda tickers, period="2y": called.append(tickers) or {},
    )
    assert build_market_rows([]) == {}
    assert called == []
