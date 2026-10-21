"""v173 §3: replay_override -- the actual exit price and the eight statuses.

Frames sit on real NYSE sessions from 2026-09-14: 15 warm-up bars, the fill
bar at index 15 (Mon 2026-10-05), the override session at index 17 (Wed
2026-10-07). Bullish plans enter at 100 with the stop at 95 and TP1 at 110;
the breakeven trigger is 105; the hold cap is 8 bars, so a full 26-bar frame
(last bar Mon 2026-10-19) times out at index 23. Expected R figures are booked
here through the same costs.book call, so the tests pin the wiring, not the
engine's arithmetic (V173-8's arms tests pin that).
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.backtesting.instrument import costs
from swingbot.core.market.session import nyse_calendar
from swingbot.core.planning.exit_sim import runner_floor
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

START = date(2026, 9, 14)
FILL_IDX, OV_IDX = 15, 17
FILL_AT = "2026-10-05T14:00:00+00:00"      # Mon 10:00 ET -> index 15
PARTIAL_AT = "2026-10-06T15:00:00+00:00"   # Tue 11:00 ET -> index 16
CLOSE_AT = "2026-10-07T18:00:00+00:00"     # Wed 14:00 ET -> index 17
CLOSE_DAY = date(2026, 10, 7)
LAST_DAY = date(2026, 10, 19)              # index 25 of a full frame
WARM = (100.0, 100.5, 99.5, 100.0)
FILL_BAR = (100.0, 101.0, 99.0, 100.0)
FLAT = (101.0, 102.0, 100.0, 101.0)        # below the 105 breakeven trigger
TP1_BAR = (104.0, 111.0, 103.0, 108.0)
RUNNER_HOLD = (108.0, 108.5, 107.0, 107.5)  # above the runner floor
STOP_BAR = (101.0, 102.0, 94.0, 95.0)
FLOOR = runner_floor(100.0, 110.0)           # 106.667
_STAMPED = object()
UNSTAMPED = object()                          # no `override` key: a pre-v173 close
NO_FIGURES = ("engine_r", "delta_r", "delta_r_gross", "engine_usd", "delta_usd",
              "engine_exit_reason", "outcome")


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    """Code defaults, with the exit flags that would add paths held off."""
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)


def stamp(price=102.0, source="quote", bars_asof="2026-10-06"):
    return {"exit_price": price, "price_source": source,
            "quote_ts": CLOSE_AT if source == "quote" else None, "bars_asof": bars_asof}


def plan(*, partial=False, reason="manual", override=_STAMPED, fill_at=FILL_AT,
         partial_at=PARTIAL_AT, close_at=CLOSE_AT, **kw) -> TradePlanV2:
    history = [] if fill_at is None else [
        {"status": "ACTIVE", "reason": "filled", "at": fill_at}]
    legs = []
    if partial:
        history.append({"status": "PARTIAL", "reason": "tp1_partial", "at": partial_at})
        legs = [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1",
                 "closed_at": partial_at}]
    closed = {"status": "CLOSED", "reason": reason, "at": close_at}
    if override is _STAMPED:
        closed["override"] = stamp(107.5 if partial else 102.0)
    elif override is not UNSTAMPED:
        closed["override"] = override
    history.append(closed)
    base = dict(plan_id="p1", ticker="T", created_at="2026-10-02", source="strategy",
                strategy="Probe", horizon_key="2w", direction="bullish",
                entry_type="market", trigger_price=100.0, entry_price=100.0,
                expiry_bars=3, stop_loss=95.0, tp1=110.0,
                tp1_fraction=0.5 if partial else 1.0, tp2=None,
                breakeven_trigger_fraction=0.5, trail_atr_mult=5.0, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.CLOSED, status_history=history, legs_realized=legs,
                hold_cap_bars=8)
    base.update(kw)
    return TradePlanV2(**base)


def frame(rows: dict | None = None, *, n: int = 26) -> pd.DataFrame:
    bars = [WARM] * FILL_IDX + [FILL_BAR] + [FLAT] * (n - FILL_IDX - 1)
    for i, bar in (rows or {}).items():
        bars[i] = bar
    days = nyse_calendar().sessions(START, START + timedelta(days=3 * n))[:n]
    return pd.DataFrame([(*bar, 1_000_000.0) for bar in bars],
                        columns=["Open", "High", "Low", "Close", "Volume"],
                        index=pd.DatetimeIndex(days))


def partial_frame(rows: dict | None = None, *, n: int = 26) -> pd.DataFrame:
    return frame({16: TP1_BAR, 17: RUNNER_HOLD, **(rows or {})}, n=n)


def book(*legs, model=None) -> float:
    """costs.book over (fraction, exit_price, kind) legs, the plan's entry and stop."""
    return costs.book(model or of.INSTRUMENT.cost_model, direction="bullish",
                      entry_price=100.0, stop_loss=95.0,
                      legs=[{"fraction": f, "exit_price": p, "reason": "x", "kind": k}
                            for f, p, k in legs])[0]


def replay(p, df, *, when=None, trade=None):
    return of.replay_override(p, df, when or df.index[-1].date(), trade)


def no_figures(row) -> bool:
    return all(getattr(row, name) is None for name in NO_FIGURES)


# -- the frame itself --------------------------------------------------------

def test_the_frame_sits_on_the_sessions_the_docstring_names():
    df = frame()
    assert [df.index[i].date() for i in (FILL_IDX, 16, OV_IDX, 19, 20, 25)] == [
        date(2026, 10, 5), date(2026, 10, 6), CLOSE_DAY, date(2026, 10, 9),
        date(2026, 10, 12), LAST_DAY]


# -- resolved exit paths -----------------------------------------------------

def test_hold_cap_timeout_is_resolved_not_open():
    row = replay(plan(), frame())
    assert (row.status, row.engine_exit_reason) == ("resolved", "timeout")
    assert row.engine_r == pytest.approx(book((1.0, 101.0, "close")), abs=1e-3)
    assert row.actual_r == pytest.approx(book((1.0, 102.0, "stop")), abs=1e-3)
    assert row.delta_r == round(row.actual_r - row.engine_r, 3)
    assert row.outcome == of.outcome_of(row.delta_r)
    assert (row.approx, row.price_source, row.bulk, row.source) == (False, "quote", False, "manual")
    assert (row.state_at_close, row.horizon, row.direction, row.ticker) == (
        "ACTIVE", "2w", "bullish", "T")
    assert row.close_date == CLOSE_DAY


def test_delta_before_costs_is_the_same_two_arms_on_the_gross_model():
    """Manual 102 (stop kind) vs the engine's 101 timeout close: 1 point on a
    5-point risk is +0.2R before costs, whatever the cost model charges."""
    row = replay(plan(), frame())
    assert row.delta_r_gross == pytest.approx(0.2, abs=1e-9)
    gross = (book((1.0, 102.0, "stop"), model=of.GROSS_COST_MODEL)
             - book((1.0, 101.0, "close"), model=of.GROSS_COST_MODEL))
    assert row.delta_r_gross == round(gross, 3)
    assert row.delta_r_gross > row.delta_r       # the manual leg pays more slippage


def test_engine_stop_after_the_override_is_resolved():
    row = replay(plan(), frame({19: STOP_BAR}))
    assert (row.status, row.engine_exit_reason) == ("resolved", "stop")
    assert row.engine_r == pytest.approx(book((1.0, 95.0, "stop")), abs=1e-3)


def test_runner_stop_at_the_floor():
    row = replay(plan(partial=True), partial_frame({18: (107.0, 107.5, 106.0, 106.5)}))
    assert (row.status, row.engine_exit_reason, row.state_at_close) == (
        "resolved", "runner_be", "PARTIAL")
    assert row.engine_r == pytest.approx(
        book((0.5, 110.0, "target"), (0.5, FLOOR, "stop")), abs=1e-3)
    assert row.actual_r == pytest.approx(
        book((0.5, 110.0, "target"), (0.5, 107.5, "stop")), abs=1e-3)


def test_runner_tp2():
    row = replay(plan(partial=True, tp2=115.0),
                 partial_frame({18: (109.0, 116.0, 108.5, 114.0)}))
    assert (row.status, row.engine_exit_reason) == ("resolved", "runner_tp2")
    assert row.engine_r == pytest.approx(
        book((0.5, 110.0, "target"), (0.5, 115.0, "target")), abs=1e-3)


TRAIL_ROWS = {17: (109.0, 112.0, 108.5, 111.5), 18: (112.0, 118.0, 111.5, 117.5),
              19: (118.0, 124.0, 117.5, 123.5), 20: (123.0, 123.5, 100.0, 101.0)}


def test_runner_trail_reads_the_real_frames_atr():
    """The engine frame clamps the override bar for the exit checks only;
    ATR comes from the real frame (indicator_df), so the trail equals the
    real-frame walk's: 3.035 when this plan was written (it was 3.038 while
    the clamped bar also fed the ATR)."""
    p = plan(partial=True, trail_atr_mult=1.0, override=stamp(111.0))
    df = partial_frame(TRAIL_ROWS)
    row = replay(p, df)
    assert (row.status, row.engine_exit_reason) == ("resolved", "runner_trail")
    real = of.engine_path(p, df, FILL_IDX)
    assert row.engine_r == of.engine_r(p, real, "PARTIAL")
    assert row.engine_r == pytest.approx(3.035, abs=0.002)


# -- open, stale -------------------------------------------------------------

def test_data_ending_before_the_hold_cap_is_open():
    row = replay(plan(), frame(n=22))     # walk_v2 clips at index 21, 15 + 8 > 21
    assert row.status == "open"
    assert no_figures(row)
    assert row.actual_r == pytest.approx(book((1.0, 102.0, "stop")), abs=1e-3)


def test_a_cache_ending_before_asof_is_stale():
    assert replay(plan(), frame(), when=date(2026, 10, 20)).status == "stale"
    assert replay(plan(), frame(), when=LAST_DAY).status == "resolved"


# -- ambiguous ---------------------------------------------------------------

@pytest.mark.parametrize("p, df", [
    pytest.param(plan(), frame({OV_IDX: (101.0, 102.0, 94.0, 101.0)}), id="active-stop-wick"),
    pytest.param(plan(), frame({OV_IDX: (101.0, 111.0, 100.0, 101.0)}), id="active-tp1-wick"),
    pytest.param(plan(partial=True), partial_frame({OV_IDX: (108.0, 108.5, 106.0, 107.5)}),
                 id="partial-floor-wick"),
    pytest.param(plan(partial=True, partial_at=CLOSE_AT),
                 frame({OV_IDX: TP1_BAR, 18: RUNNER_HOLD}), id="partial-tp1-same-session"),
])
def test_override_session_touching_a_level_is_ambiguous(p, df):
    row = replay(p, df)
    assert row.status == "ambiguous"
    assert no_figures(row)


# -- parity_mismatch ---------------------------------------------------------

@pytest.mark.parametrize("p, df", [
    pytest.param(plan(), frame({FILL_IDX: (100.0, 101.0, 94.0, 100.0)}), id="fill-bar-stop"),
    pytest.param(plan(), frame({16: STOP_BAR}), id="active-early-stop"),
    pytest.param(plan(tp1_fraction=0.5), frame({16: TP1_BAR, OV_IDX: RUNNER_HOLD}),
                 id="active-but-replay-took-tp1-first"),
    pytest.param(plan(partial=True, partial_at="2026-10-08T15:00:00+00:00",
                      close_at="2026-10-09T18:00:00+00:00"),
                 partial_frame({18: RUNNER_HOLD, 19: RUNNER_HOLD}),
                 id="partial-replay-tp1-earlier-than-live"),
    pytest.param(plan(partial=True), frame(), id="partial-replay-never-reaches-tp1"),
])
def test_replay_disagreeing_with_the_live_path_is_parity_mismatch(p, df):
    row = replay(p, df)
    assert row.status == "parity_mismatch"
    assert no_figures(row)


# -- split_affected (the price band; V173-22 adds the adjustment seam) --------

def test_entry_outside_the_fill_bar_is_split_affected():
    assert replay(plan(), frame({FILL_IDX: (50.0, 50.5, 49.5, 50.0)})).status == "split_affected"


def test_entry_inside_the_two_percent_tolerance_is_not_split_affected():
    # 98.1 * 1.02 = 100.062 >= 100
    assert replay(plan(), frame({FILL_IDX: (98.0, 98.1, 97.5, 98.0)})).status == "resolved"


# -- unstamped ---------------------------------------------------------------

@pytest.mark.parametrize("override", [None, stamp(None, "none", None)],
                         ids=["override-null", "price-source-none"])
def test_a_failed_stamp_on_an_individual_close_is_unstamped(override):
    row = replay(plan(override=override), frame(), trade={"id": "t1", "shares": 10})
    assert row.status == "unstamped"
    assert (row.approx, row.price_source, row.bulk) == (False, "none", False)
    assert row.actual_r is None and row.actual_usd is None
    assert no_figures(row)
    assert row.close_date == CLOSE_DAY


@pytest.mark.parametrize("p, bars", [
    pytest.param(plan(override=None), None, id="no-bars"),
    pytest.param(plan(override=None, fill_at=None), frame(), id="no-active-entry"),
    pytest.param(plan(override=None, entry_price=None), frame(), id="no-entry-price"),
])
def test_unstamped_beats_unreplayable(p, bars):
    assert of.replay_override(p, bars, LAST_DAY).status == "unstamped"


@pytest.mark.parametrize("override", [None, stamp(None, "none", None)],
                         ids=["override-null", "price-source-none"])
def test_a_failed_stamp_on_a_bulk_close_is_priced_from_the_session_bar(override):
    row = replay(plan(reason="manual_bulk", override=override), frame())
    assert (row.status, row.bulk, row.approx, row.price_source) == (
        "resolved", True, True, "session_close")
    assert row.actual_r == pytest.approx(book((1.0, 101.0, "stop")), abs=1e-3)


# -- unreplayable and precedence ---------------------------------------------

_FULL = frame()


@pytest.mark.parametrize("p, bars", [
    pytest.param(plan(fill_at=None), _FULL, id="no-active-entry"),
    pytest.param(plan(), None, id="no-bars"),
    pytest.param(plan(), _FULL.iloc[0:0], id="empty-bars"),
    pytest.param(plan(), _FULL.iloc[16:], id="fill-session-not-in-bars"),
    pytest.param(plan(entry_price=None), _FULL, id="no-entry-price"),
    pytest.param(plan(reason="tp1_runner_trail"), _FULL, id="not-a-manual-close"),
    pytest.param(plan(close_at="not-a-time"), _FULL, id="unreadable-close-time"),
    pytest.param(plan(override=UNSTAMPED), _FULL.drop(_FULL.index[OV_IDX]),
                 id="pre-v173-override-session-missing"),
    pytest.param(plan(stop_loss=101.0), _FULL, id="costs-book-refuses"),
])
def test_rows_the_replay_cannot_place_are_unreplayable(p, bars):
    row = of.replay_override(p, bars, LAST_DAY)
    assert row.status == "unreplayable"
    assert no_figures(row)
    assert row.source == "manual"


def test_unreplayable_beats_stale_and_stale_beats_split():
    assert of.replay_override(plan(fill_at=None), _FULL, date(2026, 10, 20)).status == "unreplayable"
    split = frame({FILL_IDX: (50.0, 50.5, 49.5, 50.0)})
    assert of.replay_override(plan(), split, date(2026, 10, 20)).status == "stale"


# -- no lookahead --------------------------------------------------------------

@pytest.mark.parametrize("p, rows", [
    pytest.param(plan(), {19: STOP_BAR}, id="stop-path"),
    pytest.param(plan(), {}, id="hold-cap-timeout-path"),
    pytest.param(plan(), {18: (101.0, 111.0, 100.0, 108.0)}, id="single-leg-tp1-path"),
])
def test_bars_before_the_fill_never_change_engine_r(p, rows):
    """Pinned on single-leg (tp1_fraction 1.0) plans only, as V173-8 does. A
    runner's trailing stop reads ATR(14), which looks back up to 13 sessions
    before the fill, exactly as the live trail did: past data, not lookahead,
    so a runner plan's engine_r may legitimately move here."""
    base = replay(p, frame(rows))
    moved = frame(rows)
    moved.iloc[0] = (90.0, 91.0, 89.0, 90.0, 1_000_000.0)
    moved.iloc[5] = (100.0, 130.0, 70.0, 100.0, 1_000_000.0)
    again = replay(p, moved)
    assert base.status == again.status == "resolved"
    assert again.engine_r == base.engine_r


def test_override_bar_range_never_moves_a_pre_tp1_engine_r():
    """Pre-TP1 the walk reads no indicator, so the clamped override bar is all
    the engine arm sees of that session: a quieter or wider range touching no
    level leaves engine_r alone, a range touching the stop flips the row to
    ambiguous. (A runner plan reads the real bar's range through ATR on later
    bars, as it did live: decision 6.)"""
    quiet, touching = (101.0, 104.0, 96.0, 101.0), (101.0, 102.0, 94.0, 101.0)
    base = replay(plan(), frame())
    other = replay(plan(), frame({OV_IDX: quiet}))
    flipped = replay(plan(), frame({OV_IDX: touching}))
    assert base.status == other.status == "resolved"
    assert other.engine_r == base.engine_r
    assert flipped.status == "ambiguous"


# -- cost parity, dollars, bulk ----------------------------------------------

def test_same_exit_price_and_kind_as_the_engine_gives_zero_delta():
    """Same price, both legs of kind stop. On the override session itself the
    row would be ambiguous by design, so the engine's stop sits two sessions on."""
    row = replay(plan(override=stamp(95.0)), frame({19: STOP_BAR}))
    assert row.status == "resolved"
    assert row.delta_r == 0.0
    assert row.delta_r_gross == 0.0
    assert row.outcome == "neutral"


def test_dollars_come_from_the_linked_trades_shares():
    row = replay(plan(), frame({19: STOP_BAR}), trade={"id": "t1", "shares": 10})
    risk = 10 * abs(100.0 - 95.0)
    assert row.actual_usd == round(row.actual_r * risk, 2)
    assert row.engine_usd == round(row.engine_r * risk, 2)
    assert row.delta_usd == round(row.delta_r * risk, 2)


@pytest.mark.parametrize("trade", [None, {"id": "t1"}, {"id": "t1", "shares": None}])
def test_no_linked_shares_means_no_dollars_but_r_stays(trade):
    row = replay(plan(), frame({19: STOP_BAR}), trade=trade)
    assert (row.actual_usd, row.engine_usd, row.delta_usd) == (None, None, None)
    assert row.delta_r is not None


def test_a_bulk_close_is_replayed_and_flagged():
    row = replay(plan(reason="manual_bulk"), frame())
    assert (row.bulk, row.status) == (True, "resolved")


# -- the actual exit price (spec §3 session table, stamp kinds) ---------------

def _priced() -> pd.DataFrame:
    df = frame()
    df["Open"] = [200.0 + i for i in range(len(df))]
    df["Close"] = [300.0 + i for i in range(len(df))]
    return df


@pytest.mark.parametrize("at, expected", [
    pytest.param("2026-10-07T12:00:00+00:00", (217.0, "session_open"), id="before-open"),
    pytest.param("2026-10-07T13:30:00+00:00", (317.0, "session_close"), id="at-the-open"),
    pytest.param("2026-10-07T18:00:00+00:00", (317.0, "session_close"), id="regular-hours"),
    pytest.param("2026-10-07T21:30:00+00:00", (317.0, "session_close"), id="after-close"),
    pytest.param("2026-10-08T02:00:00+00:00", (317.0, "session_close"), id="utc-next-day"),
    pytest.param("2026-10-10T15:00:00+00:00", (319.0, "session_close"), id="saturday"),
    pytest.param("2026-10-12T03:00:00+00:00", (319.0, "session_close"), id="sunday-night-et"),
])
def test_a_pre_v173_exit_price_follows_the_session_table(at, expected):
    p = plan(override=UNSTAMPED, close_at=at)
    assert of.actual_exit(p, _priced(), of.assign_session(at)) == (*expected, True)


def test_a_quote_stamp_wins_and_is_never_approx():
    hit = of.assign_session(CLOSE_AT)
    assert of.actual_exit(plan(), _priced(), hit) == (102.0, "quote", False)
    old_cache = plan(override=stamp(102.0, "quote", "2026-09-01"))
    assert of.actual_exit(old_cache, _priced(), hit) == (102.0, "quote", False)


@pytest.mark.parametrize("bars_asof, approx", [
    pytest.param("2026-10-07", False, id="cache-at-the-close-session"),
    pytest.param("2026-10-08", False, id="cache-after-the-close-session"),
    pytest.param("2026-10-06", True, id="cache-a-session-old"),
    pytest.param(None, True, id="cache-date-unknown"),
])
def test_a_bar_close_stamp_older_than_the_close_session_is_approx(bars_asof, approx):
    hit = of.assign_session(CLOSE_AT)
    p = plan(override=stamp(101.5, "bar_close", bars_asof))
    assert of.actual_exit(p, _priced(), hit) == (101.5, "bar_close", approx)


def test_an_approx_bar_close_row_keeps_the_stamp_price():
    row = replay(plan(override=stamp(101.5, "bar_close", "2026-10-06")), frame())
    assert (row.status, row.approx, row.price_source) == ("resolved", True, "bar_close")
    assert row.actual_r == pytest.approx(book((1.0, 101.5, "stop")), abs=1e-3)


def test_a_pre_v173_row_is_approx_from_the_session_bar():
    row = replay(plan(override=UNSTAMPED), frame())
    assert (row.approx, row.price_source, row.status) == (True, "session_close", "resolved")
    assert row.actual_r == pytest.approx(book((1.0, 101.0, "stop")), abs=1e-3)


def test_no_bar_for_the_override_session_gives_no_price():
    df = _priced().drop(_priced().index[OV_IDX])
    assert of.actual_exit(plan(override=UNSTAMPED), df, of.assign_session(CLOSE_AT)) == (
        None, "none", True)


def test_an_unreplayable_row_keeps_its_stamp_fields():
    stamped = of.replay_override(plan(fill_at=None), _FULL, LAST_DAY)
    assert (stamped.status, stamped.approx, stamped.price_source) == (
        "unreplayable", False, "quote")
    old = of.replay_override(plan(fill_at=None, override=UNSTAMPED), _FULL, LAST_DAY)
    assert (old.status, old.approx, old.price_source) == ("unreplayable", True, "none")
