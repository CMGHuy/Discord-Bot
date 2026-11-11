"""v214 G1: the avoid mode's six frozen clauses. Against the matched null:
mean(d) <= -0.10R, upper 95% bound < 0, mean(d) < 0 in >= 7 of 2011-2019
(an empty year counts against), N >= 300. Against the control arm:
mean(d_c) <= -0.10R, upper bound < 0, N_c >= 300. N or N_c < 300 is
UNDERPOWERED; any other failing clause is FAIL. Edge mode is unchanged."""
import dataclasses
import functools
from datetime import date, timedelta

import numpy as np
import pytest

from swingbot.core.backtesting.screen import verdict

FAST = 500
AVOID_KEYS = ("exp_r", "ci", "years", "n", "control_exp_r", "control_ci", "control_n")


def _events(n, d=-0.25, years=verdict.YEARS):
    """n events, one per ISO week, cycling through ``years`` (as test_verdict.py)."""
    out = []
    for i in range(n):
        day = date(years[i % len(years)], 1, 4) + timedelta(weeks=i // len(years))
        out.append(verdict.PairedEvent(day.isoformat(), d(i) if callable(d) else d))
    return out


def _avoid(events, control):
    return verdict.decide(events, mode="avoid", control=control, n_resamples=FAST)


def test_mode_constants_are_the_spec_values():
    assert verdict.MODES == ("edge", "avoid")
    assert verdict.SCREEN_AVOID_PASS == "SCREEN-AVOID-PASS"


@pytest.mark.parametrize("delta, holds", [
    (-0.10, True), (-0.0999, False), (-0.25, True), (0.0, False), (0.10, False), (None, False)])
def test_avoid_mean_clause_mirrors_the_tolerance(delta, holds):
    assert verdict.avoid_mean_clause(delta) is holds


def test_avoid_mean_clause_survives_float_summation_at_exactly_minus_ten_cents():
    assert verdict.avoid_mean_clause(float(np.mean([-0.1] * 300)))


@pytest.mark.parametrize("high, holds", [(-1e-9, True), (0.0, False), (0.01, False), (None, False)])
def test_avoid_ci_clause_is_strict_on_the_upper_bound(high, holds):
    assert verdict.avoid_ci_clause(high) is holds


def test_years_negative_counts_strictly_negative_non_empty_years():
    table = {2011: (3, -0.1), 2012: (0, None), 2013: (2, 0.0), 2014: (1, 0.2), 2015: (5, -1e-9)}
    assert verdict.years_negative(table) == 2


def test_avoid_p_is_the_share_of_resamples_at_or_above_zero():
    below, above = _events(300, d=-0.25), _events(300, d=0.25)
    assert verdict.bootstrap(below, n_resamples=FAST, seed=42, mode="avoid")[2] == 0.0
    assert verdict.bootstrap(below, n_resamples=FAST, seed=42, mode="edge")[2] == 1.0
    assert verdict.bootstrap(above, n_resamples=FAST, seed=42, mode="avoid")[2] == 1.0
    assert verdict.bootstrap(above, n_resamples=FAST, seed=42)[2] == 0.0


def test_the_bounds_do_not_depend_on_the_mode_and_the_two_p_cover_everything():
    mixed = _events(400, d=lambda i: (-0.6, 0.2, 0.1, -0.3, 0.05)[i % 5])
    edge = verdict.bootstrap(mixed, n_resamples=FAST, seed=42)
    avoid = verdict.bootstrap(mixed, n_resamples=FAST, seed=42, mode="avoid")
    assert edge[:2] == avoid[:2]
    assert edge[2] + avoid[2] >= 1.0 - 1e-12


def test_all_six_clauses_holding_is_an_avoid_pass():
    out = _avoid(_events(300), _events(300))
    assert out.verdict == "SCREEN-AVOID-PASS" and out.mode == "avoid"
    assert tuple(out.clauses) == AVOID_KEYS and all(out.clauses.values())
    assert out.years_negative == 9 and out.p == 0.0
    assert out.control == verdict.ControlArm(
        n=300, delta_exp_r=pytest.approx(-0.25), ci_low=pytest.approx(-0.25),
        ci_high=pytest.approx(-0.25), per_year=verdict.per_year(_events(300)))


def test_exactly_minus_ten_cents_on_both_arms_passes():
    assert _avoid(_events(300, d=-0.10), _events(300, d=-0.10)).verdict == "SCREEN-AVOID-PASS"


def test_a_hair_short_of_minus_ten_cents_fails_on_the_null_clause():
    out = _avoid(_events(300, d=-0.0999), _events(300))
    assert out.verdict == "SCREEN-FAIL" and out.clauses["exp_r"] is False


def test_a_control_arm_short_of_minus_ten_cents_fails():
    out = _avoid(_events(300), _events(300, d=-0.05))
    assert out.verdict == "SCREEN-FAIL"
    assert out.clauses["control_exp_r"] is False and out.clauses["control_ci"] is True


def test_an_upper_bound_of_exactly_zero_on_the_control_arm_fails():
    out = _avoid(_events(300), _events(300, d=0.0))
    assert out.control.ci_high == 0.0 and out.clauses["control_ci"] is False
    assert out.verdict == "SCREEN-FAIL"


def test_299_events_is_underpowered_even_when_everything_else_passes():
    out = _avoid(_events(299), _events(300))
    assert out.verdict == "SCREEN-UNDERPOWERED"
    assert out.clauses == dict(zip(AVOID_KEYS, (True, True, True, False, True, True, True)))


def test_300_events_and_300_control_events_is_powered():
    assert _avoid(_events(300), _events(300)).verdict == "SCREEN-AVOID-PASS"


def test_299_control_events_is_underpowered_even_when_everything_else_passes():
    out = _avoid(_events(300), _events(299))
    assert out.verdict == "SCREEN-UNDERPOWERED"
    assert out.clauses == dict(zip(AVOID_KEYS, (True, True, True, True, True, True, False)))


def test_no_control_events_is_underpowered_not_fail():
    for control in (None, []):
        out = _avoid(_events(300), control)
        assert out.verdict == "SCREEN-UNDERPOWERED"
        assert out.control == verdict.ControlArm(0, None, None, None, verdict.per_year([]))
        assert out.clauses["control_n"] is False


def test_an_empty_year_counts_against_the_avoid_years_clause():
    six = _avoid(_events(300, years=verdict.YEARS[:6]), _events(300))
    assert six.years_negative == 6 and six.clauses["years"] is False
    assert six.verdict == "SCREEN-FAIL"
    seven = _avoid(_events(300, years=verdict.YEARS[:7]), _events(300))
    assert seven.years_negative == 7 and seven.verdict == "SCREEN-AVOID-PASS"


def test_an_avoid_idea_never_gets_an_edge_label_and_vice_versa():
    """G5: whatever the events, an avoid verdict is AVOID-PASS, FAIL or
    UNDERPOWERED; an edge verdict never reads AVOID-PASS."""
    for d in (0.25, 0.10, 0.0, -0.10, -0.25):
        avoid = _avoid(_events(300, d=d), _events(300, d=d))
        edge = verdict.decide(_events(300, d=d), n_resamples=FAST)
        assert avoid.verdict != verdict.SCREEN_PASS
        assert edge.verdict != verdict.SCREEN_AVOID_PASS
    assert _avoid(_events(300, d=0.25), _events(300, d=0.25)).verdict == "SCREEN-FAIL"


def test_label_is_table_driven_per_mode():
    assert verdict.label(dict.fromkeys(AVOID_KEYS, True), "avoid") == "SCREEN-AVOID-PASS"
    assert verdict.label({"exp_r": True, "ci": True, "years": True, "n": True}) == "SCREEN-PASS"
    assert verdict.label({**dict.fromkeys(AVOID_KEYS, True), "control_n": False},
                         "avoid") == "SCREEN-UNDERPOWERED"


def test_edge_mode_is_today_s_verdict_exactly():
    events = _events(400, d=lambda i: 0.3 if i % 3 else -0.1)
    plain = verdict.decide(events, n_resamples=FAST)
    assert verdict.decide(events, mode="edge", n_resamples=FAST) == plain
    assert tuple(plain.clauses) == ("exp_r", "ci", "years", "n")
    assert (plain.mode, plain.years_negative, plain.control) == ("edge", None, None)
    low, high, p = verdict.bootstrap(events, n_resamples=FAST, seed=42)
    assert (plain.ci_low, plain.ci_high, plain.p) == (low, high, p)


def test_verdict_fields_append_after_the_original_nine():
    assert [f.name for f in dataclasses.fields(verdict.Verdict)] == [
        "verdict", "n", "delta_exp_r", "ci_low", "ci_high", "p", "years_positive",
        "per_year", "clauses", "mode", "years_negative", "control"]
    legacy = verdict.Verdict("SCREEN-FAIL", 412, 0.03, -0.01, 0.07, 0.2, 6, {}, {})
    assert (legacy.mode, legacy.years_negative, legacy.control) == ("edge", None, None)


def test_the_partial_monkeypatch_the_runner_tests_use_still_works():
    fast = functools.partial(verdict.decide, n_resamples=FAST)
    assert fast(_events(300), mode="avoid", control=_events(300)).verdict == "SCREEN-AVOID-PASS"
    assert fast(_events(300, d=0.25)).verdict == "SCREEN-PASS"


def test_an_unknown_mode_or_an_edge_control_is_refused():
    with pytest.raises(ValueError, match="mode"):
        verdict.decide(_events(300), mode="veto", n_resamples=FAST)
    with pytest.raises(ValueError, match="control"):
        verdict.decide(_events(300), control=_events(300), n_resamples=FAST)
