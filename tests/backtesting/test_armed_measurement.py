import json
import sys
from pathlib import Path

import pytest

from swingbot.core.backtesting import armed_measurement as am
from swingbot.core.backtesting.acceptance import ArmTrade

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402


def _trades(wins, losses, *, date="2019-03-01", horizon="4w", win_r=1.5):
    out = [ArmTrade("AAA", "confluence:Fibonacci", horizon, date, "win", win_r, 2.0)] * wins
    return out + [ArmTrade("AAA", "confluence:Fibonacci", horizon, date, "loss", -1.0, 2.0)] * losses


def _rows(arm, wins, losses, **kw):
    return [am.Row(arm, t, "R1" if arm != am.BASELINE else None) for t in _trades(wins, losses, **kw)]


def _grid_rows(default=(6, 3), overrides=None, baseline=(5, 5)):
    rows = _rows(am.BASELINE, *baseline)
    for cell in am.CELLS:
        rows += _rows(cell.cell_id, *(overrides or {}).get(cell.cell_id, default))
    return rows


def test_the_grid_is_the_pre_registered_30_cells():
    assert len(am.CELLS) == 30
    assert len({c.cell_id for c in am.CELLS}) == 30
    assert am.CELLS[0].cell_id == "N3-k0.25-b0.00"
    assert am.CELLS[-1].cell_id == "N10-k0.50-b0.20"
    # order is n -> k -> b, 5 cells per (n, k): N5-k0.25 starts at 10
    assert am.cell_by_id("N5-k0.25-b0.10") == am.CELLS[12]
    assert not hasattr(am, "MODES")


def test_row_round_trips():
    row = _rows("N3-k0.25-b0.10", 1, 0)[0]
    assert am.Row.from_dict(json.loads(json.dumps(row.to_dict()))) == row


def test_score_cell_eligible_and_its_numbers():
    rows = _grid_rows()
    score = am.score_cell(rows, am.CELLS[0])
    assert score.volume_cut_pct == pytest.approx(10.0)                 # 10 -> 9
    assert score.delta_win_rate_pp == pytest.approx(100 * 6 / 9 - 50)
    assert score.delta_expectancy_r == pytest.approx((9 - 3) / 9 - 0.25)
    assert score.eligible and score.reasons == ()


def test_score_cell_reasons():
    cut = am.score_cell(_grid_rows(default=(4, 2)), am.CELLS[0])     # 10 -> 6: 40% cut
    assert not cut.eligible and any(r.startswith("volume") for r in cut.reasons)
    worse = am.score_cell(_grid_rows(default=(3, 7)), am.CELLS[0])
    assert any(r.startswith("profit") for r in worse.reasons)
    assert any(r.startswith("win rate") for r in worse.reasons)


def test_select_picks_by_expectancy_then_smaller_n_on_a_plateau():
    selection = am.select_cell(_grid_rows())
    assert selection.verdict == am.SELECTED
    assert selection.selected == "N3-k0.25-b0.00"                     # all tie -> smaller N, first in order
    assert all(p["is_plateau"] for p in selection.plateaus)
    assert [p["param"] for p in selection.plateaus] == ["ARMED_N", "ARMED_K", "ARMED_B"]


def test_a_best_cell_whose_neighbours_disagree_is_a_spike():
    selection = am.select_cell(_grid_rows(overrides={"N5-k0.25-b0.10": (8, 1)}))
    assert selection.best == "N5-k0.25-b0.10"
    assert selection.verdict == am.SPIKE and selection.selected is None


def test_no_eligible_cell():
    selection = am.select_cell(_grid_rows(default=(3, 7)))
    assert selection.verdict == am.NO_ELIGIBLE_CELL
    assert selection.selected is None and selection.plateaus == ()


def test_blobs_load_through_validate_component(tmp_path):
    rows = (_rows(am.BASELINE, 5, 5, date="2021-02-01") + _rows(am.BASELINE, 5, 5, date="2022-02-01")
            + _rows(am.BASELINE, 5, 5, date="2023-02-01"))
    for year in ("2021", "2022", "2023"):
        rows += _rows("N3-k0.25-b0.10", 6, 3, date=f"{year}-03-01")
    arms = tmp_path / "arms.json"
    arms.write_text(json.dumps(am.arms_blob(rows, "N3-k0.25-b0.10")))
    baseline, component = vc.load_arms(arms)
    assert len(baseline) == 30 and len(component) == 27
    folds = tmp_path / "folds.json"
    folds.write_text(json.dumps(am.folds_blob(rows, "N3-k0.25-b0.10")))
    loaded = vc.load_folds(folds)
    assert [f["test_year"] for f in loaded] == ["2021", "2022", "2023"]
    assert all(len(f["baseline"]) == 10 and len(f["component"]) == 9 for f in loaded)


def test_permutation_p_is_the_share_of_permuted_deltas_at_or_above_the_real_one():
    baseline = _trades(5, 5)
    real = _trades(8, 2)
    permuted = [_trades(5, 5), _trades(9, 1), _trades(4, 6), _trades(8, 2)]
    result = am.permutation_p(baseline, real, permuted)
    assert result["real_delta_win_rate_pp"] == pytest.approx(30.0)
    assert result["p_value"] == pytest.approx(2 / 4)                  # 9-1 and 8-2 are >= 30pp
    assert result["n"] == 4 and result["n_valid"] == 4


def test_render_selection_md_lists_every_cell_and_the_verdict():
    md = am.render_selection_md(am.select_cell(_grid_rows()))
    assert "**Verdict: SELECTED**" in md
    assert all(cell.cell_id in md for cell in am.CELLS)
    assert "greatest" in md and "ΔExpR" in md                        # the rule is quoted
    assert am.LIMITATIONS in md                                       # spec §4.3
