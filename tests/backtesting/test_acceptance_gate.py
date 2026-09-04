# tests/backtesting/test_acceptance_gate.py
"""The pre-registered clause set.

Clause 3 is the load-bearing one: without it, 'win rate up, expectancy
flat' is passed trivially by pulling targets nearer, and the repo ships a
stream of features that feel better and earn identically.
"""
from swingbot.core.backtesting.acceptance import (
    ArmTrade, evaluate, mean_win_r, median_planned_rr, population_split,
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
