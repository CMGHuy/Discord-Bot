"""v140 verdict: ΔExpR >= +0.10R, lower 95% bound > 0, >= 7 of 9 years (2011–2019)
positive (an empty year counts against), N >= 300; N < 300 is UNDERPOWERED."""
from datetime import date, timedelta

import numpy as np
import pytest

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import verdict

FAST = 500   # resamples in tests; the screen itself uses the default 10,000


def _events(n, d=0.25, years=verdict.YEARS):
    """n events, one per ISO week, cycling through ``years``."""
    out = []
    for i in range(n):
        day = date(years[i % len(years)], 1, 4) + timedelta(weeks=i // len(years))
        out.append(verdict.PairedEvent(day.isoformat(), d(i) if callable(d) else d))
    return out


def test_pass_rule_constants_are_the_spec_values():
    assert (verdict.PASS_EXP_R, verdict.MIN_N, verdict.MIN_POSITIVE_YEARS) == (0.10, 300, 7)
    assert verdict.YEARS == tuple(range(2011, 2020))
    assert (verdict.SCREEN_PASS, verdict.SCREEN_FAIL, verdict.SCREEN_UNDERPOWERED) == (
        "SCREEN-PASS", "SCREEN-FAIL", "SCREEN-UNDERPOWERED")   # V140-10's ledger strings


@pytest.mark.parametrize("delta, holds", [(0.10, True), (0.0999, False), (None, False)])
def test_mean_clause_boundary(delta, holds):
    assert verdict.mean_clause(delta) is holds


def test_mean_clause_survives_float_summation_at_exactly_ten_cents():
    assert verdict.mean_clause(float(np.mean([0.1] * 300)))


@pytest.mark.parametrize("low, holds", [(1e-9, True), (0.0, False), (-0.01, False), (None, False)])
def test_ci_clause_boundary(low, holds):
    assert verdict.ci_clause(low) is holds


@pytest.mark.parametrize("count, holds", [(7, True), (6, False), (9, True)])
def test_years_clause_boundary(count, holds):
    assert verdict.years_clause(count) is holds


@pytest.mark.parametrize("n, holds", [(300, True), (299, False)])
def test_n_clause_boundary(n, holds):
    assert verdict.n_clause(n) is holds


def test_a_year_with_no_events_counts_against():
    table = verdict.per_year(_events(30, years=verdict.YEARS[:3]))
    assert table[2015] == (0, None)
    assert verdict.years_positive(table) == 3


def test_all_four_clauses_pass():
    out = verdict.decide(_events(300), n_resamples=FAST)
    assert out.verdict == "SCREEN-PASS"
    assert out.n == 300 and out.delta_exp_r == pytest.approx(0.25)
    assert out.ci_low == pytest.approx(0.25) and out.p == 0.0
    assert out.years_positive == 9
    assert all(out.clauses.values())


def test_299_events_is_underpowered_even_when_everything_else_passes():
    out = verdict.decide(_events(299), n_resamples=FAST)
    assert out.verdict == "SCREEN-UNDERPOWERED"
    assert out.clauses == {"exp_r": True, "ci": True, "years": True, "n": False}


def test_mean_below_ten_cents_fails():
    out = verdict.decide(_events(300, d=0.09), n_resamples=FAST)
    assert out.verdict == "SCREEN-FAIL" and out.clauses["exp_r"] is False


def test_six_positive_years_fails():
    out = verdict.decide(_events(300, years=verdict.YEARS[:6]), n_resamples=FAST)
    assert out.verdict == "SCREEN-FAIL"
    assert out.clauses == {"exp_r": True, "ci": True, "years": False, "n": True}


def test_a_lower_bound_at_or_below_zero_fails():
    # ~+0.17R and positive in every year, but one week in three +4R, two in three -1.8R
    def d(i):
        return 4.0 if (i // len(verdict.YEARS)) % 3 == 0 else -1.8
    out = verdict.decide(_events(300, d=d), n_resamples=FAST)
    assert out.delta_exp_r == pytest.approx(np.mean([d(i) for i in range(300)]))
    assert out.delta_exp_r >= 0.10
    assert out.ci_low <= 0
    assert out.verdict == "SCREEN-FAIL"
    assert out.clauses == {"exp_r": True, "ci": False, "years": True, "n": True}


def test_no_events_is_underpowered_with_no_interval():
    out = verdict.decide([], n_resamples=FAST)
    assert out.verdict == "SCREEN-UNDERPOWERED"
    assert out.n == 0 and out.delta_exp_r is None and out.ci_low is None and out.p is None


def test_week_sums_reproduce_the_event_level_bootstrap():
    """Frozen reading F5: aggregating per week changes cost, not the answer."""
    base = _events(60, d=lambda i: (i % 7) - 3.0)
    same_weeks = [verdict.PairedEvent(e.entry_date, e.d * 0.5 + 1.0) for e in base]
    events = base + same_weeks                      # two events in every week
    by_event = stats.week_cluster_bootstrap([], events, verdict.mean_d,
                                            n_resamples=200, seed=42)
    by_week = stats.week_cluster_bootstrap([], verdict.week_sums(events),
                                           verdict.pooled_mean, n_resamples=200, seed=42)
    np.testing.assert_allclose(by_week, by_event, rtol=1e-12, atol=1e-12)
