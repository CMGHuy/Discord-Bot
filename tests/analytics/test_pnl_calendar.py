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


# --- Scaled-out positions: one calendar row per realized leg ---------------
#
# The Dashboard's Trades table splits a scaled-out plan into one CLOSED row
# per leg (v79) and dates each by the leg's own close. The calendar has to
# count the same population, or "closed today" reads 23 here and 36 there.

_TP1 = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0,
        "closed_at": "2026-08-03T15:00:00+00:00"}
_RUNNER = {"fraction": 0.5, "exit_price": 105.0, "r": 1.0,
           "closed_at": "2026-08-05T19:00:00+00:00"}


def _scaled_trade(trade_id, *, status="win", closed_at="2026-08-05T19:00:00+00:00",
                  pnl=75.0, legs=(_TP1, _RUNNER)):
    """10 shares, entry 100, stop 95 (risk 5). TP1 half at 110 (+2R, +$50),
    runner half at 105 (+1R, +$25) -> whole trade +$75."""
    trade = _trade(trade_id, status=status, closed_at=closed_at, pnl=pnl,
                   exit_price=107.5 if status != "open" else None)
    trade["legs"] = [dict(leg) for leg in legs]
    return trade


def test_a_scaled_out_trade_yields_one_row_per_leg_on_each_legs_own_day():
    rows = joined_rows([_scaled_trade("a" * 16)], [])
    assert [(r["day"], r["leg_index"], r["leg_total"]) for r in rows] == [
        ("2026-08-03", 0, 2), ("2026-08-05", 1, 2)]
    # Dollars per leg: 5 shares x +10 = +50, 5 shares x +5 = +25.
    assert [r["pnl_amount"] for r in rows] == [50.0, 25.0]
    # Each leg is an individual trade with its own R.
    assert [r["r_multiple"] for r in rows] == pytest.approx([2.0, 1.0])
    assert [r["outcome"] for r in rows] == ["win", "win"]


def test_a_legs_r_is_its_own_even_when_the_journal_has_the_blended_one():
    rows = joined_rows([_scaled_trade("a" * 16)], [_entry("a" * 16, r=1.5)])
    assert [r["r_multiple"] for r in rows] == pytest.approx([2.0, 1.0])
    # The journal's lesson still rides every leg of its trade.
    assert all(r["auto_lesson"] == "Held to target." for r in rows)


def test_the_legs_dollars_always_sum_to_the_trades_own_total():
    rows = joined_rows([_scaled_trade("a" * 16, pnl=74.99)], [])
    assert [r["pnl_amount"] for r in rows] == pytest.approx([50.0, 24.99])


def test_a_banked_tp1_leg_of_a_still_open_runner_is_counted():
    trade = _scaled_trade("a" * 16, status="open", closed_at=None, pnl=None,
                          legs=(_TP1,))
    rows = joined_rows([trade], [])
    assert len(rows) == 1
    row = rows[0]
    assert (row["day"], row["leg_index"], row["leg_total"]) == ("2026-08-03", 0, 2)
    assert row["pnl_amount"] == 50.0
    assert row["r_multiple"] == pytest.approx(2.0)


def test_a_trade_that_never_scaled_out_is_still_one_row():
    rows = joined_rows([_trade("a" * 16)], [])
    assert [(r["leg_index"], r["leg_total"]) for r in rows] == [(0, 1)]
    assert rows[0]["pnl_amount"] == 50.0


# --- v165 D1: fuller rows -------------------------------------------------
#
# Every figure is read from the part `expand_realized_legs` produced (leg
# prices, leg shares, leg close) -- never re-derived from the plan, never a
# third copy of the leg pricing in `expand_trade_legs` / `_row_from_leg`.

from swingbot.core.analytics.pnl_calendar import (ROW_KEYS, held_hours,
                                                  return_pct, row_exit_reason)

_D1_KEYS = ("entry_price", "exit_price", "stop_price", "tp1", "tp2", "shares",
            "held_hours", "return_pct", "exit_reason")


def test_the_d1_keys_are_appended_after_leg_total_in_order():
    assert ROW_KEYS[-10:] == ("leg_total", *_D1_KEYS)


def test_a_whole_trade_row_carries_every_d1_field():
    trade = _trade("a" * 16)
    trade.update(take_profit=120.0, target2=130.0, close_reason="time_exit")
    row = joined_rows([trade], [])[0]
    assert {k: row[k] for k in _D1_KEYS} == {
        "entry_price": 100.0, "exit_price": 110.0, "stop_price": 95.0,
        "tp1": 120.0, "tp2": 130.0, "shares": 10.0,
        # 2026-08-01T14:00Z -> 2026-08-03T20:00Z = 2 days 6 hours.
        "held_hours": 54.0,
        # (110 - 100) / 100 * 100.
        "return_pct": 10.0,
        # Whole trade: metrics.exit_reason_bucket(trade), alias time_exit.
        "exit_reason": "timeout",
    }


def test_a_short_whole_trade_return_is_sign_flipped():
    trade = _trade("a" * 16, direction="bearish", exit_price=90.0, stop=105.0)
    row = joined_rows([trade], [])[0]
    # (100 - 90) / 100 * 100: a short that fell 10% made +10%.
    assert row["return_pct"] == 10.0


def _reasoned_scaled_trade():
    """TP1 half at 110 on 08-03 15:00Z, runner half at 105 on 08-05 19:00Z,
    each leg carrying the reason the v2 manager writes."""
    trade = _scaled_trade("a" * 16, legs=({**_TP1, "reason": "tp1"},
                                          {**_RUNNER, "reason": "runner_trail"}))
    trade.update(take_profit=110.0, target2=120.0)
    return trade


def test_a_tp1_leg_reads_its_own_prices_shares_hold_and_reason():
    leg = joined_rows([_reasoned_scaled_trade()], [])[0]
    assert {k: leg[k] for k in _D1_KEYS} == {
        "entry_price": 100.0, "exit_price": 110.0, "stop_price": 95.0,
        "tp1": 110.0, "tp2": 120.0,
        # 10 shares x fraction 0.5, already scaled by expand_trade_legs.
        "shares": 5.0,
        # 2026-08-01T14:00Z -> the LEG's close 2026-08-03T15:00Z = 49 h.
        "held_hours": 49.0,
        "return_pct": 10.0,
        "exit_reason": "tp1",
    }


def test_the_closing_leg_of_a_finished_scale_out_reads_its_own_figures():
    closing = joined_rows([_reasoned_scaled_trade()], [])[1]
    assert {k: closing[k] for k in _D1_KEYS} == {
        "entry_price": 100.0, "exit_price": 105.0, "stop_price": 95.0,
        "tp1": 110.0, "tp2": 120.0, "shares": 5.0,
        # 2026-08-01T14:00Z -> 2026-08-05T19:00Z = 4 days 5 hours.
        "held_hours": 101.0,
        "return_pct": 5.0,
        "exit_reason": "runner_trail",
    }


def test_leg_dollars_still_sum_to_the_trades_realized_total():
    # The one leg invariant v165 claims (D1). Leg R is NOT additive and is
    # deliberately not asserted to sum to anything.
    trade = _reasoned_scaled_trade()
    rows = joined_rows([trade], [])
    assert sum(r["pnl_amount"] for r in rows) == pytest.approx(trade["realized_pnl_amount"])


def test_a_single_leg_trade_is_whole_and_uses_the_trade_level_bucket():
    only = {"fraction": 1.0, "exit_price": 105.0, "reason": "tp1_runner_be",
            "closed_at": "2026-08-05T19:00:00+00:00"}
    row = joined_rows([_scaled_trade("a" * 16, legs=(only,), pnl=50.0)], [])[0]
    assert (row["leg_index"], row["leg_total"]) == (0, 1)
    # legs[-1].reason through the alias table.
    assert row["exit_reason"] == "runner_be"


def test_a_banked_leg_of_an_open_runner_buckets_by_the_legs_reason():
    trade = _scaled_trade("a" * 16, status="open", closed_at=None, pnl=None,
                          legs=({**_TP1, "reason": "tp1"},))
    row = joined_rows([trade], [])[0]
    assert (row["leg_total"], row["exit_reason"]) == (2, "tp1")


def test_a_leg_with_no_or_unknown_reason_buckets_other():
    # _TP1/_RUNNER carry no "reason" key at all.
    rows = joined_rows([_scaled_trade("a" * 16)], [])
    assert [r["exit_reason"] for r in rows] == ["other", "other"]
    odd = _scaled_trade("b" * 16, legs=({**_TP1, "reason": "operator felt like it"},
                                        {**_RUNNER, "reason": None}))
    assert [r["exit_reason"] for r in joined_rows([odd], [])] == ["other", "other"]


@pytest.mark.parametrize(("part", "trade"), [
    pytest.param({"leg_index": 3, "leg_total": 4}, {"legs": [{"reason": "tp1"}]},
                 id="index-overruns-legs"),
    pytest.param({"leg_index": 0, "leg_total": 2}, {"legs": None}, id="no-legs"),
    pytest.param({"leg_index": None, "leg_total": 2}, {"legs": [{"reason": "tp1"}]},
                 id="no-index"),
    pytest.param({"leg_index": -1, "leg_total": 2}, {"legs": [{"reason": "tp1"}]},
                 id="negative-index"),
])
def test_row_exit_reason_never_raises_on_a_malformed_leg(part, trade):
    assert row_exit_reason(part, trade) == "other"


def test_missing_prices_and_stamps_are_none_never_zero():
    trade = _trade("a" * 16, exit_price=None)
    trade.update(opened_at=None, shares=None)
    row = joined_rows([trade], [])[0]
    assert row["exit_price"] is None
    assert row["return_pct"] is None
    assert row["held_hours"] is None
    assert row["shares"] is None
    # _trade sets no take_profit / target2 at all.
    assert (row["tp1"], row["tp2"]) == (None, None)


@pytest.mark.parametrize(("opened", "closed", "hours"), [
    pytest.param("2026-08-01T14:00:00+00:00", "2026-08-03T20:00:00+00:00", 54.0, id="offset"),
    pytest.param("2026-08-01T14:00:00Z", "2026-08-01T16:00:00Z", 2.0, id="zulu"),
    pytest.param("2026-08-01T14:00:00", "2026-08-01T15:30:00+00:00", 1.5, id="naive-is-utc"),
    pytest.param("2026-08-01T14:00:00+00:00", "2026-08-01T14:20:00+00:00", 0.33, id="two-dp"),
    pytest.param("2026-08-01T14:00:00+00:00", "2026-08-01T14:00:00+00:00", 0.0, id="same-instant"),
])
def test_held_hours(opened, closed, hours):
    assert held_hours(opened, closed) == hours


@pytest.mark.parametrize(("opened", "closed"), [
    pytest.param(None, "2026-08-03T20:00:00+00:00", id="no-open"),
    pytest.param("2026-08-01T14:00:00+00:00", None, id="no-close"),
    pytest.param("2026-08-01T14:00:00+00:00", "", id="empty-close"),
    pytest.param("yesterday", "2026-08-03T20:00:00+00:00", id="unparseable"),
    pytest.param("2026-08-03T20:00:00+00:00", "2026-08-01T14:00:00+00:00", id="reversed"),
])
def test_held_hours_is_none_when_it_cannot_be_measured(opened, closed):
    assert held_hours(opened, closed) is None


@pytest.mark.parametrize(("entry", "exit_price", "direction", "pct"), [
    pytest.param(100.0, 110.0, "bullish", 10.0, id="long-up"),
    pytest.param(100.0, 90.0, "bullish", -10.0, id="long-down"),
    pytest.param(100.0, 90.0, "bearish", 10.0, id="short-down"),
    pytest.param(100.0, 110.0, "bearish", -10.0, id="short-up"),
    pytest.param(3.0, 3.1, "bullish", 3.33, id="two-dp"),
])
def test_return_pct(entry, exit_price, direction, pct):
    assert return_pct(entry, exit_price, direction) == pct


@pytest.mark.parametrize(("entry", "exit_price", "direction"), [
    pytest.param(None, 110.0, "bullish", id="no-entry"),
    pytest.param(0.0, 110.0, "bullish", id="zero-entry"),
    pytest.param(100.0, None, "bullish", id="no-exit"),
    pytest.param(100.0, 110.0, None, id="no-direction"),
    pytest.param(100.0, 110.0, "sideways", id="unknown-direction"),
])
def test_return_pct_is_none_when_it_cannot_be_signed(entry, exit_price, direction):
    assert return_pct(entry, exit_price, direction) is None


# --- v165 D2: day context -------------------------------------------------
#
# Rows are built directly: day_context reads only day / pnl_amount /
# r_multiple / outcome, exactly what day_summary (the cell rule) reads.

import datetime as _dt

from swingbot.core.analytics.pnl_calendar import PERCENTILE_MIN_DAYS, day_context

_NULL_CONTEXT_DELTAS = {"pnl_amount": None, "r": None}


def _net_row(day, pnl, r=None):
    return {"day": day, "pnl_amount": pnl, "r_multiple": r,
            "outcome": "win" if (pnl or 0) > 0 else "loss"}


def _other_days(values, start="2026-05-01"):
    """One single-row day per value, on consecutive calendar dates from
    `start` -- weekday is irrelevant to the percentile."""
    first = _dt.date.fromisoformat(start)
    return [_net_row((first + _dt.timedelta(days=i)).isoformat(), value)
            for i, value in enumerate(values)]


def test_the_percentile_floor_is_twenty_other_days():
    assert PERCENTILE_MIN_DAYS == 20


def test_percentile_counts_ties_half_against_the_other_days_only():
    # 20 other days: 10 at -10, 5 at +5, 5 at +20. This day: +5.
    # Below: 10, ties: 5 -> (10 + 2.5) / 20 * 100 = 62.5.
    # Were the day in its own set it would be (10 + 3) / 21 * 100 = 61.9.
    others = _other_days([-10.0] * 10 + [5.0] * 5 + [20.0] * 5)
    context = day_context(others + [_net_row("2026-08-10", 5.0)], "2026-08-10")
    assert context["percentile"] == 62.5
    assert context["history_days"] == 20


def test_percentile_is_null_below_twenty_other_days():
    nineteen = _other_days([1.0] * 19)
    context = day_context(nineteen + [_net_row("2026-08-10", 5.0)], "2026-08-10")
    assert context["percentile"] is None
    assert context["history_days"] == 19

    twenty = _other_days([1.0] * 20)
    context = day_context(twenty + [_net_row("2026-08-10", 5.0)], "2026-08-10")
    assert context["percentile"] == 100.0


def test_null_net_days_are_left_out_of_the_reference_set():
    others = _other_days([-10.0] * 10 + [5.0] * 5 + [20.0] * 5)
    unknown = [_net_row("2026-07-01", None, 3.0), _net_row("2026-07-02", None),
               _net_row("2026-07-03", None)]
    context = day_context(others + unknown + [_net_row("2026-08-10", 5.0)], "2026-08-10")
    # Same as without them: never counted as a $0 day.
    assert context["percentile"] == 62.5
    assert context["history_days"] == 20


def test_vs_average_day_and_vs_same_weekday_compare_day_nets():
    # 2026-08-10 and 2026-08-03 and 2026-07-27 are Mondays, 08-04 a Tuesday,
    # 08-05 a Wednesday.
    rows = [
        _net_row("2026-08-10", 40.0, 2.0),            # this day
        _net_row("2026-08-03", 10.0, 1.0),
        _net_row("2026-07-27", 30.0, None),           # null R: out of R means only
        _net_row("2026-08-04", -100.0, -5.0),
        _net_row("2026-08-05", None, 9.0),            # null P&L: out of everything
    ]
    context = day_context(rows, "2026-08-10")
    assert context["history_days"] == 3
    assert context["percentile"] is None              # 3 < 20
    # P&L mean of the 3 reference days: (10 + 30 - 100) / 3 = -20 -> 40 - -20.
    # R mean of the 2 with an R: (1 - 5) / 2 = -2 -> 2 - -2.
    assert context["vs_avg_day"] == {"pnl_amount": 60.0, "r": 4.0}
    # Mondays: P&L mean (10 + 30) / 2 = 20; R mean over 08-03 only = 1.
    assert context["vs_weekday_avg"] == {"pnl_amount": 20.0, "r": 1.0}


def test_the_day_net_is_the_calendar_cells_rule():
    # Partial-null day: the cell sums the computable rows (50, 1.0).
    rows = [_net_row("2026-08-10", 50.0, 1.0), _net_row("2026-08-10", None, None),
            _net_row("2026-08-03", 10.0, 0.5)]
    context = day_context(rows, "2026-08-10")
    assert context["vs_avg_day"] == {"pnl_amount": 40.0, "r": 0.5}
    assert context["vs_weekday_avg"] == {"pnl_amount": 40.0, "r": 0.5}


def test_deltas_are_rounded_to_two_places():
    rows = [_net_row("2026-08-10", 10.0, 1.0), _net_row("2026-08-03", 1.0, 0.1),
            _net_row("2026-08-04", 2.0, 0.2), _net_row("2026-08-05", 2.0, 0.2)]
    context = day_context(rows, "2026-08-10")
    # mean P&L 5/3 = 1.6667 -> 10 - 1.6667 = 8.3333; mean R 0.5/3 -> 0.8333.
    assert context["vs_avg_day"] == {"pnl_amount": 8.33, "r": 0.83}


def test_a_day_with_a_null_net_gets_null_context():
    others = _other_days([10.0] * 25)
    context = day_context(others + [_net_row("2026-08-10", None, 1.0)], "2026-08-10")
    assert context == {
        "percentile": None, "history_days": 25,
        "vs_avg_day": _NULL_CONTEXT_DELTAS, "vs_weekday_avg": _NULL_CONTEXT_DELTAS,
    }


def test_a_date_with_no_rows_and_an_empty_book_are_null_not_errors():
    assert day_context([], "2026-08-03") == {
        "percentile": None, "history_days": 0,
        "vs_avg_day": _NULL_CONTEXT_DELTAS, "vs_weekday_avg": _NULL_CONTEXT_DELTAS,
    }
    only_others = _other_days([10.0] * 3)
    assert day_context(only_others, "2026-08-03")["vs_avg_day"] == _NULL_CONTEXT_DELTAS


def test_a_weekday_with_no_other_days_has_a_null_weekday_delta():
    rows = [_net_row("2026-08-10", 40.0, 2.0), _net_row("2026-08-04", 10.0, 1.0)]
    context = day_context(rows, "2026-08-10")
    assert context["vs_avg_day"] == {"pnl_amount": 30.0, "r": 1.0}
    assert context["vs_weekday_avg"] == _NULL_CONTEXT_DELTAS


# --- v165 D3: what drove the day ------------------------------------------

from swingbot.core.analytics.pnl_calendar import (BREAKDOWN_DIMENSIONS,
                                                  _sum_or_none, day_breakdown)


def _drove_row(strategy, horizon, direction, exit_reason, pnl, r, outcome):
    return {"strategy": strategy, "horizon": horizon, "direction": direction,
            "exit_reason": exit_reason, "pnl_amount": pnl, "r_multiple": r,
            "outcome": outcome}


def _drove_rows():
    """Four rows on one day. Hand-computed groups are in the tests below."""
    return [
        _drove_row("EMA20", "4w", "bullish", "tp1", 50.0, 2.0, "win"),
        _drove_row("EMA20", "3m", "bullish", "stop", -20.0, -0.8, "loss"),
        _drove_row("VWAP", "4w", "bearish", "tp1", 30.0, 1.0, "win"),
        # A manual close with no dollar figure and no R: counted, not $0.
        _drove_row("VWAP", None, "bearish", "other", None, None, "closed"),
    ]


def test_breakdown_has_exactly_the_four_dimensions():
    assert BREAKDOWN_DIMENSIONS == ("strategy", "horizon", "direction", "exit_reason")
    assert tuple(day_breakdown(_drove_rows())) == BREAKDOWN_DIMENSIONS


def test_breakdown_groups_sum_and_rate_each_dimension():
    breakdown = day_breakdown(_drove_rows())
    # EMA20: +50 -20 = +30, R 2.0 - 0.8 = 1.2, 1 win of 2 decided.
    # VWAP: +30 (the null row adds nothing), R 1.0, 1 win of 1 decided.
    # Equal P&L -> key order.
    assert breakdown["strategy"] == [
        {"key": "EMA20", "n": 2, "pnl_amount": 30.0, "r": 1.2, "win_rate": 50.0},
        {"key": "VWAP", "n": 2, "pnl_amount": 30.0, "r": 1.0, "win_rate": 100.0},
    ]
    assert breakdown["direction"] == [
        {"key": "bearish", "n": 2, "pnl_amount": 30.0, "r": 1.0, "win_rate": 100.0},
        {"key": "bullish", "n": 2, "pnl_amount": 30.0, "r": 1.2, "win_rate": 50.0},
    ]


def test_a_null_key_is_unknown_and_an_all_null_group_sorts_last():
    breakdown = day_breakdown(_drove_rows())
    assert breakdown["horizon"] == [
        {"key": "4w", "n": 2, "pnl_amount": 80.0, "r": 3.0, "win_rate": 100.0},
        {"key": "3m", "n": 1, "pnl_amount": -20.0, "r": -0.8, "win_rate": 0.0},
        # No decided row -> win_rate None, not 0; no dollars -> None, not 0.
        {"key": "unknown", "n": 1, "pnl_amount": None, "r": None, "win_rate": None},
    ]
    assert breakdown["exit_reason"] == [
        {"key": "tp1", "n": 2, "pnl_amount": 80.0, "r": 3.0, "win_rate": 100.0},
        {"key": "stop", "n": 1, "pnl_amount": -20.0, "r": -0.8, "win_rate": 0.0},
        {"key": "other", "n": 1, "pnl_amount": None, "r": None, "win_rate": None},
    ]


def test_every_dimension_sums_back_to_the_days_totals():
    rows = _drove_rows()
    total_pnl = _sum_or_none([r["pnl_amount"] for r in rows])
    total_r = _sum_or_none([r["r_multiple"] for r in rows])
    for dimension, groups in day_breakdown(rows).items():
        assert sum(g["n"] for g in groups) == len(rows), dimension
        assert sum(g["pnl_amount"] for g in groups
                   if g["pnl_amount"] is not None) == pytest.approx(total_pnl), dimension
        assert sum(g["r"] for g in groups if g["r"] is not None) == pytest.approx(total_r), dimension


def test_an_empty_key_string_is_unknown_too():
    rows = [_drove_row("", "4w", "bullish", "tp1", 10.0, 1.0, "win")]
    assert day_breakdown(rows)["strategy"][0]["key"] == "unknown"


def test_an_empty_day_breaks_down_into_empty_lists():
    assert day_breakdown([]) == {d: [] for d in BREAKDOWN_DIMENSIONS}


def test_breakdown_reads_the_d1_exit_reason_of_joined_rows():
    trade = _scaled_trade("a" * 16, legs=({**_TP1, "reason": "tp1"},
                                          {**_RUNNER, "reason": "runner_trail"}))
    keys = {g["key"] for g in day_breakdown(joined_rows([trade], []))["exit_reason"]}
    assert keys == {"tp1", "runner_trail"}
