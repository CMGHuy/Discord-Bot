"""v139 arm S funnel on synthetic rows: census verdicts, the paired MDE,
plateau selection over c with the ISO-week bootstrap, v129's fold rule, the
one-shot validation clauses and the disclosures."""
import pytest

from swingbot.core.backtesting import acceptance_exit_funnel as v129
from swingbot.core.backtesting import confluence_stop_funnel as funnel
from tests.backtesting.confluence_stop_rows import (KEYS, census_row, lifted_s_rows,
                                                    s_record, s_row)

N = 200
PLATEAU = {"c3": 0.1, "c4": 0.3, "c5": 0.2}


def test_frozen_constants():
    assert funnel.C_STEPS == (3.0, 4.0, 5.0)
    assert funnel.CLUSTER == "week"
    assert (funnel.TRAIN, funnel.VALIDATION) == (v129.TRAIN, v129.VALIDATION)
    assert funnel.MDE_CEILING_R == 0.10
    assert funnel.ELIGIBILITY_CLAUSES == ("expectancy_gain", "win_rate_floor", "volume")


# --- Stage -1 ---------------------------------------------------------------

def _census():
    return [census_row(None, ticker="T00"),
            census_row(2.5, (True, True, True), ticker="T01"),
            census_row(3.5, (False, True, True), ticker="T02"),
            census_row(4.5, (False, False, True), ticker="T03"),
            census_row(6.0, ticker="T04", horizon="3m", direction="bearish")]


def test_stage_minus1_counts_buckets_changes_and_drops():
    out = funnel.stage_minus1(_census())
    assert out["verdict"] == "REACHABLE"
    assert out["verdicts"] == {"S": "REACHABLE", "D": "REACHABLE"}
    totals = out["totals"]
    assert (totals["plans"], totals["clamped"]) == (5, 4)
    assert totals["d_buckets"] == {"2.5-3.0": 1, "3.5-4.0": 1, "4.5-5.0": 1, "6.0-6.5": 1}
    assert {k: v["changed"] for k, v in totals["arm_s"].items()} == {"c3": 1, "c4": 2, "c5": 3}
    assert {k: v["dropped"] for k, v in totals["arm_d"].items()} == {"c3": 3, "c4": 2, "c5": 1}
    assert set(out["by_stratum"]) == {"4w/bullish", "3m/bearish"}
    assert out["identical_adjacent"] == {"arm_s": [], "arm_d": []}


def test_stage_minus1_counts_a_rollback_as_applying_not_changing():
    out = funnel.stage_minus1([census_row(2.6, (False, True, True), ticker="T05",
                                          rollback=(True, False, False))])
    assert out["totals"]["arm_s"]["c3"] == {"applies": 1, "changed": 0, "rollback": 1}


def test_stage_minus1_zero_diff_closes_both_arms():
    out = funnel.stage_minus1([census_row(None, ticker=f"T{n}") for n in range(3)])
    assert out["verdict"] == "refused:zero-diff"
    assert out["verdicts"] == {"S": "refused:zero-diff", "D": "refused:zero-diff"}


def test_stage_minus1_flags_identical_adjacent_cells():
    out = funnel.stage_minus1([census_row(2.5, (True, True, True), ticker="T01"),
                               census_row(4.5, (False, False, True), ticker="T02")])
    assert out["identical_adjacent"] == {"arm_s": [["c3", "c4"]], "arm_d": [["c3", "c4"]]}


# --- Stage 0 ----------------------------------------------------------------

def test_stage0_powered_when_every_cell_clears_the_ceiling():
    out = funnel.stage0(lifted_s_rows(PLATEAU))
    assert out["verdict"] == "POWERED"
    assert [c["cell"] for c in out["cells"]] == list(KEYS)


def test_stage0_underpowered_when_one_cell_is_noisy():
    rows = lifted_s_rows(PLATEAU)
    noisy = lifted_s_rows(PLATEAU, jitter=2.0)
    for target, source in zip(rows, noisy):
        target["cells"]["c5"] = source["cells"]["c5"]
    out = funnel.stage0(rows)
    assert out["verdict"] == "UNDERPOWERED"
    assert {c["cell"]: c["powered"] for c in out["cells"]} == {"c3": True, "c4": True, "c5": False}


# --- Stage 1 ----------------------------------------------------------------

def test_stage1_selects_the_highest_lower_bound_on_the_plateau():
    out = funnel.stage1(lifted_s_rows(PLATEAU), n_resamples=N)
    assert out["verdict"] == "SELECTED"
    assert out["selected"] == {"cell": "c4", "c": 4.0}
    assert all(c["eligible"] and c["plateau"] for c in out["cells"])
    assert all(c["gate"]["cluster"] == "week" for c in out["cells"])


def test_stage1_a_cell_with_an_ineligible_neighbour_is_off_the_plateau():
    out = funnel.stage1(lifted_s_rows({"c3": 0.0, "c4": 0.1, "c5": 0.5}), n_resamples=N)
    by_cell = {c["cell"]: c for c in out["cells"]}
    assert by_cell["c3"]["eligible"] is False
    assert by_cell["c4"]["eligible"] is True and by_cell["c4"]["plateau"] is False
    assert by_cell["c5"]["plateau"] is True
    assert out["selected"]["cell"] == "c5"


def test_stage1_no_eligible_cell():
    out = funnel.stage1(lifted_s_rows({key: 0.0 for key in KEYS}), n_resamples=N)
    assert out["verdict"] == "NO_ELIGIBLE_CELL" and out["selected"] is None


def test_stage1_tie_goes_to_the_smaller_c():
    out = funnel.stage1(lifted_s_rows({key: 0.2 for key in KEYS}), n_resamples=N)
    assert out["selected"]["cell"] == "c3"


# --- Stage 2 ----------------------------------------------------------------

def _years(lift_by_year):
    rows = []
    for year, lift in lift_by_year.items():
        rows += lifted_s_rows({"c4": lift}, year=year)
    return rows


def test_stage2_is_v129s_fold_rule():
    out = funnel.stage2(_years({2020: 0.2, 2021: 0.2, 2022: -0.1, 2023: -0.1}), "c4")
    assert (out["verdict"], out["arm"], out["cell"]) == ("PASS", "S", "c4")
    assert funnel.stage2(_years({2020: 0.2, 2021: -0.1, 2022: -0.1, 2023: -0.1}),
                         "c4")["verdict"] == "FAIL"


# --- Stage 3 ----------------------------------------------------------------

def test_stage3_passes_a_real_lift_and_fails_a_null():
    good = funnel.stage3(lifted_s_rows({"c4": 0.3}, year=2024), "c4", n_resamples=N)
    assert good["verdict"] == "PASS" and good["permutation_p"] < 0.05
    assert good["gate"]["cluster"] == "week"
    assert {c["name"]: c["verdict"] for c in good["gate"]["clauses"]} == {
        "expectancy_gain": "PASS", "win_rate_floor": "PASS", "volume": "PASS",
        "permutation": "PASS"}
    null = funnel.stage3(lifted_s_rows({"c4": 0.0}, year=2024), "c4", n_resamples=N)
    assert null["verdict"] == "FAIL"


# --- disclosures --------------------------------------------------------------

def test_report_discloses_changes_rollbacks_fills_and_one_sided_rows():
    rows = lifted_s_rows({"c4": 0.3}, n_tickers=2, per_ticker=2)
    rows[0]["changed"]["c4"] = False
    rows[0]["rollback"]["c4"] = True
    rows[0]["cells"]["c4"] = rows[0]["baseline"]
    rows[1]["d"] = 3.5
    rows[1]["cells"]["c4"] = {**rows[1]["cells"]["c4"], "fill_beyond_ceiling": True,
                              "gap_through": True}
    rows.append(s_row(None, {"c4": s_record("T09", "2021-05-15", "win", 2.0)}))
    out = funnel.report(rows, "c4", n_resamples=N)
    assert (out["n_baseline"], out["n_component"]) == (4, 5)
    assert (out["changed"], out["rollback"]) == (4, 1)
    assert out["median_d_changed"] == pytest.approx(3.0)
    assert out["fill_beyond_ceiling"] == {"baseline": 0, "component": 1}
    assert out["gap_through"] == {"baseline": 0, "component": 1}
    assert (out["only_baseline_triggered"], out["only_cell_triggered"]) == (0, 1)
    assert out["per_horizon_n"] == {"4w": 5}
