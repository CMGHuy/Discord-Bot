"""SR54 -- the figures stats.html derived in browser JS, moved server-side.

Every fixture below has a hand-computed answer in its assertion, because the
point of moving these off the client is that there is one definition per stat
and it is checkable. A test that asserts "whatever the code returns" would
defeat the exercise.

The empty-window case is asserted for every metric: `None`, never `0.0`. A
date range that selects no trades and a genuinely flat result must not look
the same on a KPI card -- the same reason `win_rate` already returns None.
"""
import pytest

from swingbot.core.analytics.metrics import (
    annualisation_factor,
    annualised_return_pct,
    avg_loss_pct,
    avg_win_pct,
    calendar_returns,
    calmar,
    cumulative_pnl_by_strategy,
    histogram,
    holding_period_split,
    in_date_range,
    pct_in_market,
    rolling_return_pct,
    span_years,
    total_return_pct,
    trades_per_month,
    volatility_ann_pct,
)


def _t(opened, closed, entry, exit_price, *, status="win", direction="bullish",
       stop=None, strategy="RSI", pnl_amount=None):
    """One closed trade. Dates are plain ISO days -- the production records
    carry full timestamps, and every function here slices to [:10] or parses
    with fromisoformat, so both shapes must work."""
    return {
        "status": status,
        "direction": direction,
        "entry": entry,
        "exit_price": exit_price,
        "stop_loss": stop if stop is not None else entry * 0.95,
        "opened_at": opened,
        "closed_at": closed,
        "strategy": strategy,
        "realized_pnl_amount": pnl_amount,
    }


def _year_of_trades():
    """Four trades spanning exactly one calendar year, +10%, -5%, +20%, -10%.

    Compounded: 1.10 * 0.95 * 1.20 * 0.90 = 1.1286 -> +12.86% total.
    """
    return [
        _t("2024-01-01", "2024-01-11", 100.0, 110.0, strategy="RSI"),
        _t("2024-04-01", "2024-04-11", 100.0, 95.0, status="loss", strategy="RSI"),
        _t("2024-07-01", "2024-07-21", 100.0, 120.0, strategy="MACD"),
        _t("2024-12-22", "2025-01-01", 100.0, 90.0, status="loss", strategy="MACD"),
    ]


# --------------------------------------------------------------- date range

def test_in_date_range_scopes_on_closed_at_inclusive():
    trades = _year_of_trades()
    assert len(in_date_range(trades, start="2024-04-01", end="2024-07-21")) == 2
    # Both bounds inclusive: a trade closing exactly on the boundary is in.
    assert len(in_date_range(trades, start="2024-01-11", end="2024-01-11")) == 1
    assert in_date_range(trades, start=None, end=None) == trades


def test_in_date_range_ignores_open_trades_and_undated_records():
    trades = _year_of_trades() + [{"status": "open", "entry": 100.0}]
    assert len(in_date_range(trades, start="2024-01-01", end="2025-12-31")) == 4


# ------------------------------------------------------------ avg win/loss

def test_avg_win_and_avg_loss_are_signed_the_way_a_card_reads_them():
    trades = _year_of_trades()
    assert avg_win_pct(trades) == 15.0      # mean(+10, +20)
    assert avg_loss_pct(trades) == -7.5     # mean(-5, -10), stays negative


def test_avg_win_and_loss_are_none_not_zero_on_an_empty_window():
    assert avg_win_pct([]) is None
    assert avg_loss_pct([]) is None
    # A window with only wins has no average loss to report.
    assert avg_loss_pct([_t("2024-01-01", "2024-01-11", 100.0, 110.0)]) is None


# ------------------------------------------------------------------- span

def test_span_years_measures_first_open_to_last_close():
    assert round(span_years(_year_of_trades()), 4) == round(366 / 365.25, 4)


def test_span_years_floors_at_one_day_so_annualising_cannot_divide_by_zero():
    same_day = [_t("2024-01-01", "2024-01-01", 100.0, 110.0)]
    assert span_years(same_day) == pytest.approx(1 / 365, rel=1e-6)


def test_span_years_none_on_empty():
    assert span_years([]) is None


# ------------------------------------------------------- returns / calmar

def test_total_return_pct_compounds_rather_than_summing():
    # Summing would give +15.0; compounding gives +12.86. They differ, and
    # the compounded one is the honest account-growth figure.
    assert round(total_return_pct(_year_of_trades()), 2) == 12.86


def test_annualised_return_is_close_to_total_return_over_about_one_year():
    trades = _year_of_trades()
    ann = annualised_return_pct(trades)
    assert 12.0 < ann < 13.0     # ~366 days, so barely below the raw total


def test_annualised_return_scales_a_short_window_up():
    # +10% earned in ~10 days annualises to a very large number; the point of
    # the assertion is the direction and that it does not silently clamp.
    quick = [_t("2024-01-01", "2024-01-11", 100.0, 110.0)]
    assert annualised_return_pct(quick) > 1000.0


def test_returns_none_on_empty_window():
    assert total_return_pct([]) is None
    assert annualised_return_pct([]) is None
    assert calmar([]) is None


def test_calmar_is_annualised_return_over_max_drawdown():
    trades = _year_of_trades()
    # Equity walks 100 -> 110 -> 104.5 -> 125.4 -> 112.86; peak 125.4,
    # trough after it 112.86 -> max drawdown 9.9968%.
    c = calmar(trades)
    assert c == pytest.approx(annualised_return_pct(trades) / 9.9968, rel=1e-3)


def test_calmar_none_when_the_curve_never_drew_down():
    winners = [
        _t("2024-01-01", "2024-01-11", 100.0, 110.0),
        _t("2024-02-01", "2024-02-11", 100.0, 110.0),
    ]
    assert calmar(winners) is None


# ------------------------------------------------ annualisation / vol

def test_annualisation_factor_uses_average_holding_period():
    # Holding periods 10, 10, 20, 10 -> avg 12.5 days -> sqrt(252/12.5).
    assert annualisation_factor(_year_of_trades()) == pytest.approx((252 / 12.5) ** 0.5)


def test_annualisation_factor_floors_the_holding_period_at_half_a_day():
    # An intraday round trip must not blow the factor up without bound.
    intraday = [_t("2024-01-01T09:30:00", "2024-01-01T10:30:00", 100.0, 101.0)]
    assert annualisation_factor(intraday) == pytest.approx((252 / 0.5) ** 0.5)


def test_annualisation_factor_is_one_when_no_holding_period_is_knowable():
    assert annualisation_factor([]) == 1.0


def test_volatility_is_the_annualised_standard_deviation_of_returns():
    import numpy as np
    trades = _year_of_trades()
    expected = float(np.std([10.0, -5.0, 20.0, -10.0], ddof=1)) * annualisation_factor(trades)
    assert volatility_ann_pct(trades) == pytest.approx(expected)


def test_volatility_none_on_empty_and_on_a_single_trade():
    assert volatility_ann_pct([]) is None
    assert volatility_ann_pct([_t("2024-01-01", "2024-01-11", 100.0, 110.0)]) is None


# ---------------------------------------------- cadence / time in market

def test_trades_per_month_over_a_one_year_window():
    # abs, not rel: this module rounds every returned figure to 4 dp, so the
    # tolerance has to be the rounding granularity rather than a tighter
    # relative one that only passes for larger numbers.
    assert trades_per_month(_year_of_trades()) == pytest.approx(4 / (366 / 365.25 * 12), abs=5e-5)


def test_pct_in_market_sums_holding_days_over_the_span():
    # 10 + 10 + 20 + 10 = 50 days held across a 366-day span.
    assert pct_in_market(_year_of_trades()) == pytest.approx(50 / 366 * 100, rel=1e-6)


def test_pct_in_market_caps_at_100_when_trades_overlap():
    overlapping = [
        _t("2024-01-01", "2024-06-01", 100.0, 110.0),
        _t("2024-01-01", "2024-06-01", 100.0, 110.0),
        _t("2024-01-01", "2024-06-01", 100.0, 110.0),
    ]
    assert pct_in_market(overlapping) == 100.0


def test_cadence_none_on_empty():
    assert trades_per_month([]) is None
    assert pct_in_market([]) is None


# ------------------------------------------------------------ histograms

def test_histogram_buckets_values_and_keeps_empty_buckets():
    h = histogram([-1.0, -0.5, 0.5, 0.5, 2.0], bins=4)
    assert sum(b["count"] for b in h) == 5
    # Empty interior buckets must survive, or the chart's x-axis lies.
    assert len(h) == 4
    assert [b["count"] for b in h] == [2, 0, 2, 1]


def test_histogram_empty_input_is_an_empty_list_not_zero_buckets():
    assert histogram([], bins=4) == []


def test_histogram_of_a_single_repeated_value_does_not_divide_by_zero():
    h = histogram([1.0, 1.0, 1.0], bins=4)
    assert sum(b["count"] for b in h) == 3


# ------------------------------------------------------ rolling / splits

def test_rolling_return_pct_is_a_trailing_window():
    trades = _year_of_trades()
    pts = rolling_return_pct(trades, window=2)
    # One point per trade from the window'th onward.
    assert len(pts) == 3
    assert pts[0]["date"] == "2024-04-11"
    # First window is +10% then -5% compounded = +4.5%.
    assert pts[0]["return_pct"] == pytest.approx(4.5, rel=1e-6)


def test_rolling_return_empty_when_fewer_trades_than_the_window():
    assert rolling_return_pct(_year_of_trades(), window=99) == []


def test_holding_period_split_buckets_by_days_held():
    trades = _year_of_trades()
    split = {b["bucket"]: b for b in holding_period_split(trades)}
    assert split["2d+"]["n"] == 4
    assert split["0h-2h"]["n"] == 0
    assert split["2d+"]["win_rate"] == 50.0


def test_holding_period_split_buckets_intraday_holds_by_hour():
    trades = [
        _t("2024-01-01T09:30:00", "2024-01-01T10:30:00", 100.0, 105.0),
        _t("2024-01-01T09:30:00", "2024-01-01T12:30:00", 100.0, 95.0, status="loss"),
        _t("2024-01-01T09:30:00", "2024-01-01T16:30:00", 100.0, 105.0),
        _t("2024-01-01T09:30:00", "2024-01-02T08:30:00", 100.0, 105.0),
        _t("2024-01-01T09:30:00", "2024-01-02T15:30:00", 100.0, 105.0),
    ]
    split = {b["bucket"]: b for b in holding_period_split(trades)}
    assert split["0h-2h"]["n"] == 1
    assert split["2h-4h"]["n"] == 1
    assert split["4h-8h"]["n"] == 1
    assert split["8h-24h"]["n"] == 1
    assert split["1d-2d"]["n"] == 1
    assert split["2d+"]["n"] == 0
def test_holding_period_split_is_empty_on_no_trades():
    assert holding_period_split([]) == []


# ------------------------------------------------- calendar / by strategy

def test_calendar_returns_group_by_month():
    cal = {c["month"]: c for c in calendar_returns(_year_of_trades())}
    assert cal["2024-01"]["return_pct"] == pytest.approx(10.0)
    assert cal["2024-01"]["n"] == 1
    assert cal["2025-01"]["return_pct"] == pytest.approx(-10.0)
    assert "2024-02" not in cal   # months with no trades are omitted, not zeroed


def test_calendar_returns_empty_on_no_trades():
    assert calendar_returns([]) == []


def test_cumulative_pnl_by_strategy_walks_each_strategy_separately():
    out = cumulative_pnl_by_strategy(_year_of_trades())
    assert set(out) == {"RSI", "MACD"}
    # RSI: +10 then -5, walked cumulatively on percent.
    assert [round(p["cum_pct"], 4) for p in out["RSI"]] == [10.0, 4.5]
    assert out["RSI"][0]["date"] == "2024-01-11"


def test_cumulative_pnl_by_strategy_empty_on_no_trades():
    assert cumulative_pnl_by_strategy([]) == {}
