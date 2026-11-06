"""v208 V208-10: session state, clamp, rebase, series, markers, exposure."""
from datetime import date, datetime, timezone
from itertools import count

import pytest

from swingbot.core.analytics import benchmark_view as bv
from swingbot.core.market.session import US_MARKET_TZ

UTC = timezone.utc
MON, TUE, WED, THU, FRI = (date(2026, 11, d) for d in (2, 3, 4, 5, 6))
WEEK = [MON, TUE, WED, THU, FRI]
OPEN_FRI = datetime(2026, 11, 6, 15, 0, tzinfo=UTC)          # 10:00 ET
CLOSED_FRI = datetime(2026, 11, 6, 22, 0, tzinfo=UTC)        # 17:00 ET
SYMBOLS = ("SPY", "QQQ", "^IXIC", "^DJI")
_ids = count(1)


def _row(day, hh, mm, equity, *, realized=10_000.0, notional=None):
    at = datetime(day.year, day.month, day.day, hh, mm, tzinfo=US_MARKET_TZ).astimezone(UTC)
    row = {"id": next(_ids), "at": at, "equity": equity, "realized_balance": realized,
           "unrealized_pnl": equity - realized, "open_n": 1, "skipped_n": 0,
           "source": "live", "kind": "point"}
    if notional is not None:
        row["open_notional"] = notional
    return row


def _bar(symbol, day, pct, *, final=True):
    return {"symbol": symbol, "session": day, "close": None, "adj_close": None, "day_pct": pct,
            "source_symbol": symbol, "final": final, "as_of": OPEN_FRI}


ROWS = [_row(MON, 15, 55, 10_000.0, notional=5_000.0), _row(TUE, 15, 55, 10_100.0),
        _row(THU, 15, 55, 10_302.0), _row(FRI, 10, 0, 10_400.0)]            # WED missing
BARS = [_bar("SPY", d, p) for d, p in ((MON, 0.001), (TUE, 0.01), (WED, 0.02), (THU, -0.01))] \
    + [_bar("SPY", FRI, 0.005, final=False)]


def _inputs(rows=ROWS, bars=BARS, now=OPEN_FRI, sessions=WEEK):
    return bv.BenchmarkInputs(rows=list(rows), legs=[], bars=list(bars), sessions=list(sessions),
                              now=now, account_currency="USD", mixed_tickers=[], refresher_on=True)


def _series(inputs, start=None, end=None):
    completed = bv.completed_sessions(inputs, bv.view_session_state(inputs.now))
    rng = bv.clamp_range(completed, bv.live_since_of(inputs.rows), start, end)
    series, markers, exposure = bv.build_series(bv.build_frame(inputs, rng))
    return {s["key"]: s for s in series}, markers, exposure


def _pts(series, key):
    return [(p["date"], p["cum_pct"], p["day_pct"], p["span"], p["missing"]) for p in series[key]["points"]]


def test_pct_is_a_rounded_percentage():
    assert bv.pct(0.012345678) == 1.2346 and bv.pct(None) is None and bv.pct(0.0) == 0.0


@pytest.mark.parametrize("now, state", [
    (datetime(2026, 11, 4, 15, 0, tzinfo=UTC), "open"),
    (datetime(2026, 11, 4, 12, 0, tzinfo=UTC), "pre"),
    (datetime(2026, 11, 4, 21, 0, tzinfo=UTC), "closed"),     # 16:00 ET
    (datetime(2026, 11, 7, 15, 0, tzinfo=UTC), "pre"),        # Saturday
    (datetime(2026, 11, 26, 17, 0, tzinfo=UTC), "pre"),       # Thanksgiving
    (datetime(2026, 11, 27, 17, 30, tzinfo=UTC), "open"),     # half day, 12:30 ET
    (datetime(2026, 11, 27, 18, 30, tzinfo=UTC), "closed"),   # half day, 13:30 ET
])
def test_view_session_state(now, state):
    assert bv.view_session_state(now) == state


def test_today_joins_only_once_closed_with_four_final_bars():
    final_fri = [_bar(s, FRI, 0.0) for s in SYMBOLS]
    assert bv.completed_sessions(_inputs(bars=final_fri), "open") == [MON, TUE, WED, THU]
    assert bv.completed_sessions(_inputs(bars=final_fri, now=CLOSED_FRI), "closed") == WEEK
    one_late = final_fri[:3] + [_bar("^DJI", FRI, 0.0, final=False)]
    assert bv.completed_sessions(_inputs(bars=one_late, now=CLOSED_FRI), "closed") == [MON, TUE, WED, THU]


@pytest.mark.parametrize("live, start, end, expected", [
    (MON, None, None, bv.RangeSpec([MON, TUE, WED, THU], None, MON, False, True)),
    (TUE, date(2026, 10, 1), None, bv.RangeSpec([TUE, WED, THU], None, TUE, True, True)),
    (MON, WED, THU, bv.RangeSpec([WED, THU], TUE, MON, False, False)),
    (MON, MON, WED, bv.RangeSpec([MON, TUE, WED], None, MON, False, False)),
])
def test_clamp_range(live, start, end, expected):
    assert bv.clamp_range([MON, TUE, WED, THU], live, start, end) == expected


def test_clamp_range_with_no_live_book():
    assert bv.clamp_range([], None, None, None) == bv.RangeSpec([], None, None, False, True)


def test_the_all_range_starts_on_the_first_close_and_counts_one_fewer_return():
    series, _, _ = _series(_inputs())
    bot = _pts(series, "bot_account")
    assert [p[0] for p in bot] == ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]
    assert bot[0] == ("2026-11-02", 0.0, None, 1, False)
    assert bot[1] == ("2026-11-03", pytest.approx(1.0), pytest.approx(1.0), 1, False)
    assert bot[2] == ("2026-11-04", None, None, 1, True)                 # missing, never 0 %
    assert bot[3] == ("2026-11-05", pytest.approx(3.02), pytest.approx(2.0), 2, False)
    spy = _pts(series, "SPY")
    assert spy[0][1:3] == (0.0, None)
    assert spy[3][1] == pytest.approx(1.9898)
    assert "2026-11-06" not in [p[0] for p in spy]                       # non-final today stays out


def test_series_metadata_preserves_display_order_and_return_kind():
    series, _, _ = _series(_inputs())
    assert [s["key"] for s in series.values()] == list(bv.SERIES_KEYS)
    assert (series["^DJI"]["label"], series["^DJI"]["total_return"]) == ("Dow (price)", False)
    assert series["QQQ"]["total_return"]
    assert series["bot_deployed"]["kind"] == "bot"


def test_a_range_rebases_on_the_prior_close_and_counts_its_first_return():
    series, _, _ = _series(_inputs(), start=TUE, end=THU)
    assert _pts(series, "bot_account")[:2] == [("2026-11-02", 0.0, None, 1, False),
                                               ("2026-11-03", pytest.approx(1.0), pytest.approx(1.0), 1, False)]
    assert _pts(series, "SPY")[1][2] == pytest.approx(1.0)


def test_a_gap_reaching_before_the_range_counts_no_return():
    series, _, _ = _series(_inputs(), start=THU)
    assert _pts(series, "bot_account") == [("2026-11-04", None, None, 1, True),
                                           ("2026-11-05", 0.0, None, 2, False)]
    assert _pts(series, "SPY") == [("2026-11-04", 0.0, None, 1, False),
                                   ("2026-11-05", pytest.approx(-1.0), pytest.approx(-1.0), 1, False)]


def test_a_base_balance_session_carries_flat_and_gets_a_marker():
    rows = [_row(MON, 15, 55, 10_000.0), _row(TUE, 15, 55, 10_600.0, realized=10_500.0),
            _row(THU, 15, 55, 10_812.0, realized=10_500.0)]
    series, markers, _ = _series(_inputs(rows=rows))
    bot = _pts(series, "bot_account")
    assert bot[1] == ("2026-11-03", 0.0, None, 1, False)
    assert bot[3][1:3] == (pytest.approx(2.0), pytest.approx(2.0))
    assert markers == [{"date": "2026-11-03", "kind": "base_balance"}]


def test_deployed_below_the_floor_carries_flat_and_is_not_missing():
    rows = [_row(MON, 15, 55, 10_000.0, notional=100.0), _row(TUE, 15, 55, 10_100.0, notional=100.0)]
    dep = _pts(_series(_inputs(rows=rows))[0], "bot_deployed")
    assert dep[1] == ("2026-11-03", 0.0, None, 1, False)


def test_deployed_chains_on_its_peak_denominator():
    dep = _pts(_series(_inputs())[0], "bot_deployed")
    assert dep[1][1:3] == (pytest.approx(2.0), pytest.approx(2.0))       # P 100 / D 5 000


def test_exposure_rows_are_percentages_and_missing_is_none():
    _, _, exposure = _series(_inputs())
    assert [e["date"] for e in exposure] == ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]
    assert exposure[0] == {"date": "2026-11-02", "pct": 50.0, "open_n": 1, "approx": False}
    assert exposure[2] == {"date": "2026-11-04", "pct": None, "open_n": 0, "approx": False}


def test_no_live_book_is_empty_points_never_zeros():
    series, markers, exposure = _series(_inputs(rows=[], bars=[], sessions=[]))
    assert all(s["points"] == [] for s in series.values()) and markers == [] and exposure == []


def test_a_provisional_historical_bar_does_not_count():
    partial = _bar("SPY", TUE, 0.1, final=False)
    series, _, _ = _series(_inputs(bars=[*BARS[:1], partial, *BARS[2:]]))
    assert _pts(series, "SPY")[1] == ("2026-11-03", None, None, 1, True)
    assert bv.index_pct([partial], final_only=False)["SPY"][TUE] == (0.1, False)


def test_today_values_are_available_with_an_empty_chart_range():
    inputs = _inputs()
    rng = bv.clamp_range([MON, TUE, WED, THU], MON, FRI, FRI)
    frame = bv.build_frame(inputs, rng)
    assert frame.days == []
    assert frame.closes[FRI] == 10_400.0
    assert frame.exposure[FRI].open_n == 1
    assert FRI in frame.deployed
    assert FRI not in frame.pct["SPY"]
