"""v188: cancelled and filled plans to replay rows (pure).

Frames start 2026-07-30; bar 2 is the cancel day 2026-08-03 (open 108 by
default here, so the estimated risk_cap entry differs from the trigger).
"""
from datetime import date

import pytest

from swingbot.core.analytics import cancel_rows as rows_mod
from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict, record_transition
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

AT = "2026-08-03T15:00:00+00:00"
FLAT = (100.0, 100.5, 99.5, 100.0)
CANCEL_BAR = (108.0, 108.5, 99.5, 100.0)     # gap open 108 above the trigger 105
STOP_HIT = (100.0, 101.0, 94.0, 95.0)
LONG = dict(entry_type="stop_entry", trigger_price=105.0, stop_loss=95.0,
            tp1=120.0, horizon_key="2w", source="strategy", strategy="Fibonacci",
            stop_ceiling_pct=2.0)
SHORT = dict(LONG, direction="bearish", trigger_price=95.0, stop_loss=105.0, tp1=80.0)


def _frame(*walked, pre=(FLAT, FLAT, CANCEL_BAR), total=14):
    bars = list(pre) + list(walked)
    bars += [FLAT] * max(0, total - len(bars))
    return make_ohlcv(bars, start="2026-07-30")


def _cancelled(reason="invalidated", *, at=AT, extra=None, **kw):
    plan = _plan(**{**LONG, **kw})
    record_transition(plan, PlanStatus.CANCELLED, reason=reason, at=at, extra=extra)
    return plan


def _filled(*, at=AT, **kw):
    plan = _plan(**{**LONG, **kw})
    record_transition(plan, PlanStatus.ACTIVE, reason="stop_entry_fill", at=at)
    return plan


def _loader(frame):
    return lambda _ticker: frame


# -- reason buckets ------------------------------------------------------------

@pytest.mark.parametrize("raw, bucket", [
    ("risk_cap", "risk_cap"), ("invalidated", "invalidated"), ("expired", "expired"),
    ("manual", "manual"), ("never_triggered", "other"), ("no_session_data", "other"),
    (None, "other"),
])
def test_reason_bucket(raw, bucket):
    assert rows_mod.reason_bucket(raw) == bucket


def test_constants():
    assert rows_mod.REASONS == ("risk_cap", "invalidated", "expired")
    assert rows_mod.ENTRY_MODELS == ("trigger", "cancel_fill")
    assert rows_mod.EXCLUSIONS == ("no_bars", "split_guard", "bad_levels",
                                   "unknown_horizon", "no_cancel_entry")


# -- cancelled rows ------------------------------------------------------------

def test_an_invalidated_plan_is_one_trigger_row_with_its_replay():
    [row] = rows_mod.cancel_rows([_cancelled()], _loader(_frame((104, 106, 104, 105), STOP_HIT)))
    assert (row.reason, row.raw_reason, row.entry_model) == ("invalidated", "invalidated", "trigger")
    assert (row.entry, row.stop, row.tp1, row.entry_source) == (105.0, 95.0, 120.0, None)
    assert row.cancel_day == date(2026, 8, 3) and row.entry_date == "2026-08-03"
    assert (row.direction, row.origin, row.badge) == ("long", "regular", "WEAK")
    assert row.replay.outcome == "right" and row.excluded is None
    assert row.cap_size_pct is None and row.stop_ceiling_pct == 2.0


def test_a_risk_cap_plan_yields_a_trigger_row_and_an_estimated_fill_row():
    rows = rows_mod.cancel_rows([_cancelled("risk_cap")], _loader(_frame()))
    assert [r.entry_model for r in rows] == ["trigger", "cancel_fill"]
    fill = rows[1]
    assert (fill.entry, fill.entry_source) == (108.0, "estimated")   # max(open 108, trigger 105)
    assert fill.reason == "risk_cap" and fill.excluded is None


def test_a_recorded_crossing_price_wins_over_the_estimate():
    plan = _cancelled("risk_cap", extra={"entry_price": 106.5})
    fill = rows_mod.cancel_rows([plan], _loader(_frame()))[1]
    assert (fill.entry, fill.entry_source) == (106.5, "recorded")


def test_the_short_estimate_is_the_lower_of_open_and_trigger():
    gap_down = (90.0, 100.5, 89.5, 100.0)
    plan = _cancelled("risk_cap", **SHORT)
    fill = rows_mod.cancel_rows([plan], _loader(_frame(pre=(FLAT, FLAT, gap_down))))[1]
    assert (fill.entry, fill.entry_source, fill.direction) == (90.0, "estimated", "short")


def test_the_estimate_never_lies_inside_the_trigger():
    open_below = (101.0, 101.5, 99.5, 100.0)         # open under a long trigger of 105
    entry, source = rows_mod.cancel_entry(_cancelled("risk_cap"), _frame(pre=(FLAT, FLAT, open_below)),
                                          date(2026, 8, 3))
    assert (entry, source) == (105.0, "estimated")


def test_no_cancel_day_bar_excludes_only_the_fill_row():
    """Review Focus 3: never replay a missing crossing price from the trigger."""
    frame = _frame()
    frame = frame[frame.index.date != date(2026, 8, 3)]
    trigger, fill = rows_mod.cancel_rows([_cancelled("risk_cap")], _loader(frame))
    assert (fill.excluded, fill.replay, fill.entry, fill.entry_source) == \
        ("no_cancel_entry", None, None, None)
    assert trigger.excluded is None and trigger.replay is not None


def test_cap_size_on_both_risk_cap_rows():
    trigger, fill = rows_mod.cancel_rows([_cancelled("risk_cap")], _loader(_frame()))
    assert trigger.cap_size_pct == pytest.approx(21.0)    # 100 * 2 / (10/105*100)
    assert fill.cap_size_pct == pytest.approx(16.62)      # 100 * 2 / (13/108*100)


def test_a_pre_v139_plan_still_gets_a_cap_size():
    """Review Focus 5: no stored stop_ceiling_pct falls back, never raises."""
    confluence = _cancelled("risk_cap", stop_ceiling_pct=None, source="confluence")
    strategy = _cancelled("risk_cap", stop_ceiling_pct=None, plan_id="p2")
    rows = rows_mod.cancel_rows([confluence, strategy], _loader(_frame()))
    assert rows[0].stop_ceiling_pct == pytest.approx(2.0)
    assert rows[0].cap_size_pct == pytest.approx(21.0)
    assert rows[2].stop_ceiling_pct is not None and rows[2].cap_size_pct > 0


def test_manual_cancels_are_never_rows_and_are_counted():
    plans = [_cancelled("manual"), _cancelled(plan_id="p2")]
    assert [r.plan_id for r in rows_mod.cancel_rows(plans, _loader(_frame()))] == ["p2"]
    assert rows_mod.manual_count(plans) == 1


def test_an_unknown_reason_lands_in_other_with_its_raw_code():
    [row] = rows_mod.cancel_rows([_cancelled("never_triggered")], _loader(_frame()))
    assert (row.reason, row.raw_reason) == ("other", "never_triggered")
    assert row.replay is not None


def test_open_and_closed_plans_are_not_cancel_rows():
    assert rows_mod.cancel_rows([_plan(**LONG), _filled()], _loader(_frame())) == []


def test_next_session_origin_is_kept():
    [row] = rows_mod.cancel_rows([_cancelled(origin="next_session")], _loader(_frame()))
    assert row.origin == "next_session"


def test_dicts_and_plans_give_the_same_rows():
    plan = _cancelled("risk_cap")
    loader = _loader(_frame())
    assert rows_mod.cancel_rows([plan_to_dict(plan)], loader) == rows_mod.cancel_rows([plan], loader)


def test_the_window_cancel_et_timestamp_keeps_its_session():
    [row] = rows_mod.cancel_rows([_cancelled("expired", at="2026-08-03T16:00:00-04:00")],
                                 _loader(_frame()))
    assert row.cancel_day == date(2026, 8, 3)


# -- exclusions ----------------------------------------------------------------

def test_no_bars_is_excluded():
    [row] = rows_mod.cancel_rows([_cancelled()], lambda _t: None)
    assert (row.excluded, row.replay) == ("no_bars", None)


def test_an_empty_frame_is_no_bars():
    [row] = rows_mod.cancel_rows([_cancelled()], _loader(_frame().iloc[0:0]))
    assert row.excluded == "no_bars"


def test_a_split_inside_the_data_is_excluded_and_kept_visible():
    """Review Focus 2: adjusted 50s against a raw 105 trigger."""
    halved = (50.0, 50.25, 49.75, 50.0)
    [row] = rows_mod.cancel_rows([_cancelled()], _loader(_frame(pre=(halved,) * 3)))
    assert (row.excluded, row.replay, row.ticker) == ("split_guard", None, "AAPL")


@pytest.mark.parametrize("levels", [
    dict(tp1=104.0),               # TP1 not beyond a long entry
    dict(stop_loss=106.0),         # stop above a long entry
    dict(trigger_price=None),
])
def test_bad_levels_are_excluded(levels):
    [row] = rows_mod.cancel_rows([_cancelled(**levels)], _loader(_frame()))
    assert row.excluded == "bad_levels"


def test_an_unknown_horizon_is_excluded():
    [row] = rows_mod.cancel_rows([_cancelled(horizon_key="9y")], _loader(_frame()))
    assert (row.excluded, row.stop_ceiling_pct) == ("unknown_horizon", 2.0)


# -- filled rows (the baseline population) -------------------------------------

def test_a_filled_plan_replays_from_its_trigger_without_a_touch():
    [row] = rows_mod.filled_rows([_filled()], _loader(_frame(STOP_HIT)))
    assert (row.reason, row.raw_reason, row.entry_model) == ("filled", None, "trigger")
    assert row.cancel_day == date(2026, 8, 3)
    assert row.replay.outcome == "right"


def test_filled_rows_skip_pending_and_cancelled_plans():
    plans = [_plan(**LONG), _cancelled(plan_id="p2"), _filled(plan_id="p3")]
    assert [r.plan_id for r in rows_mod.filled_rows(plans, _loader(_frame()))] == ["p3"]


def test_the_fill_day_is_the_first_active_transition():
    plan = _filled(at="2026-08-04T01:30:00+00:00")            # 21:30 ET on the 3rd
    record_transition(plan, PlanStatus.PARTIAL, at="2026-08-10T15:00:00+00:00")
    [row] = rows_mod.filled_rows([plan], _loader(_frame()))
    assert row.cancel_day == date(2026, 8, 3)


def test_empty_inputs():
    assert rows_mod.cancel_rows([], _loader(_frame())) == []
    assert rows_mod.filled_rows([], _loader(_frame())) == []
    assert rows_mod.manual_count([]) == 0
