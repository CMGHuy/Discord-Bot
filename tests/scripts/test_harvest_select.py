import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
from harvest_select import select  # noqa: E402

from swingbot.core.backtesting.acceptance import ArmTrade


def _arm(lift, n=60):
    base = [ArmTrade(f"T{k % 20}", "S", "2w", f"2020-01-{k % 28 + 1:02d}-{k}", "win", 1.0, 2.0) for k in range(n)]
    comp = [ArmTrade(t.ticker, t.strategy, t.horizon_key, t.entry_date, t.outcome, 1.0 + lift, 2.0) for t in base]
    return base, comp


def test_plateau_of_eligible_neighbours_selects_largest_then_less_aggressive():
    cells = [(0.0, *_arm(0.05)), (0.25, *_arm(0.05)), (0.5, *_arm(0.04))]
    out = select(cells, param="b", less_aggressive="larger")
    assert out["verdict"] == "SELECTED" and out["selected"] == 0.25


def test_isolated_eligible_cell_is_not_selected():
    cells = [(0.70, *_arm(0.0)), (0.85, *_arm(0.2)), (1.00, *_arm(0.0))]
    assert select(cells, param="c", less_aggressive="smaller")["verdict"] == "NO_PLATEAU"


def test_mde_refused_cells_are_ineligible():
    cells = [(0.0, *_arm(0.05)), (0.25, *_arm(0.05)), (0.5, *_arm(0.05))]
    out = select(cells, param="b", less_aggressive="larger", refused=(0.0, 0.25, 0.5))
    assert out["verdict"] == "NO_ELIGIBLE_CELL"
