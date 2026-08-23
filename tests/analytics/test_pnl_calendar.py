"""Day-level P&L aggregation for the /calendar workspace (plan v53).

Every expected value below is hand-computed, per the house convention in
tests/analytics/test_metrics_derived.py -- never copied from a run.
"""
import pytest

from swingbot.core.analytics.pnl_calendar import (available_filters, day_of,
                                                  filter_rows, joined_rows)


def _trade(trade_id, *, closed_at="2026-08-03T20:00:00+00:00", status="win",
           entry=100.0, exit_price=110.0, stop=95.0, pnl=50.0,
           direction="bullish", horizon="4w", ticker="AAPL"):
    """One closed trades.json record. `strategy` is deliberately the literal
    every live confluence trade carries -- see Global Constraint 3."""
    return {
        "id": trade_id, "ticker": ticker, "strategy": "S/R Confluence",
        "horizon_key": horizon, "direction": direction, "status": status,
        "entry": entry, "stop_loss": stop, "exit_price": exit_price,
        "opened_at": "2026-08-01T14:00:00+00:00", "closed_at": closed_at,
        "realized_pnl_amount": pnl, "shares": 10,
        "target_sources": [], "stop_sources": [],
    }


def _entry(trade_id, *, r=2.0, tags=("clean-exit",), lesson="Held to target."):
    """One journal.json record. Note the key is `trade_id`, while the trade
    side calls it `id` -- that asymmetry IS the join."""
    return {
        "trade_id": trade_id, "ticker": "AAPL", "outcome": "win",
        "r_realized": r, "mfe_r": 2.4, "mae_r": -0.3,
        "exit_efficiency": 83.0, "tags": list(tags), "auto_lesson": lesson,
        "note": "", "closed_at": "2026-08-03T20:00:00+00:00",
    }


def test_day_of_slices_the_utc_calendar_day():
    assert day_of("2026-08-03T20:00:00+00:00") == "2026-08-03"
    assert day_of("2026-08-03") == "2026-08-03"
    assert day_of(None) is None
    assert day_of("") is None


def test_join_merges_journal_fields_onto_the_trade():
    rows = joined_rows([_trade("a" * 16)], [_entry("a" * 16)])
    assert len(rows) == 1
    row = rows[0]
    assert row["trade_id"] == "a" * 16
    assert row["day"] == "2026-08-03"
    assert row["pnl_amount"] == 50.0
    # The journal's own r_realized wins over a re-derivation.
    assert row["r_multiple"] == 2.0
    assert row["tags"] == ["clean-exit"]
    assert row["auto_lesson"] == "Held to target."
    assert row["mfe_r"] == 2.4


def test_a_trade_with_no_journal_entry_still_joins():
    """The dollar figure and the grid cell must survive an unjournaled
    trade -- only the lesson/tag fields go absent."""
    rows = joined_rows([_trade("b" * 16)], [])
    assert len(rows) == 1
    row = rows[0]
    assert row["pnl_amount"] == 50.0
    # r falls back to metrics.r_multiple: (110-100)/(100-95) = +2.0
    assert row["r_multiple"] == pytest.approx(2.0)
    assert row["tags"] == []
    assert row["auto_lesson"] is None
    assert row["mfe_r"] is None


def test_open_trades_and_trades_without_a_close_date_are_excluded():
    rows = joined_rows(
        [
            _trade("c" * 16, status="open", closed_at=None),
            _trade("d" * 16, status="win", closed_at=None),
            _trade("e" * 16, status="loss"),
        ],
        [],
    )
    assert [r["trade_id"] for r in rows] == ["e" * 16]


def test_strategy_label_comes_from_primary_strategy_label():
    """Never t["strategy"] -- Global Constraint 3. With no target_sources to
    rank, the label falls back to something, but it must not be the raw
    literal for a trade that HAS sources."""
    trade = _trade("f" * 16)
    trade["target_sources"] = ["EMA20"]
    rows = joined_rows([trade], [])
    assert rows[0]["strategy"] == "EMA20"


def test_filter_rows_narrows_by_strategy_and_horizon():
    a = _trade("a" * 16, horizon="4w"); a["target_sources"] = ["EMA20"]
    b = _trade("b" * 16, horizon="3m"); b["target_sources"] = ["VWAP"]
    rows = joined_rows([a, b], [])

    assert [r["trade_id"] for r in filter_rows(rows, strategy="EMA20")] == ["a" * 16]
    assert [r["trade_id"] for r in filter_rows(rows, horizon="3m")] == ["b" * 16]
    assert filter_rows(rows, strategy="EMA20", horizon="3m") == []
    assert len(filter_rows(rows)) == 2


def test_available_filters_lists_what_the_full_set_contains_sorted():
    a = _trade("a" * 16, horizon="3m"); a["target_sources"] = ["VWAP"]
    b = _trade("b" * 16, horizon="4w"); b["target_sources"] = ["EMA20"]
    options = available_filters(joined_rows([a, b], []))
    assert options == {"strategies": ["EMA20", "VWAP"], "horizons": ["3m", "4w"]}


def test_a_row_carries_exactly_the_declared_keys():
    """ROW_KEYS is what the route's contract test pins, and `assert_shape`
    fails on an undeclared key as loudly as on a missing one. Catching the
    drift here names the cause; catching it there only names a route."""
    from swingbot.core.analytics.pnl_calendar import ROW_KEYS

    rows = joined_rows([_trade("a" * 16)], [_entry("a" * 16)])
    assert set(rows[0]) == set(ROW_KEYS)


from swingbot.core.analytics.pnl_calendar import (bucket_by_day, day_summary,
                                                  month_grid)


def _day_rows():
    """Three closes: two on 2026-08-03 (+50, -20), one on 2026-08-05 (+80).

    Hand-computed: 08-03 net +30.0 with 1 win of 2 -> 50.0% WR; 08-05 net
    +80.0, 100.0% WR. Month total +110.0 over 3 trades, 2 wins -> 66.67%.
    """
    return joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=50.0,
                   status="win", exit_price=110.0),
            _trade("b" * 16, closed_at="2026-08-03T20:30:00+00:00", pnl=-20.0,
                   status="loss", exit_price=96.0),
            _trade("c" * 16, closed_at="2026-08-05T20:00:00+00:00", pnl=80.0,
                   status="win", exit_price=115.0),
        ],
        [],
    )


def test_bucket_by_day_groups_on_the_sliced_day():
    buckets = bucket_by_day(_day_rows())
    assert sorted(buckets) == ["2026-08-03", "2026-08-05"]
    assert len(buckets["2026-08-03"]) == 2


def test_day_summary_sums_dollars_and_r_and_computes_win_rate():
    buckets = bucket_by_day(_day_rows())
    summary = day_summary("2026-08-03", buckets["2026-08-03"])
    assert summary["date"] == "2026-08-03"
    assert summary["net_pnl_amount"] == pytest.approx(30.0)
    # r: (110-100)/5 = +2.0 and (96-100)/5 = -0.8  ->  +1.2
    assert summary["net_r"] == pytest.approx(1.2)
    assert summary["trade_count"] == 2
    assert summary["win_rate"] == pytest.approx(50.0)


def test_day_summary_returns_none_not_zero_when_nothing_is_computable():
    """Global Constraint 5. A day whose only trade has no dollar figure is
    not a flat $0 day."""
    trade = _trade("a" * 16, pnl=None, exit_price=None, status="closed")
    rows = joined_rows([trade], [])
    summary = day_summary("2026-08-03", rows)
    assert summary["net_pnl_amount"] is None
    assert summary["net_r"] is None
    # status "closed" is neither a win nor a loss, so there is no win rate.
    assert summary["win_rate"] is None
    assert summary["trade_count"] == 1


def test_month_grid_omits_days_with_no_closes():
    """Global Constraint 6 -- a day you did not trade is not a flat day."""
    grid = month_grid(_day_rows(), "2026-08")
    assert grid["month"] == "2026-08"
    assert [d["date"] for d in grid["days"]] == ["2026-08-03", "2026-08-05"]
    assert grid["totals"]["net_pnl_amount"] == pytest.approx(110.0)
    assert grid["totals"]["trade_count"] == 3
    assert grid["totals"]["win_rate"] == pytest.approx(66.67, abs=0.01)


def test_month_grid_scopes_to_the_requested_month_only():
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-07-31T20:00:00+00:00"),
            _trade("b" * 16, closed_at="2026-08-01T20:00:00+00:00"),
            _trade("c" * 16, closed_at="2026-09-01T20:00:00+00:00"),
        ],
        [],
    )
    assert [d["date"] for d in month_grid(rows, "2026-08")["days"]] == ["2026-08-01"]


def test_month_grid_on_a_month_with_no_trades_is_empty_not_an_error():
    grid = month_grid(_day_rows(), "2026-01")
    assert grid["days"] == []
    assert grid["totals"]["trade_count"] == 0
    assert grid["totals"]["net_pnl_amount"] is None
    assert grid["totals"]["win_rate"] is None


from swingbot.core.analytics.pnl_calendar import (best_worst_days, day_streak,
                                                  day_of_week_breakdown)


def test_day_of_week_breakdown_always_returns_the_five_trading_days():
    """A weekend never has closes, so Sat/Sun are not modelled at all --
    but Mon-Fri appear even with no data, so the table does not reflow as
    a filter narrows."""
    rows = joined_rows([_trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00")], [])
    breakdown = day_of_week_breakdown(rows)
    assert [b["weekday"] for b in breakdown] == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    # 2026-08-03 is a Monday.
    assert breakdown[0]["trade_count"] == 1
    assert breakdown[0]["avg_pnl_amount"] == pytest.approx(50.0)
    assert breakdown[1]["trade_count"] == 0
    assert breakdown[1]["avg_pnl_amount"] is None
    assert breakdown[1]["win_rate"] is None


def test_day_of_week_breakdown_averages_per_trade_not_per_day():
    """Two Monday closes of +50 and -20 average +15.0 per trade."""
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=50.0),
            _trade("b" * 16, closed_at="2026-08-10T20:00:00+00:00", pnl=-20.0,
                   status="loss", exit_price=96.0),
        ],
        [],
    )
    monday = day_of_week_breakdown(rows)[0]
    assert monday["trade_count"] == 2
    assert monday["avg_pnl_amount"] == pytest.approx(15.0)
    assert monday["win_rate"] == pytest.approx(50.0)


def test_best_and_worst_days_are_whole_days_not_single_trades():
    """08-03 nets +30 (two trades), 08-05 nets -90 (one). The worst DAY is
    08-05 even though 08-03 contains the single worst trade."""
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=50.0),
            _trade("b" * 16, closed_at="2026-08-03T21:00:00+00:00", pnl=-20.0,
                   status="loss", exit_price=96.0),
            _trade("c" * 16, closed_at="2026-08-05T20:00:00+00:00", pnl=-90.0,
                   status="loss", exit_price=91.0),
        ],
        [],
    )
    extremes = best_worst_days(rows)
    assert extremes["best"]["date"] == "2026-08-03"
    assert extremes["best"]["net_pnl_amount"] == pytest.approx(30.0)
    assert extremes["worst"]["date"] == "2026-08-05"
    assert extremes["worst"]["net_pnl_amount"] == pytest.approx(-90.0)


def test_best_worst_days_are_none_on_an_empty_set():
    assert best_worst_days([]) == {"best": None, "worst": None}


def test_day_streak_counts_consecutive_same_sign_days_backwards():
    """08-03 -40, 08-04 +10, 08-05 +30 -> a 2-day winning streak."""
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=-40.0,
                   status="loss", exit_price=96.0),
            _trade("b" * 16, closed_at="2026-08-04T20:00:00+00:00", pnl=10.0),
            _trade("c" * 16, closed_at="2026-08-05T20:00:00+00:00", pnl=30.0),
        ],
        [],
    )
    assert day_streak(rows) == {"direction": "winning", "days": 2}


def test_day_streak_is_not_broken_by_a_gap_with_no_trades():
    """A weekend, a holiday, or a quiet Wednesday is an ABSENCE of evidence,
    not a losing day. Only days that actually had closes are counted."""
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=10.0),
            # 08-04 .. 08-13 have no closes at all.
            _trade("b" * 16, closed_at="2026-08-14T20:00:00+00:00", pnl=20.0),
        ],
        [],
    )
    assert day_streak(rows) == {"direction": "winning", "days": 2}


def test_day_streak_reports_flat_for_a_zero_day_and_stops_there():
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=10.0),
            _trade("b" * 16, closed_at="2026-08-04T20:00:00+00:00", pnl=0.0,
                   status="closed", exit_price=100.0),
        ],
        [],
    )
    assert day_streak(rows) == {"direction": "flat", "days": 1}


def test_day_streak_on_an_empty_set():
    assert day_streak([]) == {"direction": None, "days": 0}
