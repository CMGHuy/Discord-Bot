"""v129 stage driver: prerequisites, the one-shot refusal and the
selected-cell-only VALIDATION replay. `build` is faked; no replay runs."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_acceptance_exits as mae  # noqa: E402

from swingbot.core.backtesting import acceptance_exit_funnel as funnel
from swingbot.core.backtesting.acceptance_replay import CELLS, cell_key
from tests.backtesting.acceptance_rows import lifted_rows

N = 200


def _fake_build(calls, lift=0.3):
    def build(arm, window, cells):
        calls.append((arm, tuple(window), [tuple(cell) for cell in cells]))
        lifts = {cell_key(m, b): lift for m, b in CELLS[arm]}
        return lifted_rows(arm, lifts, year=int(window[0][:4]))
    return build


def _run(arm, stage, out_dir, calls, **kw):
    return mae.run_stage(arm, stage, out_dir, build=_fake_build(calls, **kw), n_resamples=N)


def test_paths():
    assert mae.stage_path("d", "Z", 3).name == "2026-10-03-v129-armZ-stage3.json"
    assert mae.rows_path("d", "B", "train").name == "2026-10-03-v129-armB-train-rows.json"


def test_stage0_builds_train_rows_once_and_writes_the_verdict(tmp_path):
    calls = []
    out = _run("Z", 0, tmp_path, calls)
    assert out["verdict"] == "POWERED"
    assert calls == [("Z", funnel.TRAIN, list(CELLS["Z"]))]
    assert mae.rows_path(tmp_path, "Z", "train").exists()
    assert json.loads(mae.stage_path(tmp_path, "Z", 0).read_text())["verdict"] == "POWERED"
    _run("Z", 0, tmp_path, calls)
    assert len(calls) == 1          # the rows file is reused, not rebuilt


def test_stage1_refuses_without_stage0(tmp_path):
    calls = []
    with pytest.raises(SystemExit, match="run stage 0 first"):
        _run("Z", 1, tmp_path, calls)
    assert calls == []


def test_a_closed_arm_does_not_advance(tmp_path):
    mae.stage_path(tmp_path, "B", 0).write_text(json.dumps({"verdict": "UNDERPOWERED"}))
    with pytest.raises(SystemExit, match="closed at stage 0 with UNDERPOWERED"):
        _run("B", 1, tmp_path, [])


def test_full_chain_replays_validation_for_the_selected_cell_only(tmp_path):
    calls = []
    assert _run("Z", 0, tmp_path, calls)["verdict"] == "POWERED"
    stage1 = _run("Z", 1, tmp_path, calls)
    assert stage1["verdict"] == "SELECTED"
    assert len(stage1["reports"]) == len(CELLS["Z"])
    assert _run("Z", 2, tmp_path, calls)["verdict"] == "PASS"
    stage3 = _run("Z", 3, tmp_path, calls)
    picked = stage1["selected"]
    assert calls[-1] == ("Z", funnel.VALIDATION, [(picked["m"], picked["b"])])
    assert len(calls) == 2          # TRAIN once, VALIDATION once
    assert stage3["cell"] == picked["cell"] and stage3["verdict"] == "PASS"
    assert stage3["report"]["cell"] == picked["cell"]


def test_stage3_refuses_when_output_exists(tmp_path):
    calls = []
    for stage in (0, 1, 2, 3):
        _run("B", stage, tmp_path, calls)
    before = len(calls)
    with pytest.raises(SystemExit, match="spent"):
        _run("B", 3, tmp_path, calls)
    assert len(calls) == before


def test_stage3_reuses_saved_validation_rows_after_a_crash(tmp_path):
    calls = []
    for stage in (0, 1, 2, 3):
        _run("B", stage, tmp_path, calls)
    mae.stage_path(tmp_path, "B", 3).unlink()      # crash before the verdict write
    before = len(calls)
    assert _run("B", 3, tmp_path, calls)["verdict"] == "PASS"
    assert len(calls) == before                    # no second look at VALIDATION


def test_cli_refuses_stage3_without_a_preregistration(tmp_path, capsys):
    code = mae.main(["--arm", "Z", "--stage", "3", "--out-dir", str(tmp_path)])
    assert code == 1
    assert "refused:no-preregistration" in capsys.readouterr().err


def test_cli_refuses_a_smoke_run_into_the_real_results_dir(capsys):
    code = mae.main(["--arm", "Z", "--stage", "0", "--tickers", "3"])
    assert code == 1
    assert "refused:smoke-run" in capsys.readouterr().err


def test_cli_refuses_a_partial_universe_at_stage3(tmp_path, capsys):
    prereg = tmp_path / "prereg.md"
    prereg.write_text("x")
    code = mae.main(["--arm", "Z", "--stage", "3", "--out-dir", str(tmp_path),
                     "--tickers", "3", "--preregistration", str(prereg)])
    assert code == 1
    assert "refused:partial-validation" in capsys.readouterr().err


def test_cache_universe_lists_cached_csv_stems_sorted(tmp_path, monkeypatch):
    for name in ("MSFT.csv", "AAPL.csv", "notes.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    from swingbot.core.marketdata import backtest_cache
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)
    assert mae.cache_universe() == ["AAPL", "MSFT"]
