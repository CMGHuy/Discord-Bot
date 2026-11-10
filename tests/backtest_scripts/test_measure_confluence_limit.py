"""V212-13: the v212 measure script's frozen constants, the pre-registration
refusal and the per-ticker checkpoint. No replay runs: the worker is faked."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_confluence_limit as mcl  # noqa: E402


def test_frozen_constants():
    assert mcl.REQUIRES == {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"),
                            3: (2, "PASS")}
    assert (mcl.FILLS_SHARE, mcl.WR_SLACK_PP, mcl.THIN_PER_DIRECTION) == (0.5, 2.0, 30)
    assert (mcl.TRAIN, mcl.VALIDATION) == (("2020-01-01", "2023-12-31"),
                                           ("2024-01-01", "2025-12-31"))
    assert mcl.FOLD_YEARS == (2021, 2022, 2023)
    assert mcl.RESULTS.parts[-3:] == ("superpowers", "results", "v212")
    assert mcl.CLAUSE_NAMES == ("expr_beats_reference", "fills_half_of_reference",
                                "wr_within_2pp")


def test_require_preregistration_refuses(tmp_path, monkeypatch):
    wrong = tmp_path / "2026-11-06-v131-preregistration.md"
    wrong.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="no-preregistration"):
        mcl.require_preregistration(wrong)
    with pytest.raises(SystemExit, match="no-preregistration"):
        mcl.require_preregistration(None)
    missing = tmp_path / "2026-11-07-v212-preregistration.md"
    with pytest.raises(SystemExit, match="no-preregistration"):
        mcl.require_preregistration(missing)
    right = tmp_path / "2026-11-06-v212-preregistration.md"
    right.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="uncommitted"):     # outside the repo: untracked
        mcl.require_preregistration(right)
    monkeypatch.setattr(mcl, "_committed", lambda path: True)
    assert mcl.require_preregistration(right) is None


def test_stage_files_and_the_requires_chain(tmp_path):
    assert mcl.stage_path("d", -1).name == "v212-stageM1.json"
    assert mcl.stage_path("d", 3).name == "v212-stage3.json"
    assert mcl.rows_file("d", "rows", "train", touch=True).name == "v212-rows-train-touch-rows.json"
    with pytest.raises(SystemExit, match="run stage -1 first"):
        mcl._previous(tmp_path, 0)
    mcl._write(mcl.stage_path(tmp_path, -1), {"verdict": "refused:zero-diff"})
    with pytest.raises(SystemExit, match="closed at stage -1"):
        mcl._previous(tmp_path, 0)
    mcl._write(mcl.stage_path(tmp_path, 0), {"verdict": "POWERED"})
    assert mcl._previous(tmp_path, 1) == {"verdict": "POWERED"}


def _fake_worker(calls):
    def worker(task):
        calls.append(task[1])
        return task[1], [{"ticker": task[1], "kind": task[0], "touch": task[3]}]
    return worker


def test_build_checkpoints_each_ticker_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr(mcl, "universe", lambda: ["BBB", "AAA"])
    calls = []
    first = mcl.build("rows", mcl.TRAIN, checkpoint_dir=tmp_path, workers=1,
                      worker=_fake_worker(calls))
    assert [r["ticker"] for r in first] == ["AAA", "BBB"]       # ticker order, not run order
    assert len(list(tmp_path.rglob("*.json"))) == 2
    calls.clear()
    again = mcl.build("rows", mcl.TRAIN, checkpoint_dir=tmp_path, workers=1,
                      worker=_fake_worker(calls))
    assert (again, calls) == (first, [])                          # nothing finished is replayed


def test_build_resumes_a_half_finished_run(tmp_path, monkeypatch):
    monkeypatch.setattr(mcl, "universe", lambda: ["AAA", "BBB", "CCC"])
    calls = []
    mcl.build("census", mcl.TRAIN, tickers=1, checkpoint_dir=tmp_path, workers=1,
              worker=_fake_worker(calls))
    calls.clear()
    rows = mcl.build("census", mcl.TRAIN, checkpoint_dir=tmp_path, workers=1,
                     worker=_fake_worker(calls))
    assert calls == ["BBB", "CCC"] and len(rows) == 3


def test_touch_cells_and_windows_get_their_own_checkpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(mcl, "universe", lambda: ["AAA"])
    calls = []
    for kw in ({}, {"touch": True}, {"cells": (0.5,)}):
        mcl.build("rows", mcl.TRAIN, checkpoint_dir=tmp_path, workers=1,
                  worker=_fake_worker(calls), **kw)
    mcl.build("rows", mcl.VALIDATION, checkpoint_dir=tmp_path, workers=1,
              worker=_fake_worker(calls))
    assert calls == ["AAA"] * 4
    assert len({p.parent.name for p in tmp_path.rglob("*.json")}) == 4


def test_the_cli_refuses_before_any_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(mcl, "build", lambda *a, **k: pytest.fail("replayed before refusing"))
    with pytest.raises(SystemExit, match="no-preregistration"):
        mcl.main(["rows", "--window", "train", "--preregistration", str(tmp_path / "x.md")])


def test_the_cli_writes_the_rows_file(tmp_path, monkeypatch):
    seen = {}

    def fake_build(kind, window, **kw):
        seen.update(kind=kind, window=window, **kw)
        return [{"ticker": "AAA"}]

    monkeypatch.setattr(mcl, "require_preregistration", lambda path: None)
    monkeypatch.setattr(mcl, "build", fake_build)
    assert mcl.main(["rows", "--window", "train", "--touch", "--cells", "f0.5",
                     "--preregistration", "p.md", "--out", str(tmp_path)]) == 0
    assert (seen["kind"], seen["window"], seen["touch"]) == ("rows", mcl.TRAIN, True)
    assert list(seen["cells"]) == [0.5]
    assert mcl._load(tmp_path / "v212-rows-train-touch-rows.json") == [{"ticker": "AAA"}]


def test_the_cli_never_builds_validation_rows(monkeypatch):
    monkeypatch.setattr(mcl, "require_preregistration", lambda path: None)  # argparse refuses
    monkeypatch.setattr(mcl, "build", lambda *a, **k: pytest.fail("read VALIDATION by hand"))
    for command in ("rows", "census"):
        with pytest.raises(SystemExit):
            mcl.main([command, "--window", "validation", "--preregistration", "p.md"])


def _git(repo, *args):
    import subprocess
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo,
                   check=True, capture_output=True)


def test_committed_reads_git_for_real(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    record = tmp_path / "2026-11-06-v212-preregistration.md"
    record.write_text("frozen", encoding="utf-8")
    monkeypatch.setattr(mcl, "ROOT", tmp_path)
    assert mcl._committed(record) is False                       # untracked
    _git(tmp_path, "add", record.name)
    _git(tmp_path, "commit", "-q", "-m", "record")
    assert mcl._committed(record) is True
    mcl.require_preregistration(record)
    stray = tmp_path / "2026-11-07-v212-preregistration.md"
    stray.write_text("never added", encoding="utf-8")
    assert mcl._committed(stray) is False                        # untracked, HEAD exists
    record.write_text("edited after commit", encoding="utf-8")
    assert mcl._committed(record) is False                       # tracked but dirty
    with pytest.raises(SystemExit, match="uncommitted"):
        mcl.require_preregistration(record)


def test_a_torn_checkpoint_write_is_not_a_finished_ticker(tmp_path, monkeypatch):
    monkeypatch.setattr(mcl, "universe", lambda: ["AAA"])
    folder = tmp_path / mcl._tag("rows", mcl.TRAIN, False, mcl.clr.F_GRID)
    folder.mkdir()
    (folder / "AAA.json.tmp").write_text("[{\"tick", encoding="utf-8")
    calls = []
    rows = mcl.build("rows", mcl.TRAIN, checkpoint_dir=tmp_path, workers=1,
                     worker=_fake_worker(calls))
    assert calls == ["AAA"] and rows[0]["ticker"] == "AAA"
    assert [p.name for p in folder.iterdir()] == ["AAA.json"]
