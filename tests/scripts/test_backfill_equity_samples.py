"""v172: the equity backfill -- clamped day rows (V172-6); the CLI tests follow (V172-7)."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from scripts.data import backfill_equity_samples as bes
from swingbot.core.tracking import equity

START = Decimal("10000")
MON, TUE, WED = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)
TAG = "20261008T120000Z@bars-asof-2026-10-07"

# Long AAPL: entered Mon 10:00 NY, exited Wed 14:00 NY at 110 (+100).
AAPL = {"id": "a1", "ticker": "AAPL", "direction": "bullish", "status": "win",
        "entry": 100.0, "stop_loss": 95.0, "shares": 10.0, "exit_price": 110.0,
        "opened_at": "2026-10-05T14:00:00+00:00", "closed_at": "2026-10-07T18:00:00+00:00",
        "realized_pnl_amount": 100.0, "ledger": "main"}
# Short MSFT: entered Tue 11:00 NY, still open.
MSFT = {"id": "m1", "ticker": "MSFT", "direction": "bearish", "status": "open",
        "entry": 200.0, "stop_loss": 210.0, "shares": 5.0,
        "opened_at": "2026-10-06T15:00:00+00:00", "ledger": "main"}
TRADES = [AAPL, MSFT]


def _frame(bars):
    return pd.DataFrame([{"Open": o, "High": h, "Low": low, "Close": c}
                         for (o, h, low, c) in bars.values()],
                        index=pd.DatetimeIndex([pd.Timestamp(d) for d in bars]))


BARS = {
    "AAPL": _frame({MON: (99, 104, 98, 102), TUE: (102, 106, 101, 105), WED: (105, 112, 104, 111)}),
    "MSFT": _frame({TUE: (201, 203, 196, 198), WED: (198, 199, 194, 195)}),
}


def _rows(day, *, trades=TRADES, bars=BARS, allow_gaps=False):
    return bes.build_day_rows(day, bes.held_positions(trades, day), bars,
                              equity.realized_legs(trades), START, TAG, allow_gaps=allow_gaps)


def _kinds_and_equity(rows):
    return [(row["kind"], row["equity"]) for row in rows]


def test_session_bounds_are_new_york_open_and_close_in_utc():
    assert bes.session_bounds(MON) == (datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc),
                                       datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc))
    assert bes.session_bounds(date(2026, 12, 7)) == (       # EST, UTC-5
        datetime(2026, 12, 7, 14, 30, tzinfo=timezone.utc),
        datetime(2026, 12, 7, 21, 0, tzinfo=timezone.utc))


@pytest.mark.parametrize("day, expected", [
    # entry day of AAPL: path 100 -> 102; open contributes 0
    (MON, [("point", 10000), ("day_high", 10020), ("day_low", 10000), ("point", 10020)]),
    # AAPL full bar; MSFT entry day (short, path 200 -> 198)
    (TUE, [("point", 10020), ("day_high", 10070), ("day_low", 10010), ("point", 10060)]),
    # AAPL exit day (path 105 -> 110, net of the banked +100); MSFT full bar
    (WED, [("point", 10060), ("day_high", 10130), ("day_low", 10055), ("point", 10125)]),
])
def test_four_rows_a_day_with_clamped_extremes(day, expected):
    rows, skips = _rows(day)
    assert skips == []
    assert _kinds_and_equity(rows) == expected
    open_at, close_at = bes.session_bounds(day)
    assert [row["at"] for row in rows] == [open_at, open_at, open_at, close_at]
    assert {(row["source"], row["backfill_run"]) for row in rows} == {("backfill", TAG)}


def test_the_open_point_uses_yesterdays_realized_and_the_rest_todays():
    rows, _ = _rows(WED)
    assert [row["realized_balance"] for row in rows] == [10000, 10100, 10100, 10100]
    assert [row["unrealized_pnl"] for row in rows] == [60, 30, -45, 25]
    assert {(row["open_n"], row["skipped_n"]) for row in rows} == {(2, 0)}


def _pos(*, entry_day=MON, exit_day=None, exit_price=None, direction="bullish"):
    return {"trade_id": "x", "ticker": "X", "direction": direction, "entry": 100.0,
            "shares": 1.0, "entry_day": entry_day, "exit_day": exit_day, "exit_price": exit_price}


def test_entry_day_reads_no_bar_data_from_before_the_entry():
    bar = bes.Bar(open=50.0, high=999.0, low=1.0, close=101.0)
    assert bes.position_day(_pos(), bar, MON) == {
        "open_u": 0, "high_u": 1, "low_u": 0, "close_u": 1}


def test_exit_day_reads_no_bar_data_from_after_the_exit():
    bar = bes.Bar(open=102.0, high=999.0, low=1.0, close=50.0)
    assert bes.position_day(_pos(exit_day=WED, exit_price=105.0), bar, WED) == {
        "open_u": 2, "high_u": 0, "low_u": -3, "close_u": 0}


def test_a_same_day_round_trip_runs_entry_to_exit_only():
    bar = bes.Bar(open=90.0, high=999.0, low=1.0, close=80.0)
    assert bes.position_day(_pos(exit_day=MON, exit_price=103.0), bar, MON) == {
        "open_u": 0, "high_u": 0, "low_u": -3, "close_u": 0}


def test_a_short_on_a_full_day_favours_the_low():
    bar = bes.Bar(open=98.0, high=99.0, low=94.0, close=95.0)
    assert bes.position_day(_pos(entry_day=MON, direction="bearish"), bar, TUE) == {
        "open_u": 2, "high_u": 6, "low_u": 1, "close_u": 5}


def test_a_tp1_partial_is_two_slices_and_its_banked_leg_is_counted_once():
    leg = {"fraction": 0.5, "exit_price": 106.0, "r": 1.2, "reason": "tp1",
           "closed_at": "2026-10-06T16:00:00+00:00"}               # Tue 12:00 NY, at the bar high
    trade = {**AAPL, "id": "p1", "status": "open", "exit_price": None, "closed_at": None,
             "realized_pnl_amount": None, "legs": [leg]}
    held = bes.held_positions([trade], TUE)
    assert [(p["shares"], p["exit_day"], p["exit_price"]) for p in held] == [
        (5.0, TUE, 106.0), (5.0, None, None)]
    assert [(p["shares"], p["exit_day"]) for p in bes.held_positions([trade], WED)] == [(5.0, None)]
    rows, _ = _rows(TUE, trades=[trade])
    # Banked +30 at 106. Both halves at 106 is the reachable high: 10000 + 30 + 30 = 10060.
    # Adding the banked half's full pnl on top of realized(D) would read 10090.
    assert _kinds_and_equity(rows) == [
        ("point", 10020), ("day_high", 10060), ("day_low", 10015), ("point", 10055)]


def test_weak_and_outlook_trades_never_enter_a_day():
    weak = {**MSFT, "id": "w1", "ledger": "weak"}
    outlook = {**MSFT, "id": "o1", "origin": "next_session"}
    assert bes.held_positions([weak, outlook], TUE) == []


def test_filled_trades_drops_pending_placeholders_only():
    pending = {**MSFT, "id": "pp", "plan_id": "P1"}
    active = {**MSFT, "id": "pa", "plan_id": "P2"}
    closed = {**AAPL, "plan_id": "P3"}
    plans = {"P1": {"status": "PENDING"}, "P2": {"status": "ACTIVE"}, "P3": {"status": "CLOSED"}}
    kept = bes.filled_trades([pending, active, closed, MSFT], plans)
    assert [t["id"] for t in kept] == ["pa", "a1", "m1"]


def test_a_missing_bar_is_a_gap_refused_unless_allowed():
    bars = {"AAPL": BARS["AAPL"], "MSFT": _frame({TUE: (201, 203, 196, 198)})}
    with pytest.raises(bes.CoverageGap):
        _rows(WED, bars=bars)
    rows, skips = _rows(WED, bars=bars, allow_gaps=True)
    assert skips == [bes.Skip(WED, "m1", "MSFT", "no bar")]
    assert {(row["open_n"], row["skipped_n"]) for row in rows} == {(1, 1)}
    assert rows[-1]["equity"] == 10100                     # AAPL realized, MSFT left out


def test_a_ticker_with_no_frame_is_a_fetch_failure_gap():
    _, skips = _rows(WED, bars={"AAPL": BARS["AAPL"]}, allow_gaps=True)
    assert [s.reason for s in skips] == ["fetch failed"]


def test_an_unsized_position_is_skipped_but_is_not_a_gap():
    unsized = {**MSFT, "shares": None}
    rows, skips = _rows(WED, trades=[AAPL, unsized])          # allow_gaps=False: no raise
    assert skips == [bes.Skip(WED, "m1", "MSFT", "no size")]
    assert rows[0]["skipped_n"] == 1


def test_bar_for_matches_by_date_and_rejects_nan():
    frame = _frame({MON: (1, 2, 0.5, float("nan"))})
    assert bes.bar_for(frame, MON) is None
    assert bes.bar_for(BARS["AAPL"], MON) == bes.Bar(99.0, 104.0, 98.0, 102.0)
    assert bes.bar_for(BARS["AAPL"], date(2026, 10, 8)) is None
    assert bes.bar_for(None, MON) is None
