"""v209 shock.step: SHOCK -> RECOVERY -> NORMAL, second leg, overnight carry."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot.core.market import shock
from swingbot.core.market.shock import (NameRow, ShockReading, ShockSnapshot, ShockState,
                                        ShockThresholds, VixTape, measure, recovery_condition,
                                        reentry_condition, step)

UTC = timezone.utc
T0 = datetime(2026, 11, 5, 15, 30, tzinfo=UTC)          # 10:30 ET, 60 min after the open
D0 = date(2026, 11, 5)
D1 = date(2026, 11, 6)
OPEN_D1 = datetime(2026, 11, 6, 14, 30, tzinfo=UTC)      # 09:30 ET
TH = ShockThresholds()
REPAIRED = dict(breadth_frac=0.20, vix_off_high_pct=5.0, spy_retrace=0.5)


def _reading(at=0, **over):
    base = dict(
        as_of=T0 + timedelta(minutes=at), session_date=D0, minutes_since_open=60.0 + at,
        breadth_frac=0.05, sectors_down=0, sectors_total=5, depth_frac=0.0,
        breadth_speed=None,
        spy_atr_move=0.0, qqq_atr_move=None, spy_last=500.0, spy_prev_close=500.0,
        spy_session_low=500.0, spy_new_low=False, spy_retrace=1.0, vix_level=16.0,
        vix_chg_pct=0.0, vix_session_high=16.0, vix_off_high_pct=0.0, n_names=30,
        insufficient=False)
    base.update(over)
    return ShockReading(**base)


def _day1(minutes, **over):
    """A reading `minutes` after the 2026-11-06 open."""
    return _reading(as_of=OPEN_D1 + timedelta(minutes=minutes), session_date=D1,
                    minutes_since_open=float(minutes), **over)


def _shock(since=T0, **over):
    return ShockState(**{"label": "SHOCK", "since": since, "session_date": D0,
                         "vix_session_high": 25.0, "spy_prev_close": 500.0, **over})


def _recovery(since=T0, **over):
    return ShockState(**{"label": "RECOVERY", "since": since, "session_date": D0,
                         "vix_session_high": 25.0, "spy_prev_close": 500.0,
                         "hold_since": since, "prev_breadth": 0.20, **over})


def test_rules_are_complete():
    assert shock.RULES["SHOCK"] is shock._from_shock
    assert shock.RULES["RECOVERY"] is shock._from_recovery


def test_shock_to_recovery_once_dwelled_and_repaired():
    after = step(_shock(), _reading(45, **REPAIRED), TH)
    assert after.label == "RECOVERY"
    assert after.since == after.hold_since == T0 + timedelta(minutes=45)


def test_shock_holds_before_the_minimum_dwell():
    assert step(_shock(), _reading(44, **REPAIRED), TH).label == "SHOCK"


@pytest.mark.parametrize("over", [
    dict(breadth_frac=0.21),
    dict(vix_off_high_pct=4.9),
    dict(spy_retrace=0.49),
    dict(spy_retrace=None, spy_last=None, spy_prev_close=None, spy_session_low=None),  # no SPY frame
    dict(vix_level=None, vix_chg_pct=None, vix_session_high=None, vix_off_high_pct=None),
], ids=["breadth", "vix-off-high", "spy-retrace", "no-spy", "no-vix"])
def test_each_unmet_clause_keeps_shock(over):
    reading = _reading(60, **dict(REPAIRED, **over))
    assert recovery_condition(_shock(), reading, TH) is False
    assert step(_shock(), reading, TH).label == "SHOCK"


def test_vix_below_its_prior_close_satisfies_the_vix_clause():
    reading = _reading(60, **dict(REPAIRED, vix_off_high_pct=0.0, vix_chg_pct=-0.5))
    assert step(_shock(), reading, TH).label == "RECOVERY"


def test_hysteresis_band_holds_shock():
    after = step(_shock(), _reading(90, **dict(REPAIRED, breadth_frac=0.30)), TH)
    assert after.label == "SHOCK" and after.since == T0


def test_recovery_to_normal_after_the_hold():
    state = step(_recovery(), _reading(15, **REPAIRED), TH)
    assert state.label == "RECOVERY" and state.hold_since == T0
    state = step(state, _reading(30, **REPAIRED), TH)
    assert state.label == "NORMAL" and state.since == T0 + timedelta(minutes=30)
    assert state.hold_since is None and state.entry_streak == 0


def test_a_failing_reading_restarts_the_hold_without_leaving_recovery():
    state = step(_recovery(), _reading(15, breadth_frac=0.25), TH)
    assert state.label == "RECOVERY" and state.hold_since is None
    state = step(state, _reading(30, **REPAIRED), TH)
    assert state.hold_since == T0 + timedelta(minutes=30)
    assert step(state, _reading(59, **REPAIRED), TH).label == "RECOVERY"
    assert step(state, _reading(60, **REPAIRED), TH).label == "NORMAL"


@pytest.mark.parametrize("prev, breadth, expected", [
    (0.25, 0.30, True),
    (0.31, 0.30, False),        # falling
    (0.30, 0.30, False),        # flat is not rising
    (None, 0.40, False),        # no earlier reading this session
    (0.20, 0.29, False),        # rising but under the re-entry bar
])
def test_reentry_on_rising_breadth(prev, breadth, expected):
    state = _recovery(prev_breadth=prev)
    reading = _reading(15, breadth_frac=breadth)
    assert reentry_condition(state, reading, TH) is expected
    after = step(state, reading, TH)
    assert after.label == ("SHOCK" if expected else "RECOVERY")
    if expected:
        assert after.since == reading.as_of and after.hold_since is None


def test_reentry_on_a_new_spy_session_low_needs_one_settled_reading():
    assert step(_recovery(), _reading(15, spy_new_low=True), TH).label == "SHOCK"
    early = _reading(15, spy_new_low=True, minutes_since_open=10.0)
    assert reentry_condition(_recovery(), early, TH) is False
    assert step(_recovery(), early, TH).label == "RECOVERY"


def test_overnight_gap_up_repair_reaches_recovery_on_the_first_reading():
    yesterday_close = datetime(2026, 11, 5, 20, 0, tzinfo=UTC)
    first = _day1(1, **dict(REPAIRED, breadth_frac=0.05, vix_off_high_pct=0.0, vix_chg_pct=-3.0,
                            spy_retrace=1.0, spy_prev_close=498.0))
    after = step(_shock(since=yesterday_close), first, TH)
    assert after.label == "RECOVERY" and after.session_date == D1
    assert after.spy_prev_close == 498.0


def test_overnight_second_leg_down_stays_shock():
    first = _day1(20, breadth_frac=0.45, sectors_down=4, depth_frac=0.6, spy_retrace=0.2, spy_prev_close=490.0)
    after = step(_shock(since=datetime(2026, 11, 5, 19, 0, tzinfo=UTC)), first, TH)
    assert after.label == "SHOCK" and after.session_date == D1
    assert after.spy_prev_close == 490.0


def test_overnight_recovery_hold_restarts_with_the_session():
    late = datetime(2026, 11, 5, 20, 50, tzinfo=UTC)
    after = step(_recovery(since=late), _day1(20, **REPAIRED), TH)
    assert after.label == "RECOVERY" and after.hold_since == OPEN_D1 + timedelta(minutes=20)


def test_rising_breadth_is_judged_within_the_session_only():
    state = step(_recovery(prev_breadth=0.20), _day1(30, breadth_frac=0.35), TH)
    assert state.label == "RECOVERY" and state.prev_breadth == 0.35
    assert step(state, _day1(45, breadth_frac=0.36), TH).label == "SHOCK"


def test_an_insufficient_reading_holds_shock_and_recovery():
    thin = _reading(60, **dict(REPAIRED, insufficient=True, n_names=4))
    for state in (_shock(), _recovery()):
        assert step(state, thin, TH) is state


def _snap(at, session, minutes, spy_last, spy_prev, vix):
    names = tuple(NameRow(f"F{i}", "Flat", 100.0, 100.0, 2.0, True) for i in range(20))
    return ShockSnapshot(at, session, minutes, names,
                         NameRow("SPY", None, spy_last, spy_prev, 5.0, False), None, vix)


def test_first_reading_of_a_new_session_through_measure_and_step():
    y_at = datetime(2026, 11, 5, 19, 0, tzinfo=UTC)
    yesterday = measure(_snap(y_at, D0, 270.0, 480.0, 500.0, VixTape(30.0, 40.0, y_at)), None, TH)
    t_at = OPEN_D1 + timedelta(minutes=5)
    today = measure(_snap(t_at, D1, 5.0, 505.0, 498.0, VixTape(18.0, -8.0, t_at)), yesterday, TH)
    assert today.breadth_speed is None
    assert today.vix_session_high == 18.0 and today.spy_prev_close == 498.0
    assert today.spy_session_low == 505.0 and today.spy_new_low is False
    assert step(_shock(since=y_at), today, TH).label == "RECOVERY"


def test_a_full_cycle_normal_shock_recovery_normal():
    depth = dict(breadth_frac=0.45, sectors_down=4, sectors_total=5, depth_frac=0.6)
    state = ShockState()
    for at, over in [(0, depth), (15, depth), (60, REPAIRED), (75, REPAIRED), (90, REPAIRED)]:
        state = step(state, _reading(at, **over), TH)
    assert state.label == "NORMAL" and state.since == T0 + timedelta(minutes=90)
