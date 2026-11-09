"""v209 shock.step: NORMAL -> SHOCK entry rules (spec § State machine)."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot.core.market import shock
from swingbot.core.market.shock import (LABELS, ShockReading, ShockState, ShockThresholds,
                                        entry_condition, step)

UTC = timezone.utc
T0 = datetime(2026, 11, 5, 15, 30, tzinfo=UTC)          # 10:30 ET, 60 min after the open
D0 = date(2026, 11, 5)
TH = ShockThresholds()


def _reading(at=0, **over):
    """A calm, sufficient reading `at` minutes after T0; override any field."""
    base = dict(
        as_of=T0 + timedelta(minutes=at), session_date=D0, minutes_since_open=60.0 + at,
        breadth_frac=0.05, sectors_down=0, sectors_total=5, breadth_speed=None,
        spy_atr_move=0.0, qqq_atr_move=None, spy_last=500.0, spy_prev_close=500.0,
        spy_session_low=500.0, spy_new_low=False, spy_retrace=1.0, vix_level=16.0,
        vix_chg_pct=0.0, vix_session_high=16.0, vix_off_high_pct=0.0, n_names=30,
        insufficient=False)
    base.update(over)
    return ShockReading(**base)


DEPTH = dict(breadth_frac=0.40, sectors_down=3, sectors_total=5)
FAST = dict(breadth_frac=0.25, breadth_speed=0.10)


def _run(state, *readings):
    for reading in readings:
        state = step(state, reading, TH)
    return state


def test_default_state_and_label_validation():
    assert ShockState() == ShockState(label="NORMAL", since=None, session_date=None,
                                      vix_session_high=None, spy_prev_close=None,
                                      entry_streak=0, hold_since=None, prev_breadth=None)
    with pytest.raises(ValueError):
        ShockState(label="PANIC")


def test_state_round_trips_through_json_and_empty_rows_mean_default():
    state = ShockState("SHOCK", T0, D0, 25.0, 500.0, 0, T0, 0.42)
    assert ShockState.from_row(json.loads(json.dumps(state.as_row()))) == state
    assert ShockState.from_row(None) == ShockState() == ShockState.from_row({})


def test_rules_cover_every_label():
    assert set(shock.RULES) == set(LABELS)


@pytest.mark.parametrize("over", [DEPTH, FAST], ids=["depth", "fast"])
def test_two_consecutive_qualifying_readings_enter_shock(over):
    first = step(ShockState(), _reading(0, **over), TH)
    assert first.label == "NORMAL" and first.entry_streak == 1
    second = step(first, _reading(15, **over), TH)
    assert second.label == "SHOCK" and second.since == T0 + timedelta(minutes=15)
    assert second.entry_streak == 0 and second.hold_since is None


def test_a_non_qualifying_reading_between_resets_the_streak():
    state = _run(ShockState(), _reading(0, **DEPTH), _reading(15), _reading(30, **DEPTH))
    assert state.label == "NORMAL" and state.entry_streak == 1


@pytest.mark.parametrize("over, expected", [
    (dict(breadth_frac=0.50, sectors_down=2, sectors_total=5), False),   # needs ceil(3.0) = 3
    (dict(breadth_frac=0.50, sectors_down=3, sectors_total=5), True),
    (dict(breadth_frac=0.50, sectors_down=2, sectors_total=3), True),    # ceil(1.8) = 2
    (dict(breadth_frac=0.50, sectors_down=0, sectors_total=0), False),   # no sector to judge depth
    (dict(breadth_frac=0.39, sectors_down=5, sectors_total=5), False),
    (dict(breadth_frac=0.25, breadth_speed=0.09), False),
    (dict(breadth_frac=0.24, breadth_speed=0.20), False),
    (dict(breadth_frac=0.30, breadth_speed=None), False),
    (dict(breadth_frac=None, sectors_down=5, sectors_total=5), False),
    (dict(breadth_frac=0.05, spy_atr_move=-4.0, qqq_atr_move=-4.0), False),  # index moves never trigger
])
def test_entry_condition_paths(over, expected):
    assert entry_condition(_reading(**over), TH) is expected


@pytest.mark.parametrize("chg, expected", [(15.0, True), (14.9, False), (None, False)])
def test_vix_spike_lowers_both_breadth_bars(chg, expected):
    depth = _reading(breadth_frac=7 / 20, sectors_down=3, sectors_total=5, vix_chg_pct=chg)
    fast = _reading(breadth_frac=0.20, breadth_speed=0.10, vix_chg_pct=chg)
    assert entry_condition(depth, TH) is expected
    assert entry_condition(fast, TH) is expected


def test_readings_inside_the_open_settle_window_never_count():
    early = dict(DEPTH, minutes_since_open=14.0)
    state = _run(ShockState(), _reading(0, **early), _reading(1, **dict(early, minutes_since_open=14.9)))
    assert state.label == "NORMAL" and state.entry_streak == 0
    state = _run(state, _reading(2, **dict(DEPTH, minutes_since_open=15.0)))
    assert state.entry_streak == 1
    state = _run(state, _reading(3, **dict(DEPTH, minutes_since_open=10.0)))   # resets
    assert state.entry_streak == 0


def test_an_insufficient_reading_returns_the_state_untouched():
    state = step(ShockState(), _reading(0, **DEPTH), TH)
    thin = _reading(15, **dict(DEPTH, n_names=3, insufficient=True))
    assert step(state, thin, TH) is state
    assert step(state, _reading(30, **DEPTH), TH).label == "SHOCK"


def test_hysteresis_band_holds_normal():
    between = dict(breadth_frac=0.30, sectors_down=3, sectors_total=5)
    state = _run(ShockState(), *[_reading(15 * i, **between) for i in range(4)])
    assert state.label == "NORMAL" and state.entry_streak == 0


def test_carry_copies_session_fields_and_records_breadth():
    state = step(ShockState(), _reading(0, vix_session_high=22.0, spy_prev_close=501.0,
                                        breadth_frac=0.12), TH)
    assert (state.session_date, state.vix_session_high, state.spy_prev_close) == (D0, 22.0, 501.0)
    assert state.prev_breadth == 0.12


def test_a_missing_spy_prior_close_keeps_it_within_the_session_only():
    state = step(ShockState(), _reading(0), TH)
    same = step(state, _reading(15, spy_prev_close=None), TH)
    assert same.spy_prev_close == 500.0
    next_day = _reading(0, as_of=T0 + timedelta(days=1), session_date=D0 + timedelta(days=1),
                        spy_prev_close=None)
    assert step(same, next_day, TH).spy_prev_close is None


def test_a_shock_state_with_breadth_still_high_stays_shock():
    state = ShockState("SHOCK", T0, D0, 20.0, 500.0)
    after = step(state, _reading(120, breadth_frac=0.50, sectors_down=4), TH)
    assert after.label == "SHOCK" and after.since == T0
