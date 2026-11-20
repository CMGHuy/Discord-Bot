"""v238 additive gate clauses 3-4 (v230 spec Part C): book net gain, stability."""
from datetime import date, timedelta

import pytest

from swingbot.core.backtesting import acceptance_additive as aa
from swingbot.core.backtesting.acceptance import ArmTrade

FAST = dict(n_resamples=300, seed=42)


def _outcome(r):
    return "win" if r > 0 else ("loss" if r < 0 else "scratch")


def _row(ticker, r, *, week=0, year=2021, strategy="Turtle Soup", source="strategy"):
    entry = date(year, 1, 4) + timedelta(days=7 * week)
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key="4w",
                    entry_date=entry.isoformat(), outcome=_outcome(r), r_multiple=r,
                    planned_rr=2.0, source=source, direction="bullish")


def _base_row(ticker, r, **kw):
    return _row(ticker, r, strategy="RSI", source="confluence", **kw)


def _displacing_arms(added_r, displaced_r, weeks=30):
    """Every week: one kept baseline row (+1R), one baseline row the added
    strategy displaces, one added row. Identical weeks make every bootstrap
    draw equal the point estimate."""
    baseline, component = [], []
    for w in range(weeks):
        kept = _base_row(f"K{w}", 1.0, week=w)
        baseline += [kept, _base_row(f"D{w}", displaced_r, week=w)]
        component += [kept, _row(f"A{w}", added_r, week=w)]
    return baseline, component


def test_clause_constants_are_pinned():
    assert aa.TOLERANCE_SHARE == 0.10
    assert aa.FOLD_YEARS == ("2021", "2022", "2023")
    assert aa.FOLD_FLOOR_R == -0.10
    assert aa.FOLD_MIN_N == 30
    assert aa.FOLDS_POSITIVE == 2


# --- clause 3: book_net_gain --------------------------------------------------------

def test_book_net_gain_is_skipped_without_displacement():
    baseline = [_base_row(f"K{w}", 1.0, week=w) for w in range(10)]
    component = baseline + [_row(f"A{w}", 2.0, week=w) for w in range(10)]
    split = aa.split_additive(baseline, component)
    res = aa.clause_book_net_gain(baseline, component, split, **FAST)
    assert res.name == "book_net_gain"
    assert res.verdict == "SKIPPED"
    assert "no baseline row displaced" in res.detail


def test_book_net_gain_passes_when_the_book_makes_more_r():
    baseline, component = _displacing_arms(added_r=2.0, displaced_r=-1.0)
    split = aa.split_additive(baseline, component)
    res = aa.clause_book_net_gain(baseline, component, split, **FAST)
    assert res.verdict == "PASS"
    assert res.value == pytest.approx(30 * 3.0)          # sum, not mean
    assert res.threshold == pytest.approx(-0.10 * 30 * 2.0)


def test_book_net_gain_fails_at_a_point_change_of_zero():
    baseline, component = _displacing_arms(added_r=1.0, displaced_r=1.0)
    split = aa.split_additive(baseline, component)
    res = aa.clause_book_net_gain(baseline, component, split, **FAST)
    assert res.value == pytest.approx(0.0)
    assert res.verdict == "FAIL"


def test_book_net_gain_fails_when_displacement_costs_more_than_it_adds():
    baseline, component = _displacing_arms(added_r=0.5, displaced_r=2.0)
    split = aa.split_additive(baseline, component)
    res = aa.clause_book_net_gain(baseline, component, split, **FAST)
    assert res.value < 0
    assert res.verdict == "FAIL"


def test_book_net_gain_fails_a_positive_point_with_a_lower_bound_under_the_floor():
    # Weeks 0-4 displace a +5R plan for a +1R add (-4R each); weeks 5-29
    # only add +1R. Point +5R, floor -3R, but a draw heavy in bad weeks
    # sinks the book well below the floor.
    baseline = [_base_row(f"D{w}", 5.0, week=w) for w in range(5)]
    component = [_row(f"A{w}", 1.0, week=w) for w in range(30)]
    split = aa.split_additive(baseline, component)
    res = aa.clause_book_net_gain(baseline, component, split, **FAST)
    assert res.value == pytest.approx(5.0)
    assert res.threshold == pytest.approx(-3.0)
    assert res.verdict == "FAIL"
    assert "floor" in res.detail


@pytest.mark.parametrize("point, lo, floor, ok", [
    (0.5, -0.999, -1.0, True),
    (0.5, -1.0, -1.0, False),        # the lower bound must be strictly above the floor
    (0.0, 2.0, -1.0, False),         # the point must be strictly positive
    (1e-12, 2.0, -1.0, False),       # ... beyond float noise
])
def test_book_verdict_boundaries(point, lo, floor, ok):
    assert aa._book_verdict(point, lo, floor) is ok


# --- clause 4: stability ------------------------------------------------------------

def _fold(year, r, n=40):
    baseline = [_base_row(f"K{year}", 1.0, year=int(year))]
    added = [_row(f"A{i}", r, week=i % 40, year=int(year)) for i in range(n)]
    return {"test_year": year, "baseline": baseline, "component": baseline + added}


def _folds(r21, r22, r23, *, n=(40, 40, 40)):
    return [_fold("2021", r21, n[0]), _fold("2022", r22, n[1]), _fold("2023", r23, n[2])]


def test_stability_passes_with_two_positive_folds_and_none_sunk():
    res = aa.clause_stability(_folds(0.5, 0.2, -0.05))
    assert res.name == "stability"
    assert res.verdict == "PASS"
    assert res.value == 2.0
    assert res.threshold == 2.0
    assert "2021 +0.5000R N=40" in res.detail


def test_stability_fails_with_one_positive_fold():
    res = aa.clause_stability(_folds(0.5, -0.05, -0.05))
    assert res.verdict == "FAIL"
    assert res.value == 1.0


def test_a_fold_of_exactly_zero_is_not_positive():
    assert aa.clause_stability(_folds(0.5, 0.0, 0.0)).verdict == "FAIL"


def test_a_fold_exactly_at_the_floor_is_allowed():
    assert aa.clause_stability(_folds(0.5, 0.2, -0.10)).verdict == "PASS"


def test_a_fold_below_the_floor_fails_even_with_two_positive():
    res = aa.clause_stability(_folds(0.5, 0.2, -0.15))
    assert res.verdict == "FAIL"
    assert "below floor: 2023" in res.detail


@pytest.mark.parametrize("n, verdict", [(29, "FAIL"), (30, "PASS")])
def test_every_fold_needs_thirty_added_rows(n, verdict):
    res = aa.clause_stability(_folds(0.5, 0.2, 0.1, n=(40, n, 40)))
    assert res.verdict == verdict
    if verdict == "FAIL":
        assert "thin: 2022" in res.detail


def test_integer_fold_years_are_accepted_and_order_does_not_matter():
    folds = [_fold(2023, 0.1), _fold(2021, 0.5), _fold(2022, 0.2)]
    res = aa.clause_stability(folds)
    assert res.verdict == "PASS"
    assert res.detail.index("2021") < res.detail.index("2022") < res.detail.index("2023")


def test_folds_other_than_2021_to_2023_fail():
    folds = [_fold("2020", 0.5), _fold("2021", 0.5), _fold("2022", 0.5)]
    res = aa.clause_stability(folds)
    assert res.verdict == "FAIL"
    assert "folds must be 2021/2022/2023, got 2020/2021/2022" in res.detail


def test_no_folds_fail():
    res = aa.clause_stability([])
    assert res.verdict == "FAIL"
    assert "got none" in res.detail


def test_a_misused_fold_fails_the_clause():
    folds = _folds(0.5, 0.2, 0.1)
    folds[1] = {**folds[1], "component": list(folds[1]["baseline"])}   # adds nothing
    res = aa.clause_stability(folds)
    assert res.verdict == "FAIL"
    assert "fold 2022" in res.detail
    assert aa.ADDITIVE_GATE_MISUSE in res.detail
