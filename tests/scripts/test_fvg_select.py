# tests/scripts/test_fvg_select.py
"""v128 Stage 1 judge: both gates, k plateau with an eligible neighbour, at most one winner."""
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import fvg_select as fs  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade, ClauseResult  # noqa: E402

DATES = [d.date().isoformat() for d in pd.bdate_range("2019-01-01", periods=100)]
PASSING = ClauseResult("mechanism", "PASS", "injected")


def _baseline():
    """25 tickers x 100 trades: 40 wins (+2R), 60 losses (-1R); baseline ExpR +0.20R."""
    return [ArmTrade(f"T{t}", "S/R Confluence", "3m", DATES[i], "win" if i < 40 else "loss",
                     2.0 if i < 40 else -1.0, 2.0, "confluence", "bullish") for t in range(25) for i in range(100)]


def _remove(baseline, *, losses=0, wins=0):
    out, seen = [], {}
    for trade in baseline:
        limit = losses if trade.outcome == "loss" else wins
        count = seen.get((trade.ticker, trade.outcome), 0)
        if count < limit:
            seen[(trade.ticker, trade.outcome)] = count + 1
            continue
        out.append(trade)
    return out


def _cell(cid, refused=False, **removal):
    base = _baseline()
    return fs.evaluate_cell(cid, base, _remove(base, **removal), PASSING, refused=refused, n_resamples=200, seed=42)


def _cells(off, d10, d15, d20):
    return {"off": _cell("off", **off), "disp-1.0": _cell("disp-1.0", **d10),
            "disp-1.5": _cell("disp-1.5", **d15), "disp-2.0": _cell("disp-2.0", **d20)}


def test_largest_dexpr_on_a_plateau_wins():
    result = fs.select(_cells({"losses": 1}, {"losses": 3}, {"losses": 2}, {"losses": 1}))
    assert (result["verdict"], result["winner"]) == (fs.SELECTED, "disp-1.0")
    assert result["plateaus"]["disp-1.0"]["passes"] is True


def test_off_is_eligible_on_its_clauses_alone():
    result = fs.select(_cells({"losses": 2}, {"wins": 2}, {"wins": 2}, {"wins": 2}))
    assert (result["verdict"], result["winner"]) == (fs.SELECTED, "off")
    assert "off" not in result["plateaus"]


def test_full_tie_prefers_displacement_then_the_smaller_k():
    result = fs.select(_cells({"losses": 2}, {"losses": 2}, {"losses": 2}, {"losses": 2}))
    assert result["winner"] == "disp-1.0"


def test_a_smaller_alert_cut_breaks_a_dexpr_tie():
    def cell(cid, cut):
        return fs.Cell(cid, True, 0.05, 1.0, cut, ())
    cells = {"off": cell("off", 2.0), "disp-1.0": cell("disp-1.0", 3.0),
             "disp-1.5": cell("disp-1.5", 3.0), "disp-2.0": cell("disp-2.0", 3.0)}
    assert fs.select(cells)["winner"] == "off"
    cells["disp-1.5"] = cell("disp-1.5", 1.0)
    assert fs.select(cells)["winner"] == "disp-1.5"


def test_an_isolated_eligible_k_is_a_spike():
    result = fs.select(_cells({"wins": 2}, {"wins": 2}, {"losses": 2}, {"wins": 1}))
    assert (result["verdict"], result["winner"]) == (fs.SPIKE, None)


def test_no_eligible_cell():
    result = fs.select(_cells({"wins": 2}, {"wins": 2}, {"wins": 2}, {"wins": 2}))
    assert result["verdict"] == fs.NO_ELIGIBLE


def test_a_refused_cell_is_ineligible_but_still_a_plateau_neighbour():
    cells = _cells({"wins": 2}, {"losses": 2}, {"losses": 2}, {"losses": 2})
    base = _baseline()
    cells["disp-1.5"] = fs.evaluate_cell("disp-1.5", base, _remove(base, losses=3), PASSING, refused=True,
                                         n_resamples=200, seed=42)
    assert cells["disp-1.5"].failed[0] == "refused"
    result = fs.select(cells)
    # 1.5's dExpR still shapes its neighbours' plateau, but a refused neighbour is not eligible.
    assert result["plateaus"]["disp-1.0"]["is_plateau"] is True
    assert result["plateaus"]["disp-1.0"]["eligible_neighbour"] is False
    assert (result["verdict"], result["winner"]) == (fs.SPIKE, None)


def test_both_gates_are_required():
    cell = _cell("off", wins=2)
    assert not cell.eligible
    assert "v72:win_rate" in cell.failed and "v92:expectancy_gain" in cell.failed


def test_a_failing_injected_mechanism_blocks_eligibility():
    base = _baseline()
    cell = fs.evaluate_cell("off", base, _remove(base, losses=2), ClauseResult("mechanism", "FAIL", "x"),
                            refused=False, n_resamples=200, seed=42)
    assert cell.failed == ("v72:mechanism",)


def test_plateau_with_a_missing_expectancy_fails():
    cells = {cid: fs.Cell(cid, True, 0.05, 1.0, 1.0, ()) for cid in ("off", "disp-1.0", "disp-1.5", "disp-2.0")}
    cells["disp-1.0"] = fs.Cell("disp-1.0", True, None, None, 1.0, ())
    assert fs.k_plateau(cells, 1.0)["passes"] is False


def _write(tmp_path, name, baseline, component):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"provenance": {"knob_delta": {}}, "baseline": [asdict(t) for t in baseline],
                                "component": [asdict(t) for t in component]}), encoding="utf-8")
    return path


def test_select_refuses_baseline_drift(tmp_path, capsys):
    base = _baseline()
    mech = tmp_path / "m.json"
    mech.write_text(json.dumps(asdict(PASSING)), encoding="utf-8")
    argv = ["select"]
    for cid in ("off", "disp-1.0", "disp-1.5", "disp-2.0"):
        baseline = base[:-1] if cid == "disp-2.0" else base
        argv += ["--arm", f"{cid}={_write(tmp_path, cid, baseline, _remove(base, losses=1))}",
                 "--mechanism", f"{cid}={mech}"]
    assert fs.main(argv) == 1
    assert "refused:baseline-drift" in capsys.readouterr().err


def test_effects_prints_both_claims(tmp_path, capsys):
    base = _baseline()
    assert fs.main(["effects", "--arms", str(_write(tmp_path, "e", base, _remove(base, losses=2)))]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["delta_expectancy_r"] > 0 and out["delta_win_rate_pp"] > 0


def test_an_empty_component_arm_is_never_eligible():
    cell = fs.evaluate_cell("off", _baseline(), [], PASSING, refused=False, n_resamples=200, seed=42)
    assert not cell.eligible
