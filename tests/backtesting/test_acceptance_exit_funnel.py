"""v129 funnel: Stage 0 paired MDE, Stage 1 plateau selection, Stage 2 fold
reversal, Stage 3 one-shot gate, and the disclosure report. Synthetic rows
with uniform lifts make every bootstrap draw equal the lift, so each verdict
is checkable by hand."""
import pytest

from swingbot.core.backtesting import acceptance_exit_funnel as funnel
from swingbot.core.backtesting.acceptance_replay import CELLS, cell_key
from tests.backtesting.acceptance_rows import lifted_rows, record, row

N = 200   # bootstrap resamples: tests only, never a real run

Z_KEYS = [cell_key(m, b) for m, b in CELLS["Z"]]
PLATEAU = {"m0.5_b0": 0.10, "m0.5_b0.25": 0.05, "m1_b0": 0.30,
           "m1_b0.25": 0.25, "m1.5_b0": 0.20, "m1.5_b0.25": 0.15}


def test_frozen_constants():
    assert funnel.TRAIN == ("2020-01-01", "2023-12-31")
    assert funnel.VALIDATION == ("2024-01-01", "2025-12-31")
    assert (funnel.TRAIN_DAYS, funnel.VALIDATION_DAYS) == (1460, 730)
    assert funnel.MDE_CEILING_R == 0.10 and funnel.MDE_POWER == 0.80
    assert funnel.FOLD_YEARS == (2020, 2021, 2022, 2023)
    assert (funnel.PERMUTATION_N, funnel.PERMUTATION_SEED) == (200, 42)


def test_arm_trades_drops_untriggered_side_only():
    rows = [
        row(record("A", "2021-01-15", "loss", -1.0), {"b0": record("A", "2021-01-15", "win", 1.0)}),
        row(None, {"b0": record("B", "2021-02-15", "win", 1.5)}),
        row(record("C", "2021-03-15", "win", 2.0), {"b0": None}),
    ]
    baseline, component = funnel.arm_trades(rows, "b0")
    assert [t.ticker for t in baseline] == ["A", "C"]
    assert [t.ticker for t in component] == ["A", "B"]


# --- Stage 0 ----------------------------------------------------------------

def test_stage0_powered_when_every_cell_clears_the_ceiling():
    out = funnel.stage0(lifted_rows("Z", PLATEAU), "Z")
    assert out["verdict"] == "POWERED"
    assert [c["cell"] for c in out["cells"]] == Z_KEYS
    assert all(c["observed_n"] == 80 and c["target_n"] == 40 for c in out["cells"])
    assert all(c["mde_r"] == pytest.approx(0.0) for c in out["cells"])


def test_stage0_underpowered_when_one_cell_is_noisy():
    rows = lifted_rows("B", {"b0": 0.3, "b0.25": 0.3})
    noisy = lifted_rows("B", {"b0.25": 0.3}, jitter=2.0)
    for target, source in zip(rows, noisy):
        target["cells"]["b0.25"] = source["cells"]["b0.25"]
    out = funnel.stage0(rows, "B")
    assert out["verdict"] == "UNDERPOWERED"
    by_cell = {c["cell"]: c for c in out["cells"]}
    assert by_cell["b0"]["powered"] is True
    assert by_cell["b0.25"]["powered"] is False
    assert by_cell["b0.25"]["mde_r"] > funnel.MDE_CEILING_R


def test_stage0_underpowered_when_the_mde_is_undefined():
    rows = lifted_rows("B", {"b0": 0.3, "b0.25": 0.3}, n_tickers=1, per_ticker=1)
    assert funnel.stage0(rows, "B")["verdict"] == "UNDERPOWERED"


# --- Stage 1 ----------------------------------------------------------------

def test_stage1_selects_the_highest_lower_bound_on_the_plateau():
    out = funnel.stage1(lifted_rows("Z", PLATEAU), "Z", n_resamples=N)
    assert out["verdict"] == "SELECTED"
    assert out["selected"] == {"cell": "m1_b0", "m": 1.0, "b": 0.0}
    assert all(c["eligible"] and c["plateau"] for c in out["cells"])


def test_stage1_skips_a_spike_with_an_ineligible_neighbour():
    lifts = dict(PLATEAU, **{"m1.5_b0": 0.50, "m1.5_b0.25": 0.0})
    out = funnel.stage1(lifted_rows("Z", lifts), "Z", n_resamples=N)
    by_cell = {c["cell"]: c for c in out["cells"]}
    assert by_cell["m1.5_b0"]["eligible"] is True
    assert by_cell["m1.5_b0"]["plateau"] is False      # its b neighbour failed
    assert by_cell["m1_b0.25"]["plateau"] is False     # its m neighbour failed
    assert out["selected"]["cell"] == "m1_b0"


def test_stage1_no_eligible_cell():
    out = funnel.stage1(lifted_rows("Z", {key: 0.0 for key in Z_KEYS}), "Z", n_resamples=N)
    assert out["verdict"] == "NO_ELIGIBLE_CELL" and out["selected"] is None


def test_stage1_arm_b_needs_both_cells():
    one = funnel.stage1(lifted_rows("B", {"b0": 0.3, "b0.25": 0.0}), "B", n_resamples=N)
    assert one["verdict"] == "NO_ELIGIBLE_CELL"
    both = funnel.stage1(lifted_rows("B", {"b0": 0.1, "b0.25": 0.3}), "B", n_resamples=N)
    assert both["selected"] == {"cell": "b0.25", "m": None, "b": 0.25}


# --- Stage 2 ----------------------------------------------------------------

def _years(lift_by_year):
    rows = []
    for year, lift in lift_by_year.items():
        rows += lifted_rows("B", {"b0": lift}, year=year)
    return rows


def test_stage2_passes_when_at_most_half_the_folds_reverse():
    out = funnel.stage2(_years({2020: 0.2, 2021: 0.2, 2022: -0.1, 2023: -0.1}), "B", "b0")
    assert out["verdict"] == "PASS"
    assert [f["reversed"] for f in out["folds"]] == [False, False, True, True]


def test_stage2_fails_when_most_folds_reverse():
    out = funnel.stage2(_years({2020: 0.2, 2021: -0.1, 2022: -0.1, 2023: -0.1}), "B", "b0")
    assert out["verdict"] == "FAIL"


def test_stage2_ignores_empty_folds_and_fails_with_none_measurable():
    out = funnel.stage2(_years({2021: 0.2, 2022: -0.1}), "B", "b0")
    assert out["verdict"] == "PASS" and out["measurable"] == 2
    assert funnel.stage2([], "B", "b0")["verdict"] == "FAIL"


# --- Stage 3 ----------------------------------------------------------------

def test_sign_flip_p_detects_a_uniform_lift_and_not_identity():
    lifted = funnel.arm_trades(lifted_rows("B", {"b0": 0.3}), "b0")
    same = funnel.arm_trades(lifted_rows("B", {"b0": 0.0}), "b0")
    assert funnel.sign_flip_p(*lifted) < 0.05
    assert funnel.sign_flip_p(*same) == 1.0
    assert funnel.sign_flip_p([], []) is None


def test_stage3_passes_a_real_lift_and_fails_a_null():
    good = funnel.stage3(lifted_rows("B", {"b0": 0.3}, year=2024), "B", "b0", n_resamples=N)
    assert good["verdict"] == "PASS" and good["permutation_p"] < 0.05
    names = {c["name"]: c["verdict"] for c in good["gate"]["clauses"]}
    assert names == {"expectancy_gain": "PASS", "win_rate_floor": "PASS",
                     "volume": "PASS", "permutation": "PASS"}
    null = funnel.stage3(lifted_rows("B", {"b0": 0.0}, year=2024), "B", "b0", n_resamples=N)
    assert null["verdict"] == "FAIL"


# --- disclosures ------------------------------------------------------------

def test_report_counts_flips_mix_and_disclosures():
    stuck = record("D", "2021-04-15", "loss", -1.0, gap=True)
    rows = [
        row(record("A", "2021-01-15", "loss", -1.0),
            {"m1_b0": record("A", "2021-01-15", "win", 1.5, rr=1.0, mix="tp1+runner_trail")}),
        row(record("B", "2021-02-15", "win", 2.0),
            {"m1_b0": record("B", "2021-02-15", "loss", -0.4, rr=1.0, mix="acceptance_exit")}),
        row(None, {"m1_b0": record("C", "2021-03-15", "win", 1.0, rr=1.0)}),
        row(stuck, {"m1_b0": stuck}, eligible=False),
    ]
    out = funnel.report(rows, "Z", "m1_b0", n_resamples=N)
    assert (out["n_baseline"], out["n_component"]) == (3, 4)
    assert out["flips"] == {"win_to_loss": 1, "loss_to_win": 1, "other": 0}
    assert out["exit_mix"]["component"] == {"tp1+runner_trail": 1, "acceptance_exit": 1,
                                            "tp1": 1, "stop": 1}
    assert out["exit_mix"]["baseline"] == {"stop": 2, "tp1": 1}
    assert out["not_eligible"] == 1
    assert out["gap_through"] == {"baseline": 1, "component": 1}
    assert (out["only_baseline_triggered"], out["only_cell_triggered"]) == (0, 1)
    assert out["per_horizon_n"] == {"4w": 4}
    assert out["median_planned_rr"] == {"baseline": 2.0, "component": 1.0}
    assert out["delta_expr"] == pytest.approx((1.5 - 0.4 + 1.0 - 1.0) / 4 - 0.0)
