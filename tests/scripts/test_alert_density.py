"""Entry-day density and its buckets. Pure arithmetic over trade lists.

Import style follows this repo's other scripts/ tests
(tests/scripts/test_run_backtest_range.py): `scripts/` is not a package and its
modules import each other bare, so the module under test is imported off
sys.path rather than as `scripts.backtest.measure_alert_density`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

from measure_alert_density import (  # noqa: E402
    DENSITY_BUCKETS, bucket_trades, density_by_day, density_profile,
    per_day_rows,
)


def _t(date, r=0.0, ticker="AAA"):
    return {"opened_at": f"{date}T14:30:00", "ticker": ticker, "r_multiple": r}


def test_density_counts_trades_per_calendar_date():
    trades = [_t("2021-03-01"), _t("2021-03-01"), _t("2021-03-02")]
    assert density_by_day(trades) == {"2021-03-01": 2, "2021-03-02": 1}


def test_density_includes_the_trade_itself():
    assert density_by_day([_t("2021-03-01")]) == {"2021-03-01": 1}


def test_intraday_times_do_not_split_a_day():
    trades = [{"opened_at": "2021-03-01T09:31:00"}, {"opened_at": "2021-03-01T15:59:00"}]
    assert density_by_day(trades) == {"2021-03-01": 2}


def test_trades_without_opened_at_are_skipped_not_crashed():
    assert density_by_day([_t("2021-03-01"), {"ticker": "BBB"}]) == {"2021-03-01": 1}


def test_bucket_assignment_at_every_boundary():
    counts = {"quiet": 1, "normal": 3, "busy": 4, "flood": 8}
    for name, n in counts.items():
        trades = [_t("2021-03-01") for _ in range(n)]
        rows = {r["bucket"]: r for r in bucket_trades(trades)}
        assert rows[name]["n"] == n, f"{n} trades/day should land in {name}"


def test_every_bucket_reported_even_when_empty():
    rows = bucket_trades([_t("2021-03-01")])
    assert [r["bucket"] for r in rows] == [b[0] for b in DENSITY_BUCKETS]
    flood = [r for r in rows if r["bucket"] == "flood"][0]
    assert flood["n"] == 0
    assert flood["expectancy_r"] is None
    assert flood["win_rate"] is None


def test_expectancy_is_mean_r_within_the_bucket():
    trades = [_t("2021-03-01", 1.0), _t("2021-03-01", -1.0),
              _t("2021-03-05", 2.0)]
    rows = {r["bucket"]: r for r in bucket_trades(trades)}
    assert rows["normal"]["expectancy_r"] == pytest.approx(0.0)
    assert rows["quiet"]["expectancy_r"] == pytest.approx(2.0)


def test_empty_input_returns_empty():
    assert bucket_trades([]) == []


# --- density_profile: descriptive, reported alongside the frozen buckets so a
# --- degenerate distribution is visible as a fact rather than read as a bug.

def test_density_profile_describes_the_day_distribution():
    trades = ([_t("2021-03-01")] * 5) + ([_t("2021-03-02")] * 1)
    prof = density_profile(trades)
    assert prof["n_days"] == 2
    assert prof["n_trades"] == 6
    assert prof["min"] == 1
    assert prof["max"] == 5
    assert prof["mean"] == pytest.approx(3.0)
    assert prof["days_per_bucket"] == {"quiet": 1, "normal": 0, "busy": 1, "flood": 0}


def test_density_profile_median_is_over_days_not_trades():
    trades = ([_t("2021-03-01")] * 9) + [_t("2021-03-02")] + [_t("2021-03-03")]
    prof = density_profile(trades)
    # day counts sorted are [1, 1, 9] -> median day has 1 trade, though most
    # TRADES live on the 9-trade day.
    assert prof["median"] == 1
    assert prof["days_per_bucket"]["flood"] == 1


def test_density_profile_of_nothing_is_empty_not_zero():
    prof = density_profile([])
    assert prof["n_days"] == 0
    assert prof["median"] is None
    assert prof["mean"] is None


# --- per_day_rows: the distinct-ticker count is the whole point, because it
# --- separates "many tickers alerted" from "one setup counted per horizon".

def _th(date, ticker, horizon, r=0.0):
    return {"opened_at": f"{date}T14:30:00", "ticker": ticker,
            "horizon": horizon, "r_multiple": r}


def test_per_day_rows_separate_many_tickers_from_many_horizons():
    breadth = [_th("2021-03-01", f"T{i}", "2w") for i in range(6)]
    depth = [_th("2021-03-02", "AAA", h) for h in
             ("2w", "4w", "2m", "3m", "4m", "5m")]
    rows = {r["date"]: r for r in per_day_rows(breadth + depth)}
    # identical trade counts, and the same bucket, but not the same phenomenon
    assert rows["2021-03-01"]["n_trades"] == rows["2021-03-02"]["n_trades"] == 6
    assert rows["2021-03-01"]["bucket"] == rows["2021-03-02"]["bucket"] == "busy"
    assert rows["2021-03-01"]["n_tickers"] == 6
    assert rows["2021-03-01"]["n_horizons"] == 1
    assert rows["2021-03-02"]["n_tickers"] == 1
    assert rows["2021-03-02"]["n_horizons"] == 6


def test_per_day_rows_are_date_sorted_and_carry_outcomes():
    trades = [_th("2021-03-05", "AAA", "2w", 2.0),
              _th("2021-03-01", "BBB", "2w", 1.0),
              _th("2021-03-01", "CCC", "2w", -1.0)]
    rows = per_day_rows(trades)
    assert [r["date"] for r in rows] == ["2021-03-01", "2021-03-05"]
    assert rows[0]["mean_r"] == pytest.approx(0.0)
    assert rows[0]["win_rate"] == pytest.approx(50.0)


def test_per_day_rows_of_nothing_is_empty():
    assert per_day_rows([]) == []


def test_strategy_rows_carry_direction_and_close_date(monkeypatch):
    """v141 buckets trades by direction and, for one table, by close day."""
    import measure_alert_density as mad
    from swingbot.core.backtesting import backtest

    trade = backtest.BacktestTrade(
        entry_date="2021-03-01", exit_date="2021-03-05", direction="bullish",
        entry=100.0, stop_loss=95.0, take_profit=110.0, outcome="win",
        exit_price=110.0, return_pct=10.0, r_multiple=2.0, holding_days=4)

    class _Summary:
        trades = [trade]

    monkeypatch.setattr(backtest, "run_backtest", lambda *a, **k: _Summary())
    rows, _ = mad._entry_dates_for_ticker(
        "AAA", None, ["2w"], "2021-01-01", "2021-12-31", gates={}, scale_out=True,
        want_strategies=True, want_confluence=False, strategies=["RSI"])

    assert len(rows) == 1
    assert rows[0]["direction"] == "bullish"
    assert rows[0]["closed_at"] == "2021-03-05"
    assert rows[0]["opened_at"] == "2021-03-01"      # unchanged


def test_load_frames_caps_history_before_context_and_liquidity(monkeypatch):
    import pandas as pd
    import measure_alert_density as mad
    import run_backtest_range as rbr
    from swingbot.core.marketdata import universe

    raw = pd.DataFrame({"Close": [100.0, 120.0]},
                       index=pd.to_datetime(["2023-12-29", "2024-01-02"]))
    seen = []

    monkeypatch.setattr(rbr, "load_cached", lambda ticker: raw)

    def context(frame, *, date_to=None):
        seen.append(("context", str(frame.index.max().date()), date_to))
        return frame

    def liquidity(frame):
        seen.append(("liquidity", str(frame.index.max().date()), None))
        return None

    monkeypatch.setattr(rbr, "_with_context", context)
    monkeypatch.setattr(universe, "liquidity_reason", liquidity)
    monkeypatch.setattr(universe, "data_quality_issues", lambda frame, ticker: [])
    frames, excluded = mad.load_frames(["AAA"], date_to="2023-12-31", verbose=False)
    assert excluded == {"uncached": [], "illiquid": [], "bad_data": []}
    assert list(frames["AAA"].index) == [pd.Timestamp("2023-12-29")]
    assert seen == [("context", "2023-12-29", "2023-12-31"),
                    ("liquidity", "2023-12-29", None)]