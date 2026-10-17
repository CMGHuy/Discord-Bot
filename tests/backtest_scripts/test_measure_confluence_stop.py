"""v139 arm S driver: the census before any outcome, the stage order, the
one-shot refusal and the selected-cell-only VALIDATION replay. `build` is
faked; no replay runs."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_confluence_stop as mcs  # noqa: E402

from swingbot.core.backtesting import confluence_stop_funnel as funnel
from tests.backtesting.confluence_stop_rows import census_row, lifted_s_rows

N = 200
PLATEAU = {"c3": 0.1, "c4": 0.3, "c5": 0.2}
CENSUS = [census_row(2.5, (True, True, True), ticker="T01"),
          census_row(3.5, (False, True, True), ticker="T02"),
          census_row(4.5, (False, False, True), ticker="T03")]


def _fake_build(calls, census=None):
    def build(kind, window, cells):
        calls.append((kind, tuple(window), [float(c) for c in cells]))
        if kind == "census":
            return CENSUS if census is None else census
        keys = [f"c{float(c):g}" for c in cells]
        return lifted_s_rows({key: PLATEAU[key] for key in keys}, year=int(window[0][:4]))
    return build


def _run(stage, out_dir, calls, **kw):
    return mcs.run_stage(stage, out_dir, build=_fake_build(calls, **kw), n_resamples=N)


def test_paths():
    assert mcs.stage_path("d", -1).name == "2026-10-08-v139-armS-stageM1.json"
    assert mcs.stage_path("d", 3).name == "2026-10-08-v139-armS-stage3.json"
    assert mcs.rows_path("d", "train").name == "2026-10-08-v139-armS-train-rows.json"


def test_stage0_refuses_without_the_census(tmp_path):
    with pytest.raises(SystemExit, match="run stage -1 first"):
        _run(0, tmp_path, [])


def test_a_zero_diff_census_closes_the_arm(tmp_path):
    calls = []
    assert _run(-1, tmp_path, calls, census=[census_row(None)])["verdict"] == "refused:zero-diff"
    with pytest.raises(SystemExit, match="closed at stage -1 with refused:zero-diff"):
        _run(0, tmp_path, calls)


def test_census_reads_plans_only_then_stage0_builds_train_rows_once(tmp_path):
    calls = []
    assert _run(-1, tmp_path, calls)["verdict"] == "REACHABLE"
    assert calls == [("census", funnel.TRAIN, [3.0, 4.0, 5.0])]
    assert _run(0, tmp_path, calls)["verdict"] == "POWERED"
    assert calls[1] == ("rows", funnel.TRAIN, [3.0, 4.0, 5.0])
    _run(0, tmp_path, calls)
    assert len(calls) == 2          # the rows file is reused, not rebuilt


def test_full_chain_replays_validation_for_the_selected_cell_only(tmp_path):
    calls = []
    for stage in (-1, 0, 1, 2):
        assert _run(stage, tmp_path, calls)["verdict"] in mcs.ADVANCING
    out = _run(3, tmp_path, calls)
    assert (out["verdict"], out["cell"]) == ("PASS", "c4")
    assert calls[-1] == ("rows", funnel.VALIDATION, [4.0])
    assert out["report"]["cell"] == "c4"


def test_stage3_refuses_when_output_exists(tmp_path):
    calls = []
    for stage in (-1, 0, 1, 2, 3):
        _run(stage, tmp_path, calls)
    with pytest.raises(SystemExit, match="one VALIDATION shot is spent"):
        _run(3, tmp_path, calls)


def test_cli_refusals(tmp_path, capsys):
    assert mcs.main(["--stage", "3", "--out-dir", str(tmp_path)]) == 1
    assert "refused:no-preregistration" in capsys.readouterr().err
    prereg = tmp_path / "prereg.md"
    prereg.write_text("x", encoding="utf-8")
    assert mcs.main(["--stage", "3", "--tickers", "3", "--out-dir", str(tmp_path),
                     "--preregistration", str(prereg)]) == 1
    assert "refused:partial-validation" in capsys.readouterr().err
    assert mcs.main(["--stage", "0", "--tickers", "3"]) == 1
    assert "refused:smoke-run" in capsys.readouterr().err


def test_cli_runs_the_census_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(mcs, "build", lambda kind, window, cells, **kw: CENSUS)
    assert mcs.main(["--stage", "-1", "--out-dir", str(tmp_path)]) == 0
    assert mcs.stage_path(tmp_path, -1).exists()
