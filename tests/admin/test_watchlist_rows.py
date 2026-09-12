import pandas as pd
import pytest

from swingbot.admin.watchlist_rows import build_market_rows, build_signals


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


class _FakePlan:
    """Carries only the fields build_signals reads off a TradePlanV2."""

    def __init__(self, ticker, status, score, horizon, strategy):
        self.ticker = ticker
        self.status = status
        self.quality_score = score
        self.horizon_key = horizon
        self.strategy = strategy


@pytest.fixture
def plans(monkeypatch):
    """Install a canned plan set, in the wire vocabulary (`score`, `horizon`)
    build_signals's own tests use -- translated to the TradePlanV2 field
    names (`quality_score`, `horizon_key`) here, once, rather than in every
    test. Patches PlanStore where watchlist_rows imported it, the same
    origin-module trick test_api_v1_analytics.py's FakeStore uses."""

    def _install(records):
        installed = [_FakePlan(**r) for r in records]

        class FakeStore:
            def all(self):
                return installed

        monkeypatch.setattr("swingbot.admin.watchlist_rows.PlanStore", FakeStore)

    return _install


def test_a_pending_plan_reads_as_a_waiting_setup(plans):
    plans([{"ticker": "AAPL", "status": "PENDING", "score": 78, "horizon": "6w",
            "strategy": "RSI"}])
    sig = build_signals(["AAPL"])["AAPL"]
    assert sig["state"] == "pending"
    assert sig["score"] == 78
    assert sig["horizon"] == "6w"


def test_an_active_plan_reads_as_in_position(plans):
    plans([{"ticker": "AAPL", "status": "ACTIVE", "score": 78, "horizon": "6w",
            "strategy": "RSI"}])
    assert build_signals(["AAPL"])["AAPL"]["state"] == "active"


def test_a_symbol_with_no_plan_reads_as_no_setup_not_as_zero(plans):
    plans([])
    sig = build_signals(["AAPL"])["AAPL"]
    assert sig["state"] == "none"
    assert sig["score"] is None


def test_a_closed_plan_does_not_count_as_a_live_setup(plans):
    plans([{"ticker": "AAPL", "status": "CLOSED", "score": 78, "horizon": "6w",
            "strategy": "RSI"}])
    assert build_signals(["AAPL"])["AAPL"]["state"] == "none"


def test_the_best_scoring_plan_wins_when_a_symbol_has_several(plans):
    plans([
        {"ticker": "AAPL", "status": "PENDING", "score": 61, "horizon": "2w", "strategy": "RSI"},
        {"ticker": "AAPL", "status": "PENDING", "score": 84, "horizon": "3m", "strategy": "Fib"},
    ])
    assert build_signals(["AAPL"])["AAPL"]["score"] == 84


def test_an_active_plan_outranks_a_better_scoring_pending_one(plans):
    plans([
        {"ticker": "AAPL", "status": "PENDING", "score": 90, "horizon": "2w", "strategy": "RSI"},
        {"ticker": "AAPL", "status": "ACTIVE", "score": 60, "horizon": "3m", "strategy": "Fib"},
    ])
    assert build_signals(["AAPL"])["AAPL"]["state"] == "active"


def test_a_plan_for_a_different_ticker_does_not_leak_onto_this_one(plans):
    plans([{"ticker": "MSFT", "status": "ACTIVE", "score": 90, "horizon": "2w",
            "strategy": "RSI"}])
    assert build_signals(["AAPL"])["AAPL"]["state"] == "none"


def test_an_empty_ticker_list_makes_no_plan_store_call(monkeypatch):
    called = []
    monkeypatch.setattr(
        "swingbot.admin.watchlist_rows.PlanStore",
        lambda: called.append("constructed"),
    )
    assert build_signals([]) == {}
    assert called == []
