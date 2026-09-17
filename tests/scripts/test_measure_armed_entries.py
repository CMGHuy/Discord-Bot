import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_armed_entries as mae  # noqa: E402
import validate_component as vc  # noqa: E402
from swingbot.core.backtesting import armed_measurement as am  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade  # noqa: E402
from tests.helpers import make_ohlcv  # noqa: E402


def _cache(tmp_path):
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    cache = tmp_path / "cache"
    cache.mkdir()
    df = make_ohlcv(trend + box, start="2019-01-02")
    df.index.name = "Date"
    df.to_csv(cache / "AAA.csv")
    return cache


def _write_rows(run_dir, rows, meta=None):
    run_dir.mkdir(parents=True, exist_ok=True)
    mae.write_shard(run_dir / "AAA.jsonl", [r.to_dict() for r in rows])
    (run_dir / "run.json").write_text(json.dumps(meta or {"cells": [c.cell_id for c in am.CELLS]}))


def _synthetic_rows():
    rows = []
    for date in ("2019-03-01", "2021-03-01", "2022-03-01", "2023-03-01"):
        rows += [am.Row(am.BASELINE, ArmTrade("AAA", "confluence:Fib", "4w", date, o, r, 2.0))
                 for o, r in [("win", 1.5)] * 5 + [("loss", -1.0)] * 5]
        for cell in am.CELLS:
            rows += [am.Row(cell.cell_id, ArmTrade("AAA", "confluence:Fib", "4w", date, o, r, 2.3), "R1")
                     for o, r in [("win", 1.5)] * 6 + [("loss", -1.0)] * 3]
    return rows


def test_run2_is_locked_without_a_passing_stage2_doc(tmp_path):
    cache = _cache(tmp_path)
    out = tmp_path / "out"
    assert mae.main(["replay", "--run", "run2", "--cache-dir", str(cache), "--out-root", str(out)]) == 3
    doc = tmp_path / "stage2.md"
    doc.write_text("**Overall: FAIL**\n")
    assert mae.main(["replay", "--run", "run2", "--cache-dir", str(cache), "--out-root", str(out),
                     "--stage2-doc", str(doc)]) == 3


def test_replay_refuses_to_resume_under_different_metadata(tmp_path):
    cache = _cache(tmp_path)
    run_dir = tmp_path / "out" / "run1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"cache_files": ["ZZZ.csv"]}))
    assert mae.main(["replay", "--run", "run1", "--cache-dir", str(cache),
                     "--out-root", str(tmp_path / "out"), "--horizons", "4w", "--workers", "1"]) == 4


@pytest.mark.slow
def test_replay_writes_shards_and_removes_its_progress_file(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "CELLS", (am.Cell(10, 0.5, 0.10),))
    cache = _cache(tmp_path)
    out = tmp_path / "out"
    assert mae.main(["replay", "--run", "run1", "--cache-dir", str(cache), "--out-root", str(out),
                     "--horizons", "4w", "--workers", "1"]) == 0
    run_dir = out / "run1"
    assert (run_dir / "AAA.jsonl").exists() and (run_dir / "AAA.counts.json").exists()
    assert not (run_dir / "progress.txt").exists()
    meta = json.loads((run_dir / "run.json").read_text())
    assert meta["cells"] == ["N10-k0.50-b0.10"] and meta["horizons"] == ["4w"]
    counts = json.loads((run_dir / "AAA.counts.json").read_text())
    assert "4w|N10-k0.50-b0.10" in counts
    # resuming skips the finished ticker and still exits clean
    assert mae.main(["replay", "--run", "run1", "--cache-dir", str(cache), "--out-root", str(out),
                     "--horizons", "4w", "--workers", "1"]) == 0


@pytest.mark.slow
def test_replay_survives_a_corrupt_cache_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "CELLS", (am.Cell(10, 0.5, 0.10),))
    cache = _cache(tmp_path)
    (cache / "BBB.csv").write_bytes(b"\xff\xfe\x00garbage-not-real-csv\x01\x02")
    out = tmp_path / "out"
    assert mae.main(["replay", "--run", "run1", "--cache-dir", str(cache), "--out-root", str(out),
                     "--horizons", "4w", "--workers", "1"]) == 0
    run_dir = out / "run1"
    # the good ticker still replays normally
    assert (run_dir / "AAA.jsonl").exists() and (run_dir / "AAA.jsonl").read_text().strip()
    # the corrupt ticker is skipped, not crashed on: an empty shard, not a missing one
    assert (run_dir / "BBB.jsonl").exists() and (run_dir / "BBB.jsonl").read_text() == ""
    assert json.loads((run_dir / "BBB.counts.json").read_text()) == {}


def test_summary_select_and_arms(tmp_path):
    out = tmp_path / "out"
    _write_rows(out / "run1", _synthetic_rows())
    md = tmp_path / "summary.md"
    assert mae.main(["summary", "--run", "run1", "--window", "2018-06-01..2020-12-31",
                     "--out-root", str(out), "--out-md", str(md)]) == 0
    assert "baseline" in md.read_text() and "N3-k0.25-b0.10" in md.read_text()
    assert am.LIMITATIONS in md.read_text()

    sel_md, sel_json = tmp_path / "sel.md", tmp_path / "sel.json"
    assert mae.main(["select", "--out-root", str(out), "--out-md", str(sel_md),
                     "--out-json", str(sel_json)]) == 0
    payload = json.loads(sel_json.read_text())
    assert payload["verdict"] == am.SELECTED and payload["selected"] == "N3-k0.25-b0.00"
    assert "**Verdict: SELECTED**" in sel_md.read_text()

    mde = tmp_path / "mde.json"
    assert mae.main(["arms", "--stage", "mde", "--cell", "N3-k0.25-b0.10",
                     "--out-root", str(out), "--out", str(mde)]) == 0
    baseline, component = vc.load_arms(mde)
    assert len(baseline) == 10 and len(component) == 9          # only the 2019 rows

    wf = tmp_path / "wf.json"
    assert mae.main(["arms", "--stage", "walkforward", "--cell", "N3-k0.25-b0.10",
                     "--out-root", str(out), "--out", str(wf)]) == 0
    assert [f["test_year"] for f in vc.load_folds(wf)] == ["2021", "2022", "2023"]


def test_select_skips_the_overlap_section_without_a_v88_run(tmp_path):
    out = tmp_path / "out"
    _write_rows(out / "run1", _synthetic_rows())
    md = tmp_path / "stage1.md"
    assert mae.main(["select", "--out-root", str(out), "--out-md", str(md),
                     "--v88-run-dir", str(tmp_path / "absent")]) == 0
    assert "Overlap with v88" not in md.read_text(encoding="utf-8")


def test_select_with_no_rows_exits_2(tmp_path):
    _write_rows(tmp_path / "out" / "run1", [])
    assert mae.main(["select", "--out-root", str(tmp_path / "out")]) == 2


def test_permute_needs_a_run2(tmp_path):
    assert mae.main(["permute", "--cell", "N3-k0.25-b0.10", "--out-root", str(tmp_path / "out"),
                     "--out-json", str(tmp_path / "p.json")]) == 4
