"""v188: the post-cancel replay (pure).

Reference walk: scripts/reports/autopsy/bars.py (bisect_right strictly past the
exit day). Frames start 2026-07-30: bar 2 is the cancel day 2026-08-03, bar 3
the first walked bar, bar 12 is `until` (2026-08-17) for a 2w plan.
"""
from datetime import date

import pytest

from swingbot.core.analytics import cancel_replay as cr
from tests.helpers import make_ohlcv

FLAT = (100.0, 100.5, 99.5, 100.0)
CANCEL_DAY = date(2026, 8, 3)
UNTIL = date(2026, 8, 17)


def _frame(*walked, pre=(FLAT, FLAT, FLAT), total=14, pad=FLAT):
    """Bars 0-2 (through the cancel day), then `walked` from 2026-08-04, padded to `total`."""
    bars = list(pre) + list(walked)
    bars += [pad] * max(0, total - len(bars))
    return make_ohlcv(bars, start="2026-07-30")


def _long(frame, **kw):
    args = dict(bullish=True, entry=105.0, stop=95.0, tp1=120.0,
                after=CANCEL_DAY, until=UNTIL)
    args.update(kw)
    return cr.replay(frame, **args)


def _short(frame, **kw):
    args = dict(bullish=False, entry=95.0, stop=105.0, tp1=80.0,
                after=CANCEL_DAY, until=UNTIL)
    args.update(kw)
    return cr.replay(frame, **args)


# -- trading date --------------------------------------------------------------

@pytest.mark.parametrize("at, expected", [
    ("2026-08-03T15:00:00+00:00", date(2026, 8, 3)),   # in-session, UTC
    ("2026-08-03T16:00:00-04:00", date(2026, 8, 3)),   # window cancel, ET-aware
    ("2026-08-04T02:00:00", date(2026, 8, 3)),         # naive reads as UTC
    ("2026-08-03T15:00:00Z", date(2026, 8, 3)),
    ("2026-08-03", date(2026, 8, 3)),                  # date only stays that date
])
def test_trading_date(at, expected):
    assert cr.trading_date(at) == expected


def test_utc_after_midnight_maps_to_the_previous_ny_session():
    """Review Focus 1: 01:30 UTC on the 4th is 21:30 New York on the 3rd."""
    assert cr.trading_date("2026-08-04T01:30:00+00:00") == date(2026, 8, 3)


# -- window --------------------------------------------------------------------

def test_window_end_counts_calendar_days_of_the_horizon():
    assert cr.window_end(CANCEL_DAY, "2w") == UNTIL
    assert cr.window_end(CANCEL_DAY, "4w") == date(2026, 8, 31)


def test_unknown_horizon_has_no_window():
    assert cr.window_end(CANCEL_DAY, "9y") is None


def test_last_bar_day():
    assert cr.last_bar_day(_frame()) == date(2026, 8, 18)
    assert cr.last_bar_day(None) is None
    assert cr.last_bar_day(_frame().iloc[0:0]) is None


# -- verdicts, long ------------------------------------------------------------

def test_stop_first_is_a_right_cancel_at_minus_one_r():
    out = _long(_frame((104, 106, 104, 105), (100, 101, 94, 95)))
    assert (out.outcome, out.r, out.tie) == ("right", -1.0, False)
    assert out.touch_day == date(2026, 8, 4)
    assert out.exit_day == date(2026, 8, 5)
    assert out.until == UNTIL and out.elapsed is True


def test_tp1_first_is_a_wrong_cancel_at_full_target_r():
    out = _long(_frame((104, 106, 104, 105), (110, 121, 109, 120)))
    assert out.outcome == "wrong"
    assert out.r == pytest.approx(1.5)          # |120 - 105| / |105 - 95|
    assert out.exit_day == date(2026, 8, 5)


def test_same_bar_stop_and_tp1_counts_as_the_stop_and_is_a_tie():
    out = _long(_frame((104, 106, 104, 105), (105, 121, 94, 100)))
    assert (out.outcome, out.r, out.tie) == ("right", -1.0, True)


def test_the_touch_bar_itself_is_checked_stop_first():
    out = _long(_frame((100, 106, 94, 96)))     # touches 105 and 95 on one bar
    assert (out.outcome, out.tie) == ("right", False)
    assert out.touch_day == out.exit_day == date(2026, 8, 4)


def test_no_touch_in_an_elapsed_window_is_untriggered_after_cancel():
    out = _long(_frame())
    assert (out.outcome, out.r, out.touch_day) == ("untriggered_after_cancel", None, None)
    assert out.elapsed is True


def test_the_cancel_day_bar_is_never_walked():
    """No-lookahead: a cancel-day bar through trigger, stop and TP1 decides nothing."""
    out = _long(_frame(pre=(FLAT, FLAT, (100, 125, 90, 110))))
    assert out.outcome == "untriggered_after_cancel"


def test_a_bar_on_until_counts():
    walked = [FLAT] * 9 + [(104, 121, 104, 120)]   # bar 12 = 2026-08-17
    out = _long(_frame(*walked))
    assert (out.outcome, out.exit_day) == ("wrong", UNTIL)


def test_a_bar_after_until_never_counts():
    walked = [FLAT] * 10 + [(104, 121, 104, 120)]  # bar 13 = 2026-08-18
    out = _long(_frame(*walked))
    assert out.outcome == "untriggered_after_cancel"


def test_touched_without_exit_in_an_elapsed_window_is_marked_to_the_last_close():
    walked = [(104, 106, 104, 105)] + [(105, 108, 104, 106)] * 8 + [(106, 108, 105, 107)]
    out = _long(_frame(*walked))                   # last walked bar = 2026-08-17, close 107
    assert out.outcome == "unresolved"
    assert out.r == pytest.approx(0.2)             # (107 - 105) / 10
    assert out.elapsed is True and out.exit_day is None


def test_a_window_not_yet_over_is_unresolved_even_untouched():
    out = _long(_frame(total=8))                   # last bar 2026-08-10 < until
    assert (out.outcome, out.r, out.elapsed) == ("unresolved", None, False)


def test_a_window_not_yet_over_touched_is_marked_to_market():
    out = _long(_frame((104, 106, 104, 105), (105, 110, 104, 109), total=8))
    assert out.outcome == "unresolved"
    assert out.r == pytest.approx((100.0 - 105.0) / 10.0)   # last walked close is the flat pad
    assert out.elapsed is False


def test_no_bar_after_the_cancel_day_is_unresolved():
    out = _long(_frame(total=3))
    assert (out.outcome, out.r, out.touch_day, out.elapsed) == ("unresolved", None, None, False)


# -- verdicts, short (mirrored) ------------------------------------------------

def test_short_stop_first_is_right():
    out = _short(_frame((96, 96, 94, 95), (100, 106, 99, 104)))
    assert (out.outcome, out.r) == ("right", -1.0)


def test_short_tp1_first_is_wrong_at_full_target_r():
    out = _short(_frame((96, 96, 94, 95), (90, 91, 79, 80)))
    assert out.outcome == "wrong"
    assert out.r == pytest.approx(1.5)


def test_short_same_bar_tie_counts_as_the_stop():
    out = _short(_frame((96, 96, 94, 95), (95, 106, 79, 90)))
    assert (out.outcome, out.tie) == ("right", True)


def test_short_flat_window_is_untriggered():
    assert _short(_frame()).outcome == "untriggered_after_cancel"


def test_short_unresolved_is_marked_mirrored():
    walked = [(96, 96, 94, 95)] + [(94, 96, 92, 93)] * 9   # last close 93
    out = _short(_frame(*walked))
    assert out.outcome == "unresolved"
    assert out.r == pytest.approx(0.2)                     # (95 - 93) / 10


# -- the baseline walk ---------------------------------------------------------

def test_without_a_touch_requirement_the_walk_starts_on_the_first_bar():
    out = _long(_frame((100, 101, 94, 95)), require_touch=False)
    assert (out.outcome, out.touch_day) == ("right", date(2026, 8, 4))


def test_without_a_touch_requirement_a_flat_window_is_unresolved():
    out = _long(_frame(), require_touch=False)
    assert out.outcome == "unresolved"
    assert out.r == pytest.approx(-0.5)                    # (100 - 105) / 10


# -- split guard ---------------------------------------------------------------

def test_split_guard_passes_a_close_near_the_level():
    assert cr.split_guard_ok(_frame(), CANCEL_DAY, 105.0) is True   # |100-105|/105 = 4.8%


def test_split_guard_fails_an_adjusted_close_far_from_the_level():
    """Review Focus 2: a 2:1 split adjusts history to 50 against a raw 105 level."""
    halved = (50.0, 50.25, 49.75, 50.0)
    assert cr.split_guard_ok(_frame(pre=(halved,) * 3), CANCEL_DAY, 105.0) is False


def test_split_guard_reads_the_last_close_on_or_before_the_day():
    frame = _frame(pre=(FLAT, FLAT, (100, 131, 99, 130)))   # cancel-day close 130
    assert cr.split_guard_ok(frame, CANCEL_DAY, 105.0) is True    # 23.8%
    assert cr.split_guard_ok(frame, date(2026, 7, 31), 140.0) is False  # 7/31 close 100: 28.6%


def test_split_guard_fails_with_no_bar_on_or_before_the_day():
    assert cr.split_guard_ok(_frame(), date(2026, 7, 1), 105.0) is False


def test_constants():
    assert cr.OUTCOMES == ("right", "wrong", "unresolved", "untriggered_after_cancel")
    assert cr.SPLIT_GUARD == 0.25
