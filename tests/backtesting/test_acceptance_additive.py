"""v238 additive gate (v230 spec Part C): the add-only split and clauses 1-2.

Fixtures put rows in distinct ISO weeks so the week-cluster bootstrap has
units to resample. Where a clause is tested at its boundary every week has
the same composition, so every bootstrap draw equals the full-sample value
and the lower bound is exact.
"""
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from swingbot.core.backtesting import acceptance_additive as aa
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms.pairing import DuplicateKeyError

FAST = dict(n_resamples=300, seed=42)


def _row(i, r, outcome="win", *, week=0, strategy="Turtle Soup", source="strategy"):
    entry = date(2021, 1, 4) + timedelta(days=7 * week)
    return ArmTrade(ticker=f"T{i}", strategy=strategy, horizon_key="4w",
                    entry_date=entry.isoformat(), outcome=outcome, r_multiple=r,
                    planned_rr=2.0, source=source, direction="bullish")


def _base(n=20):
    return [_row(i, 1.0 if i % 2 else -1.0, "win" if i % 2 else "loss", week=i,
                 strategy="RSI", source="confluence") for i in range(n)]


def _weekly(pattern, weeks=30):
    """`pattern` = [(r, outcome), ...] repeated in every week, one ticker per row."""
    return [_row(100 * w + j, r, outcome, week=w)
            for w in range(weeks) for j, (r, outcome) in enumerate(pattern)]


ADDED = [_row(500 + i, 2.0, "win", week=i) for i in range(3)]


def test_module_constants_are_pinned():
    assert aa.ADDITIVE_VERSION == 1
    assert aa.ADDITIVE_GATE_MISUSE == "ADDITIVE_GATE_MISUSE"
    assert aa.CLAUSES == ("own_expectancy", "win_rate_above_breakeven",
                          "book_net_gain", "stability")


# --- split_additive -----------------------------------------------------------------

def test_an_add_only_component_splits_cleanly():
    base = _base()
    split = aa.split_additive(base, base + ADDED)
    assert split.misuse is None
    assert split.added == tuple(ADDED)
    assert split.displaced == ()


def test_a_component_that_adds_nothing_is_misuse():
    base = _base()
    split = aa.split_additive(base, list(base))
    assert split.misuse.startswith(aa.ADDITIVE_GATE_MISUSE)
    assert "adds no row" in split.misuse


def test_a_changed_shared_outcome_is_misuse():
    base = _base()
    flipped = replace(base[1], outcome="loss", r_multiple=-1.0)
    split = aa.split_additive(base, [base[0], flipped, *base[2:], *ADDED])
    assert split.misuse.startswith(aa.ADDITIVE_GATE_MISUSE)
    assert "changed outcome or R" in split.misuse


def test_a_changed_shared_r_with_the_same_outcome_is_misuse():
    base = _base()
    moved = replace(base[1], r_multiple=1.5)
    split = aa.split_additive(base, [base[0], moved, *base[2:], *ADDED])
    assert split.misuse.startswith(aa.ADDITIVE_GATE_MISUSE)
    assert "changed outcome or R" in split.misuse


def test_a_vanished_baseline_row_with_an_added_row_is_a_displacement():
    base = _base()
    split = aa.split_additive(base, base[1:] + ADDED)
    assert split.misuse is None
    assert split.displaced == (base[0],)
    assert len(split.added) == 3


def test_more_rows_vanished_than_added_is_misuse():
    base = _base()
    split = aa.split_additive(base, base[3:] + ADDED[:2])
    assert split.misuse.startswith(aa.ADDITIVE_GATE_MISUSE)
    assert "3 baseline row(s) vanished but only 2 were added" in split.misuse


def test_the_first_failing_rule_is_the_reason():
    base = _base()
    split = aa.split_additive(base, base[3:])   # adds nothing AND removes three
    assert "adds no row" in split.misuse


def test_a_duplicate_key_is_refused_not_collapsed():
    base = _base()
    with pytest.raises(DuplicateKeyError):
        aa.split_additive(base, base + [ADDED[0], ADDED[0]])


# --- the week bootstrap over added rows ---------------------------------------------

def test_added_bootstrap_resamples_whole_weeks():
    week_a = [_row(1, 1.0, week=0), _row(2, 1.0, week=0)]
    week_b = [_row(3, -1.0, "loss", week=1)]
    draws = aa.added_bootstrap(week_a + week_b, aa.expectancy_r, **FAST)
    values = set(np.round(draws, 6))
    assert values <= {1.0, round(1 / 3, 6), -1.0}    # AA, AB, BB
    assert round(-1 / 3, 6) not in values            # a row bootstrap would hit this


# --- clause 1: own_expectancy -------------------------------------------------------

def test_own_expectancy_passes_when_every_week_pays():
    res = aa.clause_own_expectancy(_weekly([(2.0, "win"), (-1.0, "loss")]), **FAST)
    assert res.name == "own_expectancy"
    assert res.verdict == "PASS"
    assert res.value == pytest.approx(0.5)
    assert res.threshold == 0.0
    assert "p=" in res.detail                        # the one-sided p is reported


def test_own_expectancy_fails_at_a_lower_bound_of_exactly_zero():
    res = aa.clause_own_expectancy(_weekly([(1.0, "win"), (-1.0, "loss")]), **FAST)
    assert res.value == pytest.approx(0.0)
    assert res.verdict == "FAIL"


def test_own_expectancy_fails_when_the_rows_lose():
    res = aa.clause_own_expectancy(_weekly([(0.5, "win"), (-1.0, "loss")]), **FAST)
    assert res.verdict == "FAIL"


def test_own_expectancy_fails_with_no_closed_row():
    rows = [_row(i, None, "not_triggered", week=i) for i in range(5)]
    res = aa.clause_own_expectancy(rows, **FAST)
    assert res.verdict == "FAIL"
    assert res.value is None
    assert "undefined" in res.detail


# --- realised break-even ------------------------------------------------------------

def test_breakeven_is_avg_loss_over_avg_win_plus_avg_loss():
    rows = [_row(1, 2.0), _row(2, 2.0), _row(3, -1.0, "loss")]
    assert aa.realised_breakeven(rows) == pytest.approx(1.0 / 3.0)


def test_breakeven_ignores_undecided_rows():
    rows = [_row(1, 2.0), _row(2, -1.0, "loss"), _row(3, -0.4, "timeout"),
            _row(4, 0.0, "scratch")]
    assert aa.realised_breakeven(rows) == pytest.approx(1.0 / 3.0)


def test_breakeven_with_no_win_is_one_and_with_no_loss_is_zero():
    assert aa.realised_breakeven([_row(1, -1.0, "loss")]) == pytest.approx(1.0)
    assert aa.realised_breakeven([_row(1, 2.0)]) == pytest.approx(0.0)


def test_breakeven_is_undefined_with_no_decided_row():
    assert aa.realised_breakeven([_row(1, -0.2, "timeout")]) is None
    assert aa.realised_breakeven([]) is None


# --- clause 2: win_rate_above_breakeven ---------------------------------------------

def test_win_rate_passes_above_its_own_breakeven():
    # WR 33.33% every week; break-even 1 / (2.2 + 1) = 31.25%
    rows = _weekly([(2.2, "win"), (-1.0, "loss"), (-1.0, "loss")])
    res = aa.clause_win_rate_above_breakeven(rows, **FAST)
    assert res.name == "win_rate_above_breakeven"
    assert res.verdict == "PASS"
    assert res.value == pytest.approx(100.0 / 3.0)
    assert res.threshold == pytest.approx(31.25)


def test_win_rate_fails_when_its_lower_bound_equals_breakeven():
    # WR 33.33% every week; break-even 1 / (2 + 1) = 33.33%
    rows = _weekly([(2.0, "win"), (-1.0, "loss"), (-1.0, "loss")])
    res = aa.clause_win_rate_above_breakeven(rows, **FAST)
    assert res.value == pytest.approx(res.threshold)
    assert res.verdict == "FAIL"


def test_win_rate_fails_below_breakeven_even_with_a_high_pooled_look():
    # WR 33.33%, break-even 50%: a 1R winner with two 1R losers
    rows = _weekly([(1.0, "win"), (-1.0, "loss"), (-1.0, "loss")])
    res = aa.clause_win_rate_above_breakeven(rows, **FAST)
    assert res.verdict == "FAIL"
    assert res.threshold == pytest.approx(50.0)


def test_win_rate_fails_with_no_decided_row():
    rows = [_row(i, -0.1, "timeout", week=i) for i in range(5)]
    res = aa.clause_win_rate_above_breakeven(rows, **FAST)
    assert res.verdict == "FAIL"
    assert res.value is None
