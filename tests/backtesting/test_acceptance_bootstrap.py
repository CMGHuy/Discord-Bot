# tests/backtesting/test_acceptance_bootstrap.py
"""The bootstrap resamples TICKERS, not trades.

Trades on one symbol share a price path. Treating them as independent
overstates power -- the failure that let v68 fire a one-shot budget at a
+0.0104R effect against a +-0.05R standard error.
"""
import numpy as np

from swingbot.core.backtesting.acceptance import (
    ArmTrade, bootstrap_delta, cluster_bootstrap, delta_expectancy_r,
    delta_standardised_win_rate, win_rate,
)


def pop(n_tickers, per_ticker, win_frac, r_win=2.0, r_loss=-1.0, tag=""):
    """A population with an exact win fraction per ticker."""
    out = []
    for t in range(n_tickers):
        for i in range(per_ticker):
            is_win = i < int(per_ticker * win_frac)
            out.append(ArmTrade(
                ticker=f"{tag}T{t}", strategy="MACD", horizon_key="3m",
                entry_date=f"2021-01-{(i % 28) + 1:02d}",
                outcome="win" if is_win else "loss",
                r_multiple=r_win if is_win else r_loss, planned_rr=2.0))
    return out


def test_bootstrap_is_deterministic_under_a_fixed_seed():
    b, c = pop(20, 10, 0.4), pop(20, 10, 0.5)
    a = cluster_bootstrap(b, c, delta_standardised_win_rate,
                          n_resamples=200, seed=42)
    d = cluster_bootstrap(b, c, delta_standardised_win_rate,
                          n_resamples=200, seed=42)
    assert np.array_equal(a, d)


def test_a_different_seed_gives_a_different_draw():
    # NOTE: `pop()` gives every ticker the identical win fraction, which
    # makes the delta invariant to which tickers get drawn (see
    # `hetero_pop`'s docstring below) -- a fixed data bug, not a bootstrap
    # bug, since a whole-ticker resample of an all-identical population is
    # provably deterministic regardless of seed. Per-ticker win counts here
    # vary (and the baseline/component shift is non-uniform across
    # tickers), so which tickers land in a draw actually changes the
    # statistic.
    b = hetero_pop(20, 10, [1, 3, 5, 7, 2, 4, 6, 8, 3, 5])
    c = hetero_pop(20, 10, [3, 4, 5, 6, 7, 2, 8, 1, 6, 2])
    a = cluster_bootstrap(b, c, delta_standardised_win_rate,
                          n_resamples=200, seed=42)
    d = cluster_bootstrap(b, c, delta_standardised_win_rate,
                          n_resamples=200, seed=7)
    assert not np.array_equal(a, d)


def test_identical_arms_give_a_zero_delta_and_a_useless_p_value():
    b = pop(20, 10, 0.4)
    res = bootstrap_delta(b, list(b), delta_standardised_win_rate,
                          n_resamples=200, seed=42)
    assert abs(res.point) < 1e-9
    assert res.p_greater_than_zero > 0.5      # cannot beat its own self


def test_a_large_real_improvement_is_significant():
    b = pop(30, 20, 0.30)
    c = pop(30, 20, 0.70)
    res = bootstrap_delta(b, c, delta_standardised_win_rate,
                          n_resamples=500, seed=42)
    assert res.point > 30.0
    assert res.p_greater_than_zero < 0.05
    assert res.lo > 0.0


def hetero_pop(n_tickers, per_ticker, win_counts, tag=""):
    """Like `pop`, but each ticker gets its own win count (cycled through
    `win_counts`). Heterogeneous tickers are what make cluster count
    matter -- if every ticker were identical, resampling tickers would
    return the same population every draw and the bootstrap would show
    zero variance regardless of how many clusters there are.
    """
    out = []
    for t in range(n_tickers):
        wins = win_counts[t % len(win_counts)]
        for i in range(per_ticker):
            is_win = i < wins
            out.append(ArmTrade(
                ticker=f"{tag}T{t}", strategy="MACD", horizon_key="3m",
                entry_date=f"2021-01-{(i % 28) + 1:02d}",
                outcome="win" if is_win else "loss",
                r_multiple=2.0 if is_win else -1.0, planned_rr=2.0))
    return out


def test_clustering_widens_the_interval_versus_pretending_independence():
    """Identical trade counts and identical pooled win rates -- 4 tickers
    x 100 trades against 40 tickers x 10, same underlying per-ticker rates
    just chunked into 4 big clusters versus 40 small ones. The 4-cluster
    interval must be WIDER: that is the within-symbol correlation being
    priced instead of ignored, and it is exactly the inflation that let a
    0.0104R effect look meaningful.
    """
    # NOTE: the component win counts are a non-uniform shift over the
    # baseline's ([+10, +20, -10, +40] pp rather than a flat +10pp on every
    # ticker) -- a UNIFORM per-ticker shift makes the delta invariant to
    # which tickers a draw lands on (see `hetero_pop`'s docstring), which
    # collapses both intervals to zero width and hides the very effect this
    # test exists to show.
    few = hetero_pop(4, 100, [20, 40, 60, 30])
    few_c = hetero_pop(4, 100, [30, 60, 50, 70])
    many = hetero_pop(40, 10, [2, 4, 6, 3])
    many_c = hetero_pop(40, 10, [3, 6, 5, 7])
    # Same N and same pooled win rate on both sides of the comparison.
    assert len(few) == len(many) == 400
    assert abs(win_rate(few) - win_rate(many)) < 1e-9

    wide = bootstrap_delta(few, few_c, delta_standardised_win_rate,
                           n_resamples=500, seed=42)
    narrow = bootstrap_delta(many, many_c, delta_standardised_win_rate,
                             n_resamples=500, seed=42)
    assert (wide.hi - wide.lo) > (narrow.hi - narrow.lo)


def test_expectancy_delta_tracks_the_r_multiples():
    b = pop(20, 10, 0.50, r_win=2.0, r_loss=-1.0)
    c = pop(20, 10, 0.50, r_win=3.0, r_loss=-1.0)
    assert delta_expectancy_r(b, c) > 0.4


def test_coverage_is_about_95_percent_on_a_known_delta():
    """Acceptance criterion 2 from the spec: the 95% interval must contain
    the true value about 95% of the time. 200 draws, not 1000, so the test
    stays under the ~7s per-file budget -- the tolerance is widened to
    match rather than the claim weakened."""
    rng = np.random.default_rng(2026)
    hits = 0
    trials = 200
    for _ in range(trials):
        b, c = [], []
        for t in range(25):
            for i in range(8):
                bw = rng.random() < 0.40
                cw = rng.random() < 0.50
                for arm, is_win in ((b, bw), (c, cw)):
                    arm.append(ArmTrade(
                        ticker=f"T{t}", strategy="MACD", horizon_key="3m",
                        entry_date=f"2021-02-{i + 1:02d}",
                        outcome="win" if is_win else "loss",
                        r_multiple=2.0 if is_win else -1.0, planned_rr=2.0))
        res = bootstrap_delta(b, c, delta_standardised_win_rate,
                              n_resamples=200, seed=int(rng.integers(1e6)))
        if res.lo <= 10.0 <= res.hi:      # true delta is 50 - 40 = 10pp
            hits += 1
    assert 0.88 <= hits / trials <= 1.0
