import pytest

from swingbot.core.backtesting import armed_measurement as am
from swingbot.core.backtesting import structure_measurement as sm
from swingbot.core.backtesting.acceptance import ArmTrade


def _trades(arm, wins, losses, kind=None, date="2019-03-01"):
    return [sm.Row(arm, ArmTrade("AAA", "confluence:Fib", "4w", date, o, r, 2.0), kind)
            for o, r in [("win", 1.5)] * wins + [("loss", -1.0)] * losses]


def _rows(component=(6, 3), override=None):
    """Baseline 5W/5L; every cell `component` (W, L) unless overridden."""
    rows = _trades(sm.BASELINE, 5, 5)
    for cell in sm.CELLS:
        wins, losses = (override or {}).get(cell.cell_id, component)
        rows += _trades(cell.cell_id, wins, losses, kind=cell.trigger)
    return rows


def test_the_grid_is_the_pre_registered_twelve_cells():
    assert sm.N_GRID == (5, 10, 15) and sm.K_GRID == (0.25, 0.5)
    assert [c.cell_id for c in sm.CELLS] == [
        "MSB-N5-k0.25", "MSB-N5-k0.50", "MSB-N10-k0.25", "MSB-N10-k0.50",
        "MSB-N15-k0.25", "MSB-N15-k0.50", "HL-N5-k0.25", "HL-N5-k0.50",
        "HL-N10-k0.25", "HL-N10-k0.50", "HL-N15-k0.25", "HL-N15-k0.50"]


def test_windows_and_permutation_constants_are_v90s():
    assert sm.SELECTION_WINDOW == ("2018-06-01", "2020-12-31")
    assert sm.FOLD_TEST_YEARS == ("2021", "2022", "2023")
    assert sm.VALIDATION_WINDOW == ("2024-01-01", "2025-12-31")
    assert (sm.PERMUTATION_N, sm.PERMUTATION_SEED) == (200, 42)
    assert (sm.SELECTION_OBSERVED_DAYS, sm.MDE_TARGET_DAYS) == (945, 730)


def test_v90s_grid_is_untouched():
    assert len(am.CELLS) == 30 and am.CELLS[0].cell_id == "N3-k0.25-b0.00"


def test_cell_by_id_round_trips_and_rejects_unknown_ids():
    assert sm.cell_by_id("HL-N10-k0.50") == sm.CELLS[9]
    with pytest.raises(KeyError):
        sm.cell_by_id("N10-k0.50-b0.10")


def test_flat_eligible_grid_selects_the_first_cell_on_a_plateau():
    selection = sm.select_cell(_rows())
    assert selection.verdict == sm.SELECTED and selection.selected == "MSB-N5-k0.25"
    assert [p["param"] for p in selection.plateaus] == ["STRUCT_N", "STRUCT_K"]
    assert all(p["is_plateau"] for p in selection.plateaus)
    score = {s.cell_id: s for s in selection.scores}["MSB-N5-k0.25"]
    assert score.volume_cut_pct == pytest.approx(10.0)
    assert score.delta_win_rate_pp == pytest.approx(16.6667, abs=1e-4)
    assert score.delta_expectancy_r == pytest.approx(0.416667, abs=1e-6)


def test_a_lone_peak_is_a_spike():
    """MSB-N10-k0.25 at 7W/2L (ExpR 0.944) beside 6W/3L (0.667) neighbours."""
    selection = sm.select_cell(_rows(override={"MSB-N10-k0.25": (7, 2)}))
    assert selection.verdict == sm.SPIKE and selection.selected is None
    assert selection.best == "MSB-N10-k0.25"
    assert [p["is_plateau"] for p in selection.plateaus] == [False, False]


def test_trigger_is_categorical_and_both_rows_are_reported():
    """HL beats MSB everywhere by the same margin: a plateau across N and k,
    selected, with both trigger rows at the pick's N and k."""
    override = {c.cell_id: (7, 2) for c in sm.CELLS if c.trigger == "HL"}
    selection = sm.select_cell(_rows(override=override))
    assert selection.verdict == sm.SELECTED and selection.selected == "HL-N5-k0.25"
    assert [s.cell_id for s in sm.trigger_rows(selection)] == ["MSB-N5-k0.25", "HL-N5-k0.25"]


def test_a_negative_dwr_is_never_eligible_at_any_expectancy():
    selection = sm.select_cell(_rows(component=(4, 5)))
    assert selection.verdict == sm.NO_ELIGIBLE_CELL and selection.best is None
    assert sm.trigger_rows(selection) == []


def test_a_volume_cut_over_25_percent_is_ineligible():
    selection = sm.select_cell(_rows(component=(5, 2)))
    assert selection.verdict == sm.NO_ELIGIBLE_CELL
    assert selection.scores[0].reasons == ("volume: cut 30.00% > 25.0%",)


def test_funnel_buckets_regates_and_windows_by_arm_date():
    recs = [{"cell": "MSB-N5-k0.25", "horizon": "4w", "arm_date": d, "status": s} for d, s in [
        ("2019-03-01", "issued"), ("2019-03-02", "regate_reward"),
        ("2019-03-03", "regate_no_target"), ("2019-03-04", "cancelled_zone_failed"),
        ("2019-03-05", "expired"), ("2021-03-05", "expired")]]
    recs.append({"cell": "HL-N15-k0.50", "horizon": "4w", "arm_date": "2020-12-31",
                 "status": "unresolved"})
    funnel = sm.funnel(recs, sm.SELECTION_WINDOW)
    assert funnel["MSB-N5-k0.25"] == {"armed": 5, "issued": 1, "regated": 2,
                                      "cancelled_zone_failed": 1, "expired": 1, "unresolved": 0}
    assert funnel["HL-N15-k0.50"]["unresolved"] == 1
    assert funnel["HL-N5-k0.25"]["armed"] == 0 and len(funnel) == 12


def test_selection_markdown_carries_rule_limitations_plateaus_and_disclosure():
    selection = sm.select_cell(_rows())
    md = sm.render_selection_md(selection, sm.funnel([], sm.SELECTION_WINDOW))
    assert "**Verdict: SELECTED**" in md and "## All 12 cells" in md
    assert sm.SELECTION_RULE in md and sm.LIMITATIONS in md
    assert "STRUCT_N" in md and "STRUCT_K" in md
    assert "## Population disclosure" in md and "alert-volume ratio" in md
    assert "| MSB-N5-k0.25 | 0 | 0 | 0 | 0 | 0 | 0 | 0.900 |" in md
