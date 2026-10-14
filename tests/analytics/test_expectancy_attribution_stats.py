"""v146 study statistics: the week-clustered tercile spread, per-factor
deltas, bucket looks, BH over every look and the pre-registered verdict, on
synthetic populations built to be predictive, flat and inverted."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.market.strategy_types import HORIZONS

HK = next(iter(HORIZONS))
SEED = 42
MONO_KEYS = ["n", "spearman_rho", "tercile_spread", "ci_low", "ci_high", "p",
             "inverted", "tercile_n", "rr_by_tercile"]


def population(kind: str, n: int = 180) -> list[dict]:
    """Deterministic rows: score i (distinct), R = slope * (rank - 0.5) plus a
    fixed zero-mean wobble, spread over 30 entry weeks. ``predictive`` has a
    +0.4R top-minus-bottom tercile spread, ``inverted`` -0.4R, ``flat`` none."""
    slope = {"predictive": 0.6, "flat": 0.0, "inverted": -0.6}[kind]
    rows = []
    for i in range(n):
        r = slope * (i / (n - 1) - 0.5) + ((i * 37) % 11 - 5) / 10.0
        points = {"MACD momentum": 10 if i >= n // 2 else 0,
                  "ADX trend strength": 7 if i % 5 == 0 else (15 if i % 2 else 0)}
        if i % 3 == 0:
            points["Tight stop penalty"] = -5
        rows.append({
            "r": r, "r_gross": r + 0.03,
            "week": (dt.date(2024, 1, 1) + dt.timedelta(weeks=i % 30)).isoformat(),
            "confidence_score": i, "confidence_level": 3 + (3 * i) // n,
            "confidence_points": points,
            "confidence_unevaluated": ["ADX trend strength"] if i % 5 == 0 else [],
            "confluence_count": 2 + i % 3, "regime2_state": "bull_quiet",
            "rs_pctile": float(i % 100),
            "direction": "bullish" if i % 3 else "bearish", "horizon": HK,
            "earnings_sessions": i % 40, "earnings_status": "known",
            "risk_reward_ratio": 1.5 + (i % 4) / 4.0,
        })
    return rows


@pytest.fixture(autouse=True)
def few_resamples(monkeypatch):
    monkeypatch.setattr(ea, "N_RESAMPLES", 300)


def test_a_predictive_population_passes_its_clause():
    mono = ea.monotonicity(population("predictive"), seed=SEED)
    assert list(mono) == MONO_KEYS
    assert mono["n"] == 180 and mono["tercile_n"] == [60, 60, 60]
    assert mono["tercile_spread"] == pytest.approx(0.4, abs=0.05)
    assert 0 < mono["ci_low"] < mono["tercile_spread"] < mono["ci_high"]
    assert mono["spearman_rho"] > 0.2 and mono["p"] < 0.05
    assert mono["inverted"] is False
    assert len(mono["rr_by_tercile"]) == 3 and set(mono["rr_by_tercile"][0]) == {"p25", "median", "p75"}
    assert ea.population_passes(mono) is True


def test_a_flat_population_fails_its_clause():
    mono = ea.monotonicity(population("flat"), seed=SEED)
    assert abs(mono["tercile_spread"]) < 0.10
    assert mono["inverted"] is False
    assert ea.population_passes(mono) is False


def test_an_inverted_population_is_flagged_and_fails():
    mono = ea.monotonicity(population("inverted"), seed=SEED)
    assert mono["ci_high"] < 0 and mono["inverted"] is True
    assert mono["spearman_rho"] < 0
    assert ea.population_passes(mono) is False


def test_the_same_seed_reproduces_the_interval():
    rows = population("predictive")
    first, second = ea.monotonicity(rows, seed=7), ea.monotonicity(rows, seed=7)
    assert (first["ci_low"], first["ci_high"], first["p"]) == (
        second["ci_low"], second["ci_high"], second["p"])


def test_tercile_cuts_are_fixed_once_on_the_full_sample(monkeypatch):
    calls = []
    real = ea.quantile_bins

    def counting(values, k):
        calls.append((len(values), k))
        return real(values, k)

    monkeypatch.setattr(ea, "quantile_bins", counting)
    ea.monotonicity(population("predictive"), seed=SEED)
    assert calls == [(180, 3)]          # never once per bootstrap resample


def test_unscored_rows_stay_out_of_the_confidence_analysis():
    rows = population("predictive")
    extra = [dict(row, confidence_score=None, r=-5.0) for row in rows[:50]]
    assert ea.monotonicity(rows + extra, seed=SEED) == ea.monotonicity(rows, seed=SEED)


def test_a_thin_tercile_gets_no_interval_and_fails_the_clause():
    mono = ea.monotonicity(population("predictive", n=60), seed=SEED)
    assert mono["tercile_n"] == [20, 20, 20]
    assert mono["tercile_spread"] > 0.3            # the point estimate is still shown
    assert mono["ci_low"] is None and mono["ci_high"] is None and mono["p"] is None
    assert ea.population_passes(mono) is False


def test_whole_weeks_are_resampled():
    # One entry week: every resample is the same week repeated, so the
    # interval collapses onto the point estimate. Row-level resampling would not.
    rows = [dict(row, week="2024-03-04") for row in population("predictive")]
    mono = ea.monotonicity(rows, seed=SEED)
    assert mono["ci_low"] == pytest.approx(mono["tercile_spread"])
    assert mono["ci_high"] == pytest.approx(mono["tercile_spread"])


def test_bootstrap_p_is_two_sided_with_the_plus_one_correction(monkeypatch):
    monkeypatch.setattr(ea.stats, "week_cluster_bootstrap",
                        lambda *args, **kwargs: np.array([1.0, 1.0, 1.0, -1.0]))
    mono = ea.monotonicity(population("predictive"), seed=SEED)
    assert mono["p"] == pytest.approx(2 * (1 + 1) / (4 + 1))   # one draw <= 0, of four


def test_factor_deltas_cover_every_key_and_skip_unevaluated_rows():
    factors = {item["key"]: item for item in ea.factor_deltas(population("predictive"), seed=SEED)}
    assert list(factors) == ["ADX trend strength", "MACD momentum", "Tight stop penalty"]
    assert list(factors["MACD momentum"]) == ["key", "n", "n_pos", "n_zero", "delta",
                                              "ci_low", "ci_high", "p", "q"]
    adx = factors["ADX trend strength"]
    assert adx["n"] == 144                              # 36 fallback rows left out
    assert adx["n_pos"] + adx["n_zero"] == 144
    macd = factors["MACD momentum"]
    assert (macd["n_pos"], macd["n_zero"]) == (90, 90)
    assert macd["delta"] == pytest.approx(0.3, abs=0.05) and macd["ci_low"] > 0
    assert macd["q"] is None                            # assign_qvalues fills it


def test_a_penalty_key_reads_zero_when_absent_but_other_keys_do_not():
    rows = population("predictive")
    other_scorer = [dict(row, confidence_points={"gap": 0}) for row in rows[:30]]
    factors = {item["key"]: item for item in ea.factor_deltas(rows + other_scorer, seed=SEED)}
    penalty = factors["Tight stop penalty"]
    assert (penalty["n_pos"], penalty["n_zero"]) == (60, 150)   # absent = not applied
    assert factors["MACD momentum"]["n"] == 180                 # the other scorer's rows are out
    assert factors["gap"]["n_pos"] == 0 and factors["gap"]["p"] is None


def test_bucket_looks_fill_the_interval_on_non_thin_buckets_only():
    rows = population("predictive")
    buckets = ea.population_buckets(rows)
    ea.bucket_looks(rows, buckets, seed=SEED)
    bearish, bullish = buckets["direction"]
    assert (bearish["label"], bullish["label"]) == ("bearish", "bullish")
    assert bearish["delta"] == pytest.approx(bearish["exp_r"] - bullish["exp_r"])
    assert bearish["ci_low"] <= bearish["delta"] <= bearish["ci_high"]
    assert 0 < bearish["p"] <= 1
    for decile in buckets["confidence_decile"]:               # 18 rows each: thin
        assert decile["thin"] and decile["p"] is None and decile["ci_low"] is None
    lone = buckets["regime2_state"][0]                        # nothing to compare against
    assert lone["delta"] is None and lone["p"] is None


def _population_dict(rows):
    buckets = ea.population_buckets(rows)
    ea.bucket_looks(rows, buckets, seed=SEED)
    return {"monotonicity": ea.monotonicity(rows, seed=SEED),
            "factors": ea.factor_deltas(rows, seed=SEED), "buckets": buckets,
            "splits": {"direction": {"bullish": ea.monotonicity(
                [row for row in rows if row["direction"] == "bullish"], seed=SEED)}}}


def test_assign_qvalues_runs_bh_over_every_look_of_both_populations():
    populations = {"live": _population_dict(population("flat")),
                   "train": _population_dict(population("predictive"))}
    holders = [holder for name in ("live", "train")
               for holder, _ in ea._look_holders(populations[name])]
    expected = sum(1 for holder in holders if holder.get("p") is not None)
    looks = ea.assign_qvalues(populations)
    assert looks == expected and looks > 10
    for name in ("live", "train"):
        assert "q" not in populations[name]["monotonicity"]
        takers = populations[name]["factors"] + [
            bucket for grouping in populations[name]["buckets"].values() for bucket in grouping]
        for item in takers:
            assert (item["q"] is None) == (item["p"] is None)
            if item["p"] is not None:
                assert item["p"] <= item["q"] <= 1.0


def test_assign_qvalues_accepts_a_missing_population():
    populations = {"live": None, "train": _population_dict(population("predictive"))}
    assert ea.assign_qvalues(populations) > 0


@pytest.mark.parametrize("spread, low, tercile_n, expected", [
    (0.10, 0.01, [30, 30, 30], True),      # exactly at both floors
    (0.0999, 0.01, [30, 30, 30], False),   # point estimate under +0.10R
    (0.25, 0.0, [30, 30, 30], False),      # lower bound must be > 0, not >= 0
    (0.25, 0.05, [30, 29, 30], False),     # any tercile under 30
    (0.25, None, [60, 60, 60], False),     # no interval
])
def test_population_passes_is_the_pre_registered_clause(spread, low, tercile_n, expected):
    mono = {"tercile_spread": spread, "ci_low": low, "ci_high": 1.0, "tercile_n": tercile_n}
    assert ea.population_passes(mono) is expected


def test_population_passes_refuses_a_missing_population():
    assert ea.population_passes(None) is False
    assert ea.population_passes({}) is False


def test_verdict_counts_the_populations_that_pass():
    good = ea.monotonicity(population("predictive"), seed=SEED)
    flat = ea.monotonicity(population("flat"), seed=SEED)
    inverted = ea.monotonicity(population("inverted"), seed=SEED)
    assert ea.verdict(good, good) == "PREDICTIVE"
    assert ea.verdict(good, flat) == "WEAK"
    assert ea.verdict(inverted, good) == "WEAK"
    assert ea.verdict(flat, inverted) == "NOT PREDICTIVE"
    assert ea.verdict(None, good) == "WEAK"
    assert ea.verdict(None, None) == "NOT PREDICTIVE"
