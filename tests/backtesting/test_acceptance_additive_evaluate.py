"""v238 additive gate (v230 spec Part C): Stage 0 and evaluate_additive."""
from datetime import date, timedelta

import pytest

from swingbot.core.backtesting import acceptance_additive as aa
from swingbot.core.backtesting.acceptance import ArmTrade, render_json

FAST = dict(n_resamples=300, seed=42)


def _row(ticker, r, *, day=0, year=2021, strategy="Turtle Soup", source="strategy"):
    entry = date(year, 1, 4) + timedelta(days=day)
    outcome = "win" if r > 0 else ("loss" if r < 0 else "scratch")
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key="4w",
                    entry_date=entry.isoformat(), outcome=outcome, r_multiple=r,
                    planned_rr=2.0, source=source, direction="bullish")


def _baseline(weeks=20, year=2021):
    return [_row(f"B{w}", 1.0 if w % 2 else -1.0, day=7 * w, year=year,
                 strategy="RSI", source="confluence") for w in range(weeks)]


def _added(pattern, weeks=30, year=2021):
    return [_row(f"T{w}-{j}", r, day=7 * w, year=year)
            for w in range(weeks) for j, r in enumerate(pattern)]


PAYING = (2.2, -1.0, -1.0)     # own ExpR +0.067R every week, WR 33% vs break-even 31.25%
LOSING = (1.0, -1.0, -1.0)     # own ExpR -0.33R


def _fold(year, r=0.5, n=40):
    base = _baseline(5, year=int(year))
    return {"test_year": year, "baseline": base,
            "component": base + [_row(f"F{i}", r, day=7 * (i % 40), year=int(year))
                                 for i in range(n)]}


FOLDS = [_fold("2021"), _fold("2022"), _fold("2023")]


# --- Stage 0 --------------------------------------------------------------------------

def test_mde_is_the_two_sided_95_plus_power_z_over_root_n():
    assert aa.mde_own_expectancy(n=100, sd_r=1.0) == pytest.approx((1.96 + 0.8416) / 10.0)
    assert aa.mde_own_expectancy(n=400, sd_r=2.0) == pytest.approx((1.96 + 0.8416) / 10.0)


def test_mde_is_undefined_without_rows_and_refuses_bad_inputs():
    assert aa.mde_own_expectancy(n=0, sd_r=1.0) is None
    with pytest.raises(ValueError):
        aa.mde_own_expectancy(n=100, sd_r=-0.1)
    with pytest.raises(ValueError):
        aa.mde_own_expectancy(n=100, sd_r=float("nan"))
    with pytest.raises(ValueError):
        aa.mde_own_expectancy(n=100, sd_r=1.0, power=0.85)


def test_stage0_passes_when_the_frozen_effect_clears_the_mde():
    assert aa.stage0_refusal(n=100, expected_r=0.30, sd_r=1.0) is None


def test_stage0_passes_when_the_mde_equals_the_frozen_effect():
    mde = aa.mde_own_expectancy(n=100, sd_r=1.0)
    assert aa.stage0_refusal(n=100, expected_r=mde, sd_r=1.0) is None


def test_stage0_refuses_when_the_mde_exceeds_the_frozen_effect():
    refusal = aa.stage0_refusal(n=100, expected_r=0.25, sd_r=1.0)
    assert refusal.startswith(aa.STAGE0_REFUSAL)
    assert "exceeds" in refusal and "budget intact" in refusal


@pytest.mark.parametrize("n, expected_r", [(0, 0.30), (100, 0.0), (100, -0.1)])
def test_stage0_refuses_no_rows_or_a_non_positive_effect(n, expected_r):
    refusal = aa.stage0_refusal(n=n, expected_r=expected_r, sd_r=1.0)
    assert refusal.startswith(aa.STAGE0_REFUSAL)
    assert "budget intact" in refusal


# --- evaluate_additive ----------------------------------------------------------------

def test_stage_clauses_are_pinned():
    assert aa.STAGE_CLAUSES == {"selection": aa.CLAUSES[:3],
                                "walkforward": aa.CLAUSES[3:],
                                "validation": aa.CLAUSES}


def test_selection_runs_clauses_one_to_three_and_passes_a_paying_add():
    base = _baseline()
    res = aa.evaluate_additive(base, base + _added(PAYING), stage="selection", **FAST)
    assert tuple(c.name for c in res.clauses) == aa.CLAUSES[:3]
    assert res.clause("book_net_gain").verdict == "SKIPPED"   # no displacement
    assert res.verdict == "PASS"
    assert (res.version, res.cluster, res.stage) == (1, "week", "selection")
    assert res.split == {"added": 90, "displaced": 0}
    assert render_json(res)["cluster"] == "week"


def test_a_losing_add_fails_selection():
    base = _baseline()
    res = aa.evaluate_additive(base, base + _added(LOSING), stage="selection", **FAST)
    assert res.clause("own_expectancy").verdict == "FAIL"
    assert res.verdict == "FAIL"


def test_walkforward_runs_only_stability():
    base = _baseline()
    res = aa.evaluate_additive(base, base + _added(PAYING), stage="walkforward",
                               folds=FOLDS, **FAST)
    assert tuple(c.name for c in res.clauses) == ("stability",)
    assert res.verdict == "PASS"


def test_validation_runs_all_four_clauses():
    base = _baseline()
    res = aa.evaluate_additive(base, base + _added(PAYING), stage="validation",
                               folds=FOLDS, **FAST)
    assert tuple(c.name for c in res.clauses) == aa.CLAUSES
    assert res.verdict == "PASS"


@pytest.mark.parametrize("stage", ["walkforward", "validation"])
def test_a_clause_four_stage_without_folds_is_refused(stage):
    base = _baseline()
    with pytest.raises(ValueError, match="needs folds"):
        aa.evaluate_additive(base, base + _added(PAYING), stage=stage, **FAST)


def test_an_unknown_stage_is_refused():
    base = _baseline()
    with pytest.raises(ValueError, match="stage must be one of"):
        aa.evaluate_additive(base, base + _added(PAYING), stage="mde", **FAST)


def test_misuse_raises_with_its_reason():
    base = _baseline()
    with pytest.raises(aa.AdditiveMisuse) as caught:
        aa.evaluate_additive(base, base[3:], stage="selection", **FAST)
    assert caught.value.reason.startswith(aa.ADDITIVE_GATE_MISUSE)
    assert isinstance(caught.value, ValueError)
