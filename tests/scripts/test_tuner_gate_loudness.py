import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "backtest"))
from tune_strategy import report_gate


def _row(win_rate, expectancy_r):
    return ({"k": 1}, {"n_eval": 100, "win_rate": win_rate, "expectancy_r": expectancy_r,
                         "excluded_share": 0.1})


def test_reports_ungated_when_nothing_qualifies():
    got = report_gate([_row(35, .05)], [])
    assert not got["gated"] and "UNGATED" in got["headline"] and "80" in got["headline"]


def test_reports_gated_when_some_qualify():
    row = _row(85, .05)
    got = report_gate([row], [row])
    assert got["gated"] and got["n_qualifying"] == 1


def test_payload_shape_is_stable():
    assert set(report_gate([_row(35, .05)], [])) >= {"gated", "n_qualifying", "n_rows", "headline"}
