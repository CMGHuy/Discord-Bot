"""v238 V238-8: validate_component --gate additive Stages 1-3 and the report."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402
from swingbot.core.backtesting import acceptance_additive as aa  # noqa: E402


def _row(ticker, day, r, *, year, strategy="MACD"):
    entry = date(year, 1, 4) + timedelta(days=day)
    return {"ticker": ticker, "strategy": strategy, "horizon_key": "3m",
            "entry_date": entry.isoformat(), "outcome": "win" if r > 0 else "loss",
            "r_multiple": r, "planned_rr": 2.0, "source": "strategy", "direction": "bullish"}


def _arms(*, n=60, win_r=2.0, good=True, year=2021, drop=0):
    """Added rows one per week; good = 2 wins in 3 (ExpR > 0), else 1 in 3 at 2R (ExpR 0)."""
    baseline = [_row(f"B{i % 6}", 7 * i, 2.0 if i % 2 == 0 else -1.0, year=year) for i in range(20)]
    wins = (lambda i: i % 3 != 0) if good else (lambda i: i % 3 == 0)
    added = [_row(f"A{i % 6}", 7 * i + 1, win_r if wins(i) else -1.0, year=year,
                  strategy="Turtle Soup") for i in range(n)]
    return baseline, baseline[drop:] + added


def _write(path, blob, basis="net"):
    path.write_text(json.dumps({**blob, "provenance": {"r_basis": basis}}), encoding="utf-8")
    return path


def _pair(tmp_path, name, arms, basis="net"):
    baseline, component = arms
    return _write(tmp_path / name, {"baseline": baseline, "component": component}, basis)


def _folds(tmp_path, good=(True, True, True), basis="net"):
    folds = []
    for year, ok in zip((2021, 2022, 2023), good):
        baseline, component = _arms(n=39, good=ok, year=year)  # 39: 1-in-3 exact, N >= 30
        folds.append({"test_year": year, "baseline": baseline, "component": component})
    return _write(tmp_path / "folds.json", {"folds": folds}, basis)


def _run(stage, *extra):
    return vc.main(["--gate", "additive", "--stage", stage, "--title", "t", "--window", "w",
                    "--resamples", "300", *extra])


@pytest.fixture(autouse=True)
def no_data(monkeypatch):
    monkeypatch.setattr(vc.cache_dir_source, "resolve", lambda args: None)
    monkeypatch.setattr(vc, "check_stamp", lambda *a, **k: None)
    monkeypatch.setattr(vc, "_selection_stamp_shape", lambda blob: None)
    monkeypatch.setattr(vc, "_full_universe", lambda: [])


def test_selection_one_cell_runs_clauses_1_to_3_week_clustered(tmp_path, capsys):
    cell = _pair(tmp_path, "c.json", _arms())
    out_json = tmp_path / "s.json"
    assert _run("selection", "--grid-arms", f"0.5={cell}", "--out-json", str(out_json)) == 0
    assert "adopted=0.5" in capsys.readouterr().out
    blob = json.loads(out_json.read_text(encoding="utf-8"))
    assert [c["name"] for c in blob["clauses"]] == list(aa.CLAUSES[:3])
    assert blob["gate"] == "additive" and blob["cluster"] == "week" and blob["plateau"] is None
    assert set(blob["disclosures"]) >= {"max_drawdown_r", "same_week_corr"}


def test_selection_adopts_the_highest_own_expr_and_prints_the_plateau(tmp_path, capsys):
    grid = [f"1.0={_pair(tmp_path, 'a.json', _arms())}",
            f"2.0={_pair(tmp_path, 'b.json', _arms(win_r=3.0))}",
            f"3.0={_pair(tmp_path, 'c.json', _arms(good=False))}"]
    argv = [item for cell in grid for item in ("--grid-arms", cell)]
    assert _run("selection", *argv, "--knob", "lookback") == 0
    out = capsys.readouterr().out
    assert "adopted=2.0" in out and 'plateau: {"param": "lookback"' in out


def test_selection_breaks_a_tie_by_grid_order(tmp_path, capsys):
    a, b = _pair(tmp_path, "a.json", _arms()), _pair(tmp_path, "b.json", _arms())
    assert _run("selection", "--grid-arms", f"1.0={a}", "--grid-arms", f"2.0={b}") == 0
    assert "adopted=1.0" in capsys.readouterr().out


def test_selection_with_no_passing_cell_fails(tmp_path, capsys):
    cell = _pair(tmp_path, "c.json", _arms(good=False))
    assert _run("selection", "--grid-arms", f"1.0={cell}") == 1
    assert "verdict=FAIL adopted=None" in capsys.readouterr().out


def test_selection_refuses_a_gross_cell(tmp_path, capsys):
    cell = _pair(tmp_path, "c.json", _arms(), basis="gross")
    assert _run("selection", "--grid-arms", f"1.0={cell}") == 1
    assert capsys.readouterr().err.startswith("refused:r-basis -- ")


def test_selection_refuses_a_misuse_cell(tmp_path, capsys):
    baseline, _ = _arms()
    cell = _pair(tmp_path, "c.json", (baseline, baseline))
    assert _run("selection", "--grid-arms", f"1.0={cell}") == 1
    assert capsys.readouterr().err.startswith("ADDITIVE_GATE_MISUSE")


def test_selection_keeps_the_old_grid_refusals(capsys):
    assert _run("selection") == 1
    assert capsys.readouterr().err.startswith("refused:no-grid -- --grid-arms is required.")


@pytest.mark.parametrize("good, code", [((True, True, True), 0), ((True, False, False), 1)])
def test_walkforward_runs_clause_4_on_the_folds(tmp_path, good, code):
    out_json = tmp_path / "w.json"
    assert _run("walkforward", "--arms", str(_folds(tmp_path, good)),
                "--bespoke-instrument", "x", "--out-json", str(out_json)) == code
    assert [c["name"] for c in json.loads(out_json.read_text())["clauses"]] == ["stability"]


def test_validation_needs_net_folds_arms(tmp_path, capsys):
    arms = _pair(tmp_path, "v.json", _arms())
    base = ["--arms", str(arms), "--bespoke-instrument", "x"]
    assert _run("validation", *base) == 1
    assert capsys.readouterr().err.startswith("refused:no-folds-arms -- ")
    assert _run("validation", *base, "--folds-arms", str(_folds(tmp_path, basis="gross"))) == 1
    assert capsys.readouterr().err.startswith("refused:r-basis -- ")


def test_validation_runs_all_four_and_writes_the_report(tmp_path, capsys):
    out_md, out_json = tmp_path / "v.md", tmp_path / "v.json"
    assert _run("validation", "--arms", str(_pair(tmp_path, "v.json", _arms(drop=1))),
                "--folds-arms", str(_folds(tmp_path)), "--bespoke-instrument", "x",
                "--out-md", str(out_md), "--out-json", str(out_json)) == 0
    blob = json.loads(out_json.read_text(encoding="utf-8"))
    assert [c["name"] for c in blob["clauses"]] == list(aa.CLAUSES)
    assert blob["split"] == {"added": 60, "displaced": 1} and len(blob["displaced"]) == 1
    md = out_md.read_text(encoding="utf-8")
    assert "never gating" in md and "## Displaced rows" in md
    assert f"cause: {vc.DISPLACEMENT_CAUSE}" in md and "- removed: 1" in md


def test_the_additive_only_flags_need_the_additive_gate(capsys):
    with pytest.raises(SystemExit):
        vc.main(["--stage", "mde", "--arms", "a.json", "--title", "t", "--window", "w",
                 "--knob", "lookback"])
    assert "--knob and --folds-arms belong to the additive gate" in capsys.readouterr().err


def test_every_additive_stage_is_wired():
    assert not hasattr(vc, "_additive_pending")
    assert all(callable(getattr(vc, name)) for name in vc._ADDITIVE_STAGES.values())
