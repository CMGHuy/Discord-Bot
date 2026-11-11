"""V212-13c: the v212 stage chain -- census verdicts, the paired MDE, the
portfolio-passed clauses and plateau, the fold gate, the one VALIDATION shot
on the selected cell only, and one ledger row per look. `build` is faked."""
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
    assert validation == [("rows", mcl.VALIDATION, False, (0.333,))]
    train_rows = [c for c in calls if c[0] == "rows" and c[1] == mcl.TRAIN]
    assert len(train_rows) == 1                          # TRAIN rows built once, then reused


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
