import sys
import types

import swingbot.core.gate.folds as folds


def test_fold_windows_anchored():
    windows = folds.fold_windows()
    assert [w["year"] for w in windows] == [2021, 2022, 2023]
    for w in windows:
        assert w["test_start"] == f"{w['year']}-01-01"
        assert w["test_end"] == f"{w['year']}-12-31"
        assert w["train_end"] < w["test_start"]       # anchored, no overlap


def test_apply_fold_gate_math():
    base = [{"year": y, "n": 100, "wr": 60.0, "expectancy_r": 0.30} for y in (2021, 2022, 2023)]
    good = [{"year": y, "n": 60, "wr": 68.0, "expectancy_r": 0.32} for y in (2021, 2022, 2023)]
    assert folds.apply_fold_gate(good, base)["passes_gate"] is True
    one_fold_degrades = [dict(good[0]), dict(good[1]),
                         {"year": 2023, "n": 60, "wr": 68.0, "expectancy_r": 0.20}]
    verdict = folds.apply_fold_gate(one_fold_degrades, base)
    assert verdict["passes_gate"] is False            # > 0.05R degradation
    small_n = [dict(r, n=20) for r in good]
    assert folds.apply_fold_gate(small_n, base)["passes_gate"] is False
    only_one_improves = [dict(good[0]),
                         {"year": 2022, "n": 60, "wr": 55.0, "expectancy_r": 0.30},
                         {"year": 2023, "n": 60, "wr": 58.0, "expectancy_r": 0.30}]
    assert folds.apply_fold_gate(only_one_improves, base)["passes_gate"] is False


def test_run_folds_with_stub_replay():
    def replay(strategy, ticker, start, end, min_tier):
        year = int(start[:4])
        wins = {"2021": 6, "2022": 7, "2023": 8}[str(year)]
        return ([{"outcome": "win", "r_multiple": 1.5}] * wins
                + [{"outcome": "loss", "r_multiple": -1.0}] * 4)

    result = folds.run_folds("VWAP", tickers=["T1", "T2"], replay=replay)
    assert [f["year"] for f in result["folds"]] == [2021, 2022, 2023]
    assert result["folds"][0]["n"] == 20              # 2 tickers x 10 trades
    assert result["folds"][0]["wr"] == 60.0           # 12/20
    assert result["pooled"]["n"] == 66
    assert result["strategy"] == "VWAP"


def test_delegates_to_edge_engine_when_present(monkeypatch):
    fake = types.ModuleType("swingbot.core.backtest_wf")
    fake.run_walk_forward = lambda strategy, gate_min_tier=None: {"delegated": strategy}
    monkeypatch.setitem(sys.modules, "swingbot.core.backtest_wf", fake)
    assert folds.run_folds("VWAP")["delegated"] == "VWAP"


def test_ablation_loop_mechanics():
    from swingbot.core.gate.folds import ablate_flags

    trades = ([{"outcome": "loss", "r_multiple": -1.0, "fired_flags": ["rf_dead_cat"]}] * 10
              + [{"outcome": "win", "r_multiple": 1.5, "fired_flags": []}] * 30
              + [{"outcome": "loss", "r_multiple": -1.0, "fired_flags": []}] * 10)
    rows = ablate_flags(trades, flags=["rf_dead_cat", "rf_opex_pin"])
    dead_cat = next(r for r in rows if r["flag"] == "rf_dead_cat")
    # removing rf_dead_cat trades: 50 -> 40 signals (20% removed), WR 60 -> 75
    assert dead_cat["signals_removed_pct"] == 20.0
    assert dead_cat["wr_delta"] == 15.0
    assert dead_cat["expectancy_delta"] > 0
    opex = next(r for r in rows if r["flag"] == "rf_opex_pin")
    assert opex["signals_removed_pct"] == 0.0 and opex["wr_delta"] == 0.0


def test_no_delegation_against_the_real_backtest_wf_module():
    """swingbot/core/backtest_wf.py (edge-engine E39) already exists in this
    repo, but it exposes its own differently-shaped run_folds(overrides, ...)
    -- not run_walk_forward(strategy, gate_min_tier=...). A bare
    `except ImportError` around `backtest_wf.run_walk_forward(...)` would
    import successfully (the module exists) and then blow up with an
    unhandled AttributeError instead of falling through to the fallback.
    This pins the real, non-monkeypatched module to prove the hasattr guard
    is actually there and not just satisfied by the stub test above."""
    import swingbot.core.backtest_wf as real_wf
    assert not hasattr(real_wf, "run_walk_forward")


import random

from swingbot.core.gate.folds import permutation_test


def _rigged(n=200):
    return [{"gate_score": i / 2.0,
             "outcome": "win" if i >= 80 else "loss",
             "r_multiple": 1.5 if i >= 80 else -1.0} for i in range(n)]


def _noise(n=200, seed=7):
    rng = random.Random(seed)
    return [{"gate_score": rng.uniform(0, 100),
             "outcome": rng.choice(["win", "loss"]),
             "r_multiple": rng.choice([1.5, -1.0])} for _ in range(n)]


def test_rigged_monotone_tiny_p():
    assert permutation_test(_rigged(), n=500, seed=1)["p_value"] < 0.01


def test_noise_large_p():
    assert permutation_test(_noise(), n=500, seed=1)["p_value"] >= 0.05


from swingbot.core.gate.folds import overfit_sentinel


def test_overfit_sentinel_rules():
    healthy = {"pooled": {"n": 120, "wr": 68.0, "expectancy_r": 0.3}}
    assert overfit_sentinel(healthy, train_wr=72.0, pct_kept=55.0) == []
    # train-test gap > 12 pts
    warns = overfit_sentinel(healthy, train_wr=85.0, pct_kept=55.0)
    assert any("overfit" in w for w in warns)
    # over-filtered to anecdotes
    warns = overfit_sentinel(healthy, train_wr=72.0, pct_kept=10.0)
    assert any("anecdotes" in w for w in warns)
    # thin pooled evidence
    warns = overfit_sentinel({"pooled": {"n": 50, "wr": 68.0}}, train_wr=None,
                             pct_kept=None)
    assert any("N=50" in w for w in warns)
