# tests/backtesting/test_acceptance_gate.py
"""The pre-registered clause set.

Clause 3 is the load-bearing one: without it, 'win rate up, expectancy
flat' is passed trivially by pulling targets nearer, and the repo ships a
stream of features that feel better and earn identically.
"""
import pytest

from swingbot.core.backtesting.acceptance import (
    ArmTrade, NON_INFERIORITY_R, evaluate, mean_win_r, median_planned_rr,
    population_split,
)


def mk(ticker, outcome, *, rr=2.0, r=None, date="2021-01-01",
       strategy="MACD", horizon="3m"):
    if r is None:
        r = {"win": 2.0, "loss": -1.0}.get(outcome, 0.0)
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key=horizon,
                    entry_date=date, outcome=outcome, r_multiple=r,
                    planned_rr=rr)


def good_filter_arms(n_tickers=30):
    """A feature that removes only losers -- real discrimination, and the
    shape that SHOULD pass every clause."""
    baseline, component = [], []
    for t in range(n_tickers):
        for i in range(10):
            trade = mk(f"T{t}", "win" if i < 4 else "loss",
                       date=f"2021-03-{i + 1:02d}")
            baseline.append(trade)
            if not (i >= 8):          # drop 2 losers of every 10
                component.append(trade)
    return baseline, component


def test_a_real_discriminator_passes():
    b, c = good_filter_arms()
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.verdict == "PASS"
    assert res.clause("win_rate").verdict == "PASS"
    assert res.clause("mechanism").verdict == "PASS"


def test_geometry_cheat_is_rejected():
    """Same trades, but the component pulled every target from 2.0R to
    1.4R. Win rate rises; the feature is worthless. Clause 3 must catch it
    even though clause 1 is happy."""
    b, c = [], []
    for t in range(30):
        for i in range(10):
            b.append(mk(f"T{t}", "win" if i < 4 else "loss", rr=2.0,
                        date=f"2021-03-{i + 1:02d}"))
            c.append(mk(f"T{t}", "win" if i < 7 else "loss", rr=1.4,
                        r=1.4 if i < 7 else -1.0,
                        date=f"2021-03-{i + 1:02d}"))
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.clause("win_rate").verdict == "PASS"
    assert res.clause("geometry").verdict == "FAIL"
    assert res.verdict == "FAIL"


def test_volume_floor_rejects_a_filter_that_barely_trades():
    b, c = [], []
    for t in range(30):
        for i in range(10):
            trade = mk(f"T{t}", "win" if i < 4 else "loss",
                       date=f"2021-03-{i + 1:02d}")
            b.append(trade)
            if i < 3:                 # keeps 30% -> a 70% cut
                c.append(trade)
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.clause("volume").verdict == "FAIL"
    assert res.verdict == "FAIL"


def test_profit_floor_rejects_a_win_rate_bought_with_expectancy():
    """Removes big winners along with losers: win rate up, expectancy
    materially down."""
    b, c = [], []
    for t in range(30):
        for i in range(10):
            outcome = "win" if i < 4 else "loss"
            r = 8.0 if i == 0 else (2.0 if outcome == "win" else -1.0)
            trade = mk(f"T{t}", outcome, r=r, date=f"2021-03-{i + 1:02d}")
            b.append(trade)
            if i not in (0, 8, 9):    # drop the huge winner and two losers
                c.append(trade)
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.clause("profit_floor").verdict == "FAIL"
    assert res.verdict == "FAIL"


def test_mechanism_clause_skipped_for_a_non_subset_feature():
    """A feature that changes outcomes rather than removing trades has no
    'removed population' -- the clause is SKIPPED and says so, and the
    skip does not block a PASS."""
    b, c = [], []
    for t in range(30):
        for i in range(10):
            b.append(mk(f"T{t}", "win" if i < 4 else "loss",
                        date=f"2021-03-{i + 1:02d}"))
            c.append(mk(f"T{t}", "win" if i < 6 else "loss",
                        date=f"2021-03-{i + 1:02d}"))
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.clause("mechanism").verdict == "SKIPPED"
    assert res.verdict == "PASS"


def test_validation_stage_fails_without_a_permutation_p():
    b, c = good_filter_arms()
    res = evaluate(b, c, stage="validation", n_resamples=300, seed=42)
    assert res.clause("permutation").verdict == "FAIL"
    assert res.verdict == "FAIL"


def test_validation_stage_passes_with_a_significant_permutation_p():
    b, c = good_filter_arms()
    res = evaluate(b, c, stage="validation", permutation_p=0.01,
                   n_resamples=300, seed=42)
    assert res.clause("permutation").verdict == "PASS"
    assert res.verdict == "PASS"


def test_walkforward_stage_does_not_require_permutation():
    b, c = good_filter_arms()
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.clause("permutation").verdict == "SKIPPED"


def test_population_split_names_removed_changed_and_unchanged():
    b = [mk("T1", "win", date="2021-01-01"), mk("T1", "loss", date="2021-01-02"),
         mk("T1", "win", date="2021-01-03")]
    c = [mk("T1", "win", date="2021-01-01"), mk("T1", "win", date="2021-01-02")]
    split = population_split(b, c)
    assert len(split["removed"]) == 1        # 01-03 is gone
    assert len(split["changed"]) == 1        # 01-02 flipped loss -> win
    assert len(split["unchanged"]) == 1
    assert split["is_subset"] is False       # an outcome changed


def test_geometry_helpers():
    trades = [mk("T1", "win", rr=2.0, r=2.0), mk("T1", "loss", rr=3.0, r=-1.0),
              mk("T1", "win", rr=1.0, r=1.0)]
    assert median_planned_rr(trades) == 2.0
    assert mean_win_r(trades) == 1.5


# ---------------------------------------------------------------------------
# Fix round 1 -- mutation-killing fixtures.
#
# All ten tests above build 30 IDENTICAL ticker blocks, so every bootstrap
# resample (drawing tickers with replacement) recomputes the exact same
# value: lo == hi == point in every one of them. That leaves four
# load-bearing comparisons unproven -- each of the four tests below swaps
# in a heterogeneous fixture (or a differing pair of geometry drops) built
# specifically to give the correct implementation and the named mutation
# different verdicts. The numbers in each docstring were computed by a
# throwaway script calling the real `bootstrap_delta`/`evaluate` before the
# assertion was written, not guessed against pytest output.
# ---------------------------------------------------------------------------


def test_profit_floor_uses_the_lower_bound_not_the_point_estimate():
    """29 tickers are exactly breakeven in both arms (5 win @ +1R, 5 loss
    @ -1R -> mean 0). Ticker T0 is identical too, except ONE of its
    component-arm losses is deepened from -1.0R to -2.5R.

    Computed via bootstrap_delta(..., n_resamples=300, seed=42):
        point = -0.0050R   (comfortably ABOVE the -0.01R floor)
        lo    = -0.0150R   (comfortably BELOW the -0.01R floor)

    Pooling 300 real trades, T0's one deepened loss barely moves the point
    estimate. But resampling TICKERS with replacement sometimes draws T0
    two or three times in the same 30-pick resample, and those draws pull
    the delta well below the floor -- which is exactly what a lower-bound
    (non-inferiority) test is supposed to catch and a point-estimate test
    is not. Swapping `res.lo` for `res.point` in `_clause_profit_floor`
    would read -0.0050 > -0.01 and PASS; the correct code reads
    -0.0150 <= -0.01 and FAILs.
    """
    b, c = [], []
    for t in range(30):
        for i in range(10):
            outcome = "win" if i < 5 else "loss"
            base_r = 1.0 if outcome == "win" else -1.0
            b.append(mk(f"T{t}", outcome, r=base_r, date=f"2021-03-{i + 1:02d}"))
            if t == 0 and i == 9:
                comp_r = -2.5          # the one deepened loss on ticker T0
            else:
                comp_r = base_r
            c.append(mk(f"T{t}", outcome, r=comp_r, date=f"2021-03-{i + 1:02d}"))
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    clause = res.clause("profit_floor")
    assert clause.verdict == "FAIL"
    assert clause.value == pytest.approx(-0.015, abs=1e-9)     # the lower bound
    assert -0.005 > NON_INFERIORITY_R > clause.value            # point vs. lo straddle the floor
    assert res.verdict == "FAIL"


def test_geometry_rejects_on_the_worse_of_the_two_drops():
    """Planned-RR falls from 2.0 to 1.9 (a 5% drop, over the 2% max);
    mean win R is untouched (both arms use the r=2.0 default for wins).

    median_planned_rr: baseline 2.0 -> component 1.9  =>  drop = +5.00%
    mean_win_r:        baseline 2.0 -> component 2.0   =>  drop = +0.00%

    `max(5.0, 0.0) = 5.0 > 2.0` -> FAIL is the only correct reading.
    `min(5.0, 0.0) = 0.0 <= 2.0` would PASS -- the mutation this kills.
    """
    b, c = [], []
    for t in range(30):
        for i in range(10):
            outcome = "win" if i < 4 else "loss"
            b.append(mk(f"T{t}", outcome, rr=2.0, date=f"2021-03-{i + 1:02d}"))
            c.append(mk(f"T{t}", outcome, rr=1.9, date=f"2021-03-{i + 1:02d}"))
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    clause = res.clause("geometry")
    assert clause.verdict == "FAIL"
    assert clause.value == pytest.approx(5.0, abs=1e-9)   # the worse of the two drops
    assert res.verdict == "FAIL"


def test_win_rate_clause_rejects_a_positive_but_insignificant_delta():
    """28 of 30 tickers are unchanged (40% WR in both arms). Exactly 2
    tickers are bumped from 4/10 wins to 5/10 wins in the component arm
    only -- a real but small, thinly-supported effect.

    Computed via bootstrap_delta(..., n_resamples=300, seed=42):
        point = +0.6667pp   (> 0 -- there IS a positive delta)
        p_greater_than_zero = 0.1567   (>= alpha=0.05 -- NOT significant;
                                         most ticker-resamples draw neither
                                         bumped ticker and land at delta 0)

    `point > 0 and p < alpha` = True and False = FAIL is the only correct
    reading. `point > 0 or p < alpha` = True or False = True would PASS --
    the mutation this kills.
    """
    b, c = [], []
    for t in range(30):
        for i in range(10):
            base_outcome = "win" if i < 4 else "loss"
            b.append(mk(f"T{t}", base_outcome, date=f"2021-03-{i + 1:02d}"))
            if t < 2:
                comp_outcome = "win" if i < 5 else "loss"   # bumped: 50% WR
            else:
                comp_outcome = base_outcome                  # unchanged: 40% WR
            c.append(mk(f"T{t}", comp_outcome, date=f"2021-03-{i + 1:02d}"))
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    clause = res.clause("win_rate")
    assert clause.verdict == "FAIL"
    assert clause.value == pytest.approx(0.6667, abs=1e-3)
    assert clause.value > 0.0
    assert res.verdict == "FAIL"


def test_mechanism_clause_rejects_a_removed_population_with_positive_expectancy():
    """Each ticker's 20 baseline trades: 2 big winners (r=+10), 6 normal
    winners (r=+2), 12 losses (r=-1) -- WR 40%. The component removes the
    2 big winners and 8 of the 12 losses, keeping the 6 normal winners and
    4 losses (retained WR 60%).

    Removed population (2 win / 8 loss per ticker):
        removed WR  = 20.00%   (< retained WR of 60.00%)
        removed ExpR = (2*10 - 8*1) / 10 = +1.2000R   (> 0 -- the removed
                                                         trades were net
                                                         PROFITABLE despite
                                                         their low win rate)

    `r_wr < k_wr and r_exp <= 0.0` = True and False = FAIL is the only
    correct reading: a feature that cuts a profitable (if low-win-rate)
    population is not earning its win-rate gain, it is discarding edge.
    `r_wr < k_wr or r_exp <= 0.0` = True or False = True would PASS --
    the mutation this kills.
    """
    b, c = [], []
    for t in range(30):
        trades = []
        for i in range(2):                                    # 2 big winners
            trades.append(mk(f"T{t}", "win", r=10.0, date=f"2021-03-{i + 1:02d}"))
        for i in range(2, 8):                                  # 6 normal winners
            trades.append(mk(f"T{t}", "win", r=2.0, date=f"2021-03-{i + 1:02d}"))
        for i in range(8, 20):                                 # 12 losses
            trades.append(mk(f"T{t}", "loss", r=-1.0, date=f"2021-03-{i + 1:02d}"))
        b.extend(trades)
        removed_idx = set([0, 1] + list(range(8, 16)))         # 2 big win + 8 loss
        for i, trade in enumerate(trades):
            if i not in removed_idx:
                c.append(trade)
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    clause = res.clause("mechanism")
    assert clause.verdict == "FAIL"
    assert clause.value == pytest.approx(20.0, abs=1e-9)       # removed WR
    assert clause.threshold == pytest.approx(60.0, abs=1e-9)   # retained WR
    assert res.verdict == "FAIL"
