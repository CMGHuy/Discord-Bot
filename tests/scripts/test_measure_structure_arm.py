import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_structure_arm as msa  # noqa: E402
import validate_component as vc  # noqa: E402
from swingbot.core.backtesting import structure_measurement as sm  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade  # noqa: E402
from swingbot.core.backtesting.structure_arm import MSB, StructCell  # noqa: E402
from tests.helpers import make_ohlcv  # noqa: E402

ONE_CELL = (StructCell(MSB, 10, 0.5),)


def _cache(tmp_path):
    """tests/scripts/test_measure_armed_entries.py's trend + box frame. On
    horizon 4w under MSB-N10-k0.50 it arms five times and issues once."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    cache = tmp_path / "cache"
    cache.mkdir()
    df = make_ohlcv(trend + box, start="2019-01-02")
    df.index.name = "Date"
    df.to_csv(cache / "AAA.csv")
    return cache


def _replay(cache, out, *extra):
    return msa.main(["replay", "--run", "run1", "--cache-dir", str(cache), "--out-root", str(out),
                     "--horizons", "4w", "--workers", "1", *extra])


def _synthetic_rows():
    rows = []
    for date in ("2019-03-01", "2021-03-01", "2022-03-01", "2023-03-01"):
        rows += [sm.Row(sm.BASELINE, ArmTrade("AAA", "confluence:Fib", "4w", date, o, r, 2.0))
                 for o, r in [("win", 1.5)] * 5 + [("loss", -1.0)] * 5]
        for cell in sm.CELLS:
            rows += [sm.Row(cell.cell_id, ArmTrade("AAA", "confluence:Fib", "4w", date, o, r, 2.3),
                            cell.trigger)
                     for o, r in [("win", 1.5)] * 6 + [("loss", -1.0)] * 3]
    return rows


def _write_run1(out, rows, arms=()):
    run_dir = out / "run1"
    run_dir.mkdir(parents=True, exist_ok=True)
    msa.write_shard(run_dir / "AAA.jsonl", [r.to_dict() for r in rows])
    (run_dir / "AAA.arms.json").write_text(json.dumps(list(arms)))
    return run_dir


def test_defaults_point_at_the_v127_root_and_all_ten_horizons():
    assert msa.OUT_ROOT.parts[-2:] == ("data", "v127")
    assert len(msa.LEGACY_HORIZONS) == 10


def test_run2_is_locked_without_a_passing_stage2_doc(tmp_path):
    cache, out = _cache(tmp_path), tmp_path / "out"
    assert msa.main(["replay", "--run", "run2", "--cache-dir", str(cache), "--out-root", str(out)]) == 3
    doc = tmp_path / "stage2.md"
    doc.write_text("**Overall: FAIL**\n")
    assert msa.main(["replay", "--run", "run2", "--cache-dir", str(cache), "--out-root", str(out),
                     "--stage2-doc", str(doc)]) == 3
    assert not (out / "run2").exists()


def test_replay_refuses_to_resume_under_different_metadata(tmp_path):
    cache = _cache(tmp_path)
    run_dir = tmp_path / "out" / "run1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"cache_files": ["ZZZ.csv"]}))
    assert _replay(cache, tmp_path / "out") == 4


@pytest.mark.slow
def test_replay_writes_shards_arm_records_and_removes_its_progress_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "CELLS", ONE_CELL)
    cache, out = _cache(tmp_path), tmp_path / "out"
    assert _replay(cache, out) == 0
    run_dir = out / "run1"
    assert not (run_dir / "progress.txt").exists()
    meta = json.loads((run_dir / "run.json").read_text())
    assert meta["cells"] == ["MSB-N10-k0.50"] and meta["horizons"] == ["4w"]
    counts = json.loads((run_dir / "AAA.counts.json").read_text())
    assert counts == {"4w|MSB-N10-k0.50": {"armed": 5, "regate_no_target": 1, "expired": 3,
                                           "issued": 1}}
    arms = json.loads((run_dir / "AAA.arms.json").read_text())
    assert [a["status"] for a in arms] == ["regate_no_target", "expired", "issued",
                                           "expired", "expired"]
    rows = msa.read_rows(run_dir)
    assert [(r.arm, r.reaction, r.trade.entry_date) for r in rows] == [
        ("MSB-N10-k0.50", "MSB", "2019-07-12")]
    # resuming skips the finished ticker and still exits clean
    assert _replay(cache, out) == 0


@pytest.mark.slow
def test_arm_records_never_carry_the_walk_status_triggered(tmp_path, monkeypatch):
    """funnel() buckets only issued / regate_* / expired ...; a 'triggered'
    status would land in no column."""
    monkeypatch.setattr(sm, "CELLS", ONE_CELL)
    cache, out = _cache(tmp_path), tmp_path / "out"
    assert _replay(cache, out) == 0
    arms = msa.read_arms(out / "run1")
    assert arms and "triggered" not in {a["status"] for a in arms}
    funnel = sm.funnel(arms, ("2000-01-01", "2100-01-01"))["MSB-N10-k0.50"]
    assert funnel["issued"] == 1 and funnel["regated"] == 1


@pytest.mark.slow
def test_replay_survives_a_corrupt_cache_csv(tmp_path, monkeypatch):
    """Review focus: a poisoned cache file must not stall the run."""
    monkeypatch.setattr(sm, "CELLS", ONE_CELL)
    cache = _cache(tmp_path)
    (cache / "BBB.csv").write_bytes(b"\xff\xfe\x00garbage-not-real-csv\x01\x02")
    out = tmp_path / "out"
    assert _replay(cache, out) == 0
    run_dir = out / "run1"
    assert (run_dir / "AAA.jsonl").read_text().strip()
    assert (run_dir / "BBB.jsonl").read_text() == ""
    assert json.loads((run_dir / "BBB.arms.json").read_text()) == []


def test_arm_records_are_never_read_as_trade_rows(tmp_path):
    """Review focus: read_rows globs *.jsonl; arm records must not match."""
    arms = [{"cell": "MSB-N5-k0.25", "horizon": "4w", "arm_date": "2019-03-01", "status": "issued"}]
    run_dir = _write_run1(tmp_path / "out", _synthetic_rows(), arms)
    assert len(msa.read_rows(run_dir)) == len(_synthetic_rows())
    assert msa.read_arms(run_dir) == arms


def test_summary_reports_the_selection_window_only(tmp_path):
    arms = [{"cell": "MSB-N5-k0.25", "horizon": "4w", "arm_date": d, "status": "expired"}
            for d in ("2019-03-01", "2022-03-01")]
    out = tmp_path / "out"
    _write_run1(out, _synthetic_rows(), arms)
    md = tmp_path / "summary.md"
    assert msa.main(["summary", "--out-root", str(out), "--out-md", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    assert "Rows in the selection window 2018-06-01..2020-12-31: 118" in text   # 10 + 12 * 9
    assert "| MSB-N5-k0.25 | 9 | 1 | 0 | 0 | 0 | 1 | 0 |" in text           # the 2022 arm is not counted
    assert sm.LIMITATIONS in text


def test_select_and_arms(tmp_path):
    out = tmp_path / "out"
    _write_run1(out, _synthetic_rows())
    sel_md, sel_json = tmp_path / "sel.md", tmp_path / "sel.json"
    assert msa.main(["select", "--out-root", str(out), "--out-md", str(sel_md),
                     "--out-json", str(sel_json)]) == 0
    payload = json.loads(sel_json.read_text())
    assert payload["verdict"] == sm.SELECTED and payload["selected"] == "MSB-N5-k0.25"
    assert set(payload["funnel"]) == {c.cell_id for c in sm.CELLS}
    assert "**Verdict: SELECTED**" in sel_md.read_text(encoding="utf-8")

    mde = tmp_path / "mde.json"
    assert msa.main(["arms", "--stage", "mde", "--cell", "HL-N10-k0.50",
                     "--out-root", str(out), "--out", str(mde)]) == 0
    baseline, component = vc.load_arms(mde)
    assert len(baseline) == 10 and len(component) == 9          # only the 2019 rows
    wf = tmp_path / "wf.json"
    assert msa.main(["arms", "--stage", "walkforward", "--cell", "HL-N10-k0.50",
                     "--out-root", str(out), "--out", str(wf)]) == 0
    assert [f["test_year"] for f in vc.load_folds(wf)] == ["2021", "2022", "2023"]


def test_the_arms_feed_validate_component_as_a_bespoke_instrument(tmp_path, capsys):
    out = tmp_path / "out"
    _write_run1(out, _synthetic_rows())
    mde = tmp_path / "mde.json"
    assert msa.main(["arms", "--stage", "mde", "--cell", "MSB-N5-k0.25",
                     "--out-root", str(out), "--out", str(mde)]) == 0
    assert vc.main(["--stage", "mde", "--arms", str(mde), "--title", "v127 fixture",
                    "--window", "2018-06-01..2020-12-31", "--train-effect-pp", "16.67",
                    "--observed-days", "945", "--target-days", "730",
                    "--bespoke-instrument", msa.BESPOKE_REASON]) == 0
    assert f"BESPOKE INSTRUMENT: {msa.BESPOKE_REASON}" in capsys.readouterr().out


def test_select_with_no_rows_exits_2(tmp_path):
    _write_run1(tmp_path / "out", [])
    assert msa.main(["select", "--out-root", str(tmp_path / "out")]) == 2


def test_validation_arms_and_permute_need_a_run2(tmp_path):
    out = tmp_path / "out"
    _write_run1(out, _synthetic_rows())
    assert msa.main(["arms", "--stage", "validation", "--cell", "MSB-N5-k0.25",
                     "--out-root", str(out), "--out", str(tmp_path / "v.json")]) == 2
    assert msa.main(["permute", "--cell", "MSB-N5-k0.25", "--out-root", str(out),
                     "--out-json", str(tmp_path / "p.json")]) == 4
