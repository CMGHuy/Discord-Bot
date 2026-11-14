"""V212-13c: the v212 stage chain -- census verdicts, the paired MDE, the
portfolio-passed clauses and plateau, the fold gate, the one VALIDATION shot
on the selected cell only, and one ledger row per look. `build` is faked."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_confluence_limit as mcl  # noqa: E402

from swingbot import config
from swingbot.core.backtesting import confluence_limit_replay as clr
from tests.backtest_scripts.test_measure_confluence_limit_clauses import row


@pytest.fixture(autouse=True)
def _open_caps(monkeypatch):
    monkeypatch.setattr(mcl, "require_preregistration", lambda path: None)
    for attr, value in (("RISK_PER_TRADE_PCT", 1.0), ("PORTFOLIO_HEAT_CAP_PCT", 1e9),
                        ("SECTOR_HEAT_CAP_PCT", 1e9), ("MAX_OPEN_POSITIONS", None),
                        ("MAX_POSITION_SIZE_PCT", 1e9), ("MAX_POSITION_VALUE_ABSOLUTE", 0.0)):
        monkeypatch.setattr(config, attr, value, raising=False)
    monkeypatch.setattr(mcl, "_spy", lambda: {"2021-03-01": -1.5})
    monkeypatch.setattr(mcl, "_earnings", lambda tickers: {})


def alerts(years, cells=clr.CELLS, n=100):
    """Reference: WR 50, ExpR 0. Every cell: 80% fills, WR 50, ExpR +0.1."""
    out = []
    for year in years:
        for i in range(n):
            out.append(row("ref", i, 1.0 if i % 2 == 0 else -1.0, year=year))
            for cell in cells:
                filled = i % 5 != 4
                r = (1.2 if i % 2 == 0 else -1.0) if filled else None
                out.append(row(cell, i, r, year=year, filled=filled))
    return out


def census_rows(filled=True):
    return [{"key": f"T{i}|4w|2021-03-01|bullish", "direction": "bullish", "d_pct": 2.5 + i,
             "drops": {cell: None for cell in clr.CELLS},
             "fill_state": {cell: "filled" if filled else "expired" for cell in clr.CELLS},
             "filled": {cell: filled for cell in clr.CELLS}} for i in range(3)]


def fake_build(calls, census=None):
    def build(kind, window, *, touch=False, cells=clr.F_GRID):
        calls.append((kind, tuple(window), touch, tuple(round(c, 3) for c in cells)))
        if kind == "census":
            return census_rows() if census is None else census
        years = (2024,) if tuple(window) == mcl.VALIDATION else (2021, 2022, 2023)
        return alerts(years, [clr.cell_key(c) for c in cells])
    return build


def _run(stage, out, calls, **kw):
    return mcl.run_stage(stage, out, build=fake_build(calls, **kw), preregistration="p.md")


def test_every_stage_refuses_without_the_preregistration(tmp_path, monkeypatch):
    monkeypatch.undo()
    with pytest.raises(SystemExit, match="no-preregistration"):
        mcl.run_stage(-1, tmp_path, build=fake_build([]), preregistration=None)


def test_stage0_refuses_without_the_census(tmp_path):
    with pytest.raises(SystemExit, match="run stage -1 first"):
        _run(0, tmp_path, [])


def test_a_census_without_fills_closes_the_run(tmp_path):
    out = _run(-1, tmp_path, [], census=census_rows(filled=False))
    assert out["verdict"] == "refused:zero-diff"
    with pytest.raises(SystemExit, match="closed at stage -1"):
        _run(0, tmp_path, [])


def test_the_full_chain_reads_validation_for_the_selected_cell_only(tmp_path):
    calls = []
    verdicts = [_run(stage, tmp_path, calls)["verdict"] for stage in (-1, 0, 1, 2, 3)]
    assert verdicts == ["REACHABLE", "POWERED", "SELECTED", "PASS", "THIN"]   # no bearish fills
    stage1 = mcl._load(mcl.stage_path(tmp_path, 1))
    assert stage1["selected"] == {"cell": "f0.333", "f": pytest.approx(1 / 3)}   # tie -> smaller f
    assert all(cell["passes"] for cell in stage1["cells"])
    _assert_folds(mcl._load(mcl.stage_path(tmp_path, 2))["folds"])
    _assert_builds(calls)


def _assert_folds(folds):
    assert [(f["year"], f["n_tp1"]) for f in folds] == [(2021, 40), (2022, 40), (2023, 40)]
    assert all(f["delta_expectancy_r"] == pytest.approx(0.1) for f in folds)


def _assert_builds(calls):
    validation = [c for c in calls if c[1] == mcl.VALIDATION]
    assert validation == [("rows", mcl.VALIDATION, False, (0.333,)),       # the shot
                          ("census", mcl.VALIDATION, False, (0.333,)),     # disclosures only
                          ("rows", mcl.VALIDATION, True, (0.333,))]        # touch sensitivity
    train_rows = [c for c in calls if c[0] == "rows" and c[1] == mcl.TRAIN]
    assert sorted(c[2] for c in train_rows) == [False, True]   # each TRAIN file built once


def test_stage3_is_one_shot(tmp_path):
    for stage in (-1, 0, 1, 2, 3):
        _run(stage, tmp_path, [])
    with pytest.raises(SystemExit, match="one VALIDATION shot is spent"):
        _run(3, tmp_path, [])


def test_ledger_rows_one_per_look(tmp_path):
    for stage in (-1, 0, 1, 2, 3):
        _run(stage, tmp_path, [])
    rows = mcl.ledger_rows(tmp_path, "2026-11-20", "docs/superpowers/results/x.md")
    assert [r["id"] for r in rows] == ["v212-f0.333", "v212-f0.5", "v212-f0.667"]
    assert [(r["verdict"], r["stage_verdict"]) for r in rows] == [
        ("UNMEASURABLE", "THIN"), ("NO-LIFT", "NOT_SELECTED"), ("NO-LIFT", "NOT_SELECTED")]
    assert {r["instrument"] for r in rows} == {"v2"} and rows[0]["n"] == 80


def test_an_underpowered_stage0_makes_every_look_unmeasurable(tmp_path):
    mcl._write(mcl.stage_path(tmp_path, -1), {"verdict": "REACHABLE"})
    mcl._write(mcl.stage_path(tmp_path, 0), {"verdict": "UNDERPOWERED"})
    rows = mcl.ledger_rows(tmp_path, "2026-11-20", "r.md")
    assert {(r["verdict"], r["stage_verdict"]) for r in rows} == {("UNMEASURABLE", "UNDERPOWERED")}
    assert {r["verdict"] for r in mcl.ledger_rows(tmp_path / "none", "d", "r")} == {"OPEN"}


def test_the_cli_refuses_a_partial_validation_shot():
    with pytest.raises(SystemExit, match="partial-validation"):
        mcl.main(["stage", "--stage", "3", "--tickers", "5", "--preregistration", "p.md"])
    with pytest.raises(SystemExit, match="smoke-run"):
        mcl.main(["stage", "--stage", "0", "--tickers", "5", "--preregistration", "p.md"])


# --- review follow-ups: re-run refusal, non-thin VALIDATION, ledger and CLI paths ----

def _both_directions(arm_win):
    """VALIDATION rows with both directions filled (not THIN); arm wins pay `arm_win`R."""
    def build(kind, window, *, touch=False, cells=clr.F_GRID, **_):
        out = []
        for direction, prefix in (("bullish", "L"), ("bearish", "S")):
            for i in range(100):
                ticker = f"{prefix}{i:03d}"
                out.append(row("ref", i, 1.0 if i % 2 == 0 else -1.0, year=2024,
                               direction=direction, ticker=ticker))
                for cell in (clr.cell_key(c) for c in cells):
                    filled = i % 5 != 4
                    r = (arm_win if i % 2 == 0 else -1.0) if filled else None
                    out.append(row(cell, i, r, year=2024, direction=direction,
                                   ticker=ticker, filled=filled))
        return out
    return build


def _through_stage2(out):
    for stage in (-1, 0, 1, 2):
        _run(stage, out, [])


def _stage3(out, arm_win):
    return mcl.run_stage(3, out, build=_both_directions(arm_win), preregistration="p.md")


def test_stage3_passes_a_non_thin_selected_cell_that_beats_the_reference(tmp_path):
    _through_stage2(tmp_path)
    out = _stage3(tmp_path, 1.2)
    assert (out["verdict"], out["cell"], out["score"]["passes"]) == ("PASS", "f0.333", True)
    rows = mcl.ledger_rows(tmp_path, "d", "r")
    assert [(r["verdict"], r["stage_verdict"]) for r in rows][0] == ("PASS", "PASS")


def test_stage3_fails_a_non_thin_selected_cell_below_the_reference(tmp_path):
    _through_stage2(tmp_path)
    out = _stage3(tmp_path, 0.8)
    assert (out["verdict"], out["score"]["expr_beats_reference"]) == ("FAIL", False)
    assert mcl.ledger_rows(tmp_path, "d", "r")[0]["verdict"] == "NO-LIFT"


def test_no_train_stage_reruns_once_validation_is_read(tmp_path):
    _through_stage2(tmp_path)
    _stage3(tmp_path, 1.2)
    for stage in (-1, 0, 1, 2):
        with pytest.raises(SystemExit, match="VALIDATION is read"):
            _run(stage, tmp_path, [])


def _write_stages(out, **verdicts):
    selected = {"cell": "f0.333", "f": 1 / 3}
    stages = {-1: {"verdict": "REACHABLE"}, 0: {"verdict": "POWERED"},
              1: {"verdict": "SELECTED", "selected": selected,
                  "cells": [{"cell": c, "n": 10, "expr": 0.1} for c in clr.CELLS]}}
    stages.update({int(k[1:]): v for k, v in verdicts.items()})
    for stage, body in stages.items():
        mcl._write(mcl.stage_path(out, stage), body)


def test_a_stage2_fail_is_no_lift_for_the_selected_look(tmp_path):
    _write_stages(tmp_path, s2={"verdict": "FAIL", "cell": "f0.333", "folds": []})
    rows = mcl.ledger_rows(tmp_path, "d", "r")
    assert [(r["verdict"], r["stage_verdict"]) for r in rows] == [
        ("NO-LIFT", "FAIL"), ("NO-LIFT", "NOT_SELECTED"), ("NO-LIFT", "NOT_SELECTED")]
    assert rows[0]["n"] == 10


def test_no_eligible_cell_is_no_lift_for_every_look(tmp_path):
    _write_stages(tmp_path, s1={"verdict": "NO_ELIGIBLE_CELL", "selected": None, "cells": []})
    rows = mcl.ledger_rows(tmp_path, "d", "r")
    assert {(r["verdict"], r["stage_verdict"]) for r in rows} == {("NO-LIFT", "NO_ELIGIBLE_CELL")}


def test_a_stage2_pass_without_stage3_leaves_the_selected_look_open(tmp_path):
    _write_stages(tmp_path, s2={"verdict": "PASS", "cell": "f0.333", "folds": []})
    assert mcl.ledger_rows(tmp_path, "d", "r")[0]["verdict"] == "OPEN"


def test_the_ledger_command_prints_one_json_line_per_look(tmp_path, capsys):
    _write_stages(tmp_path, s2={"verdict": "FAIL", "cell": "f0.333", "folds": []})
    code = mcl.main(["ledger", "--run-date", "2026-11-20", "--record", "r.md",
                     "--out", str(tmp_path), "--preregistration", "p.md"])
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert code == 0
    assert [(r["id"], r["verdict"], r["date"], r["record"]) for r in lines] == [
        ("v212-f0.333", "NO-LIFT", "2026-11-20", "r.md"),
        ("v212-f0.5", "NO-LIFT", "2026-11-20", "r.md"),
        ("v212-f0.667", "NO-LIFT", "2026-11-20", "r.md")]


@pytest.mark.parametrize("filled, code", [(True, 0), (False, 1)])
def test_the_stage_command_exits_zero_only_on_an_advancing_verdict(tmp_path, monkeypatch,
                                                                   capsys, filled, code):
    def build(kind, window, *, touch=False, cells=clr.F_GRID, **_):
        return census_rows(filled=filled)
    monkeypatch.setattr(mcl, "build", build)
    assert mcl.main(["stage", "--stage", "-1", "--out", str(tmp_path),
                     "--preregistration", "p.md"]) == code
    verdict = "REACHABLE" if filled else "refused:zero-diff"
    assert f"v212 stage -1: {verdict}" in capsys.readouterr().out


def test_stages_1_and_3_carry_disclosures_that_never_change_the_verdict(tmp_path):
    from swingbot.core.backtesting.confluence_limit_disclosures import render_disclosures
    verdicts = [_run(stage, tmp_path, [])["verdict"] for stage in (-1, 0, 1, 2, 3)]
    assert verdicts == ["REACHABLE", "POWERED", "SELECTED", "PASS", "THIN"]
    blob = mcl._load(mcl.stage_path(tmp_path, 1))["disclosures"]
    assert blob["window"] == "train"
    assert [c["cell"] for c in blob["cells"]] == list(clr.CELLS)
    assert [t["cell"] for t in blob["touch"]] == list(clr.CELLS)
    assert blob["cells"][0]["paired"]["alerts"] == 300          # 100 alerts x 3 TRAIN years
    stage3 = mcl._load(mcl.stage_path(tmp_path, 3))["disclosures"]
    assert (stage3["window"], [c["cell"] for c in stage3["cells"]]) == ("validation", ["f0.333"])
    text = render_disclosures(blob)
    assert "D range" in text and "direction" in text
    assert "disclosures" not in mcl._load(mcl.stage_path(tmp_path, 2))
