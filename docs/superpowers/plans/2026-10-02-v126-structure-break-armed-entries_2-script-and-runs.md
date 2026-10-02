# v126 Structure-Break Armed Entries — Part 2: the script, the gate and the runs

> Part of `2026-10-02-v126-structure-break-armed-entries`. Header, global constraints, spec readings, review focus, parallelisation and outcomes live in `_0-index.md` — read its **Global Constraints** before any task here. Phase 1 (V126-1..4) is in `_1-replay-and-grid.md`.

# Phase 2 — The measurement script and the gate (worktree branch)

### Task V126-5: `measure_structure_arm.py`

**Files:**
- Create: `scripts/backtest/measure_structure_arm.py`
- Test: `tests/scripts/test_measure_structure_arm.py`

**Interfaces:**
- Consumes: V126-2's `replay_structure` / `StructCellResult.arms`; V126-3's `structure_permutations`; V126-4's `structure_measurement` (`CELLS`, `cell_by_id`, `select_cell`, `funnel`, `render_selection_md`, `FUNNEL_COLUMNS`, the re-exported windows/blobs). From the sibling script `measure_armed_entries.py`, unchanged: `STAGE2_PASS_MARKER = "**Overall: PASS**"`, `_map(worker, tasks, workers)`, `_trade(frame, index, plan, date) -> ArmTrade`, `load_frame(cache_dir, symbol)`, `read_rows(run_dir)` (globs `*.jsonl`), `write_shard(path, rows)`. Sibling-script imports are established (`measure_fib_v103.py`, `measure_v104.py`).
- Produces: CLI `replay --run run1|run2 [--stage2-doc] [--tickers] [--horizons] [--workers]`, `summary --out-md`, `select [--out-md] [--out-json]`, `arms --stage mde|walkforward|validation --cell --out`, `permute --cell --out-json [--workers]`; exit codes 0 ok, 1 select non-SELECTED, 2 empty window/no baseline, 3 run2 locked, 4 resume metadata mismatch / no run2. Module constants `OUT_ROOT = ROOT / "data" / "v126"`, `RUNS`, `BESPOKE_REASON`. On disk per ticker: `<ticker>.jsonl` (trade rows, written last — its presence marks the ticker done), `<ticker>.counts.json`, `<ticker>.arms.json` (arm records; **not** `.jsonl`), plus `run.json` and a transient `progress.txt`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_measure_structure_arm.py`:

```python
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


def test_defaults_point_at_the_v126_root_and_all_ten_horizons():
    assert msa.OUT_ROOT.parts[-2:] == ("data", "v126")
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
    assert vc.main(["--stage", "mde", "--arms", str(mde), "--title", "v126 fixture",
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_structure_arm.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'measure_structure_arm'`.

- [ ] **Step 3: Implement the script**

Create `scripts/backtest/measure_structure_arm.py`:

```python
#!/usr/bin/env python3
"""v126: replay and score the pre-registered structure-break armed-entry grid.

Read docs/superpowers/specs/2026-10-02-v126-structure-break-armed-entries-design.md
§4 first. The walk lives in swingbot/core/backtesting/structure_arm.py, the
arithmetic in structure_measurement.py; this script only replays frames and
moves rows to and from disk. Stage verdicts come from
scripts/backtest/validate_component.py (with --bespoke-instrument), fed by `arms`.

    replay   --run run1 | run2     sharded per ticker, resumable; run2 refused
                                   without a Stage 2 doc reading **Overall: PASS**
    summary  --out-md PATH         run1 row counts + arm funnel, selection window only
    select   (Stage 1, selection window only)
    arms     --stage mde | walkforward | validation --cell CELL_ID --out PATH
    permute  --cell CELL_ID        the random-delay null over run2

Long runs: dispatch to the backtest-runner subagent. Progress is flushed to
stdout and to <out-root>/<run>/progress.txt as "done/total tickers (pct%)";
the file is deleted when the command finishes.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from measure_armed_entries import (  # noqa: E402  (sibling script, same dir)
    STAGE2_PASS_MARKER, _map, _trade, load_frame, read_rows, write_shard,
)
from swingbot.core.backtesting import structure_measurement as sm  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402

CACHE_DIR = ROOT / "data" / "backtest_cache"
OUT_ROOT = ROOT / "data" / "v126"
RUNS = {"run1": sm.RUN1_WINDOW, "run2": sm.VALIDATION_WINDOW}
BESPOKE_REASON = ("structure_arm: v126 armed structure-break replay "
                  "(measure_arms.py has no armed-entry engine)")


def _in(window, date) -> bool:
    return window[0] <= date <= window[1]


def _horizon_rows(ticker, frame, horizon, window):
    """(rows, counts, arm records) for one horizon, rows/arms in window."""
    from swingbot.core.backtesting.armed_replay import arm_candidates
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.core.backtesting.structure_arm import replay_structure
    rows, counts, arms = [], {}, []
    for index, plan in replay_scenarios(ticker, frame, horizon):
        date = str(frame.index[index].date())
        if _in(window, date):
            rows.append(sm.Row(sm.BASELINE, _trade(frame, index, plan, date)))
    cache: dict = {}
    candidates = arm_candidates(ticker, frame, horizon, level_cache=cache)
    results = replay_structure(ticker, frame, horizon, sm.CELLS, candidates=candidates,
                               level_cache=cache)
    for cell_id, result in results.items():
        counts[f"{horizon}|{cell_id}"] = dict(result.counts)
        for j, plan, trigger in result.issued:
            date = str(frame.index[j].date())
            if _in(window, date):
                rows.append(sm.Row(cell_id, _trade(frame, j, plan, date), trigger))
        for arm_index, _end, status in result.arms:
            date = str(frame.index[arm_index].date())
            if _in(window, date):
                arms.append({"cell": cell_id, "horizon": horizon, "arm_date": date,
                             "status": status})
    return rows, counts, arms


def ticker_rows(ticker, frame, window, horizons):
    rows, counts, arms = [], {}, []
    for horizon in horizons:
        r, c, a = _horizon_rows(ticker, frame, horizon, window)
        rows += r
        counts.update(c)
        arms += a
    return rows, counts, arms


def _replay_worker(task):
    ticker, cache_dir, window, horizons = task
    frame = load_frame(cache_dir, ticker)
    if frame is None or frame.empty:
        return ticker, [], {}, []
    rows, counts, arms = ticker_rows(ticker, frame, window, horizons)
    return ticker, [row.to_dict() for row in rows], counts, arms


def read_arms(run_dir) -> list:
    """Arm records live in <ticker>.arms.json -- NOT .jsonl, which
    measure_armed_entries.read_rows globs as trade rows."""
    out = []
    for shard in sorted(Path(run_dir).glob("*.arms.json")):
        out += json.loads(shard.read_text(encoding="utf-8"))
    return out


def run_meta(cache_dir, window, horizons) -> dict:
    return {"cache_files": sorted(p.name for p in Path(cache_dir).glob("*.csv")),
            "window": list(window), "horizons": list(horizons),
            "cells": [cell.cell_id for cell in sm.CELLS]}


def _run2_locked(args) -> bool:
    if args.run != "run2":
        return False
    doc = Path(args.stage2_doc) if args.stage2_doc else None
    return doc is None or not doc.exists() or STAGE2_PASS_MARKER not in doc.read_text(encoding="utf-8")


def _claim_run_dir(args, horizons):
    """The run dir, or None when an existing run.json disagrees (no resume)."""
    run_dir = Path(args.out_root) / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = run_meta(Path(args.cache_dir), RUNS[args.run], horizons)
    meta_path = run_dir / "run.json"
    if meta_path.exists() and json.loads(meta_path.read_text()) != meta:
        return None
    meta_path.write_text(json.dumps(meta, indent=1))
    return run_dir


def _write_ticker(run_dir, ticker, rows, counts, arms):
    (run_dir / f"{ticker}.arms.json").write_text(json.dumps(arms), encoding="utf-8")
    (run_dir / f"{ticker}.counts.json").write_text(json.dumps(counts))
    write_shard(run_dir / f"{ticker}.jsonl", rows)       # last: its presence marks the ticker done


def cmd_replay(args) -> int:
    if _run2_locked(args):
        print("REFUSED -- run2 replays VALIDATION; it needs --stage2-doc reading "
              f"{STAGE2_PASS_MARKER}", flush=True)
        return 3
    horizons = args.horizons.split(",") if args.horizons else list(LEGACY_HORIZONS)
    run_dir = _claim_run_dir(args, horizons)
    if run_dir is None:
        print(f"REFUSED -- {args.out_root}/{args.run}/run.json was written for a different "
              "cache/window/horizons/grid", flush=True)
        return 4
    cache = Path(args.cache_dir)
    symbols = args.tickers.split(",") if args.tickers else sorted(p.stem for p in cache.glob("*.csv"))
    todo = [s for s in symbols if not (run_dir / f"{s}.jsonl").exists()]
    tasks = [(s, str(cache), RUNS[args.run], horizons) for s in todo]
    progress = run_dir / "progress.txt"
    try:
        for done, (ticker, rows, counts, arms) in enumerate(_map(_replay_worker, tasks, args.workers), 1):
            _write_ticker(run_dir, ticker, rows, counts, arms)
            pct = 100 * done // len(todo) if todo else 100
            progress.write_text(f"{done}/{len(todo)} tickers ({pct}%)\n")
            print(f"[{done}/{len(todo)}] {ticker}: {len(rows)} rows ({pct}%)", flush=True)
    finally:
        progress.unlink(missing_ok=True)
    print(f"complete: {len(read_rows(run_dir))} rows", flush=True)
    return 0


def cmd_summary(args) -> int:
    """Run 1 sanity, SELECTION window only (spec §4.3: nothing outside it
    is inspected before its stage)."""
    run_dir = Path(args.out_root) / "run1"
    rows = sm.in_window(read_rows(run_dir), sm.SELECTION_WINDOW)
    funnel = sm.funnel(read_arms(run_dir), sm.SELECTION_WINDOW)
    lo, hi = sm.SELECTION_WINDOW
    lines = ["# v126 structure-break armed entries — run1 replay", "",
             f"Rows in the selection window {lo}..{hi}: {len(rows)} across "
             f"{len({r.trade.ticker for r in rows})} tickers.", "", sm.LIMITATIONS, "",
             "| arm | rows | " + " | ".join(sm.FUNNEL_COLUMNS) + " |",
             "|---|---|" + "---|" * len(sm.FUNNEL_COLUMNS),
             f"| baseline | {len(sm.arm_trades(rows, sm.BASELINE))} |" + " |" * len(sm.FUNNEL_COLUMNS)]
    for cell in sm.CELLS:
        counts = funnel[cell.cell_id]
        lines.append(f"| {cell.cell_id} | {len(sm.arm_trades(rows, cell.cell_id))} | "
                     + " | ".join(str(counts[c]) for c in sm.FUNNEL_COLUMNS) + " |")
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def _write_text(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def cmd_select(args) -> int:
    run_dir = Path(args.out_root) / "run1"
    rows = sm.in_window(read_rows(run_dir), sm.SELECTION_WINDOW)
    if not rows:
        print("no rows in the selection window", flush=True)
        return 2
    selection = sm.select_cell(rows)
    funnel = sm.funnel(read_arms(run_dir), sm.SELECTION_WINDOW)
    payload = {"verdict": selection.verdict, "selected": selection.selected, "best": selection.best,
               "scores": [dataclasses.asdict(s) for s in selection.scores],
               "plateaus": list(selection.plateaus), "funnel": funnel}
    if args.out_json:
        _write_text(args.out_json, json.dumps(payload, indent=1))
    if args.out_md:
        _write_text(args.out_md, sm.render_selection_md(selection, funnel))
    print(f"verdict: {selection.verdict}; selected: {selection.selected}", flush=True)
    return 0 if selection.verdict == sm.SELECTED else 1


def cmd_arms(args) -> int:
    root = Path(args.out_root)
    if args.stage == "validation":
        blob = sm.arms_blob(sm.in_window(read_rows(root / "run2"), sm.VALIDATION_WINDOW), args.cell)
    elif args.stage == "walkforward":
        blob = sm.folds_blob(read_rows(root / "run1"), args.cell)
    else:
        blob = sm.arms_blob(sm.in_window(read_rows(root / "run1"), sm.SELECTION_WINDOW), args.cell)
    parts = blob["folds"] if "folds" in blob else [blob]
    if not all(part["baseline"] for part in parts):
        print("an arm has no baseline rows", flush=True)
        return 2
    _write_text(args.out, json.dumps(blob))
    return 0


def _permute_worker(task):
    from swingbot.core.backtesting.armed_replay import arm_candidates
    from swingbot.core.backtesting.structure_arm import replay_structure, structure_permutations
    ticker, cache_dir, cell_id, horizons, n, seed = task
    frame = load_frame(cache_dir, ticker)
    permutations = [[] for _ in range(n)]
    if frame is None or frame.empty:
        return ticker, permutations
    cell = sm.cell_by_id(cell_id)
    for horizon in horizons:
        cache: dict = {}
        candidates = arm_candidates(ticker, frame, horizon, level_cache=cache)
        result = replay_structure(ticker, frame, horizon, [cell], candidates=candidates,
                                  level_cache=cache)[cell_id]
        drawn = structure_permutations(ticker, frame, horizon, cell, result.confirmed, n=n,
                                       seed=seed, level_cache=cache)
        for index, rows in enumerate(drawn):
            permutations[index] += rows
    return ticker, permutations


def _collect_permutations(tasks, workers, progress) -> list:
    lo, hi = sm.VALIDATION_WINDOW
    permuted = [[] for _ in range(sm.PERMUTATION_N)]
    try:
        for done, (ticker, drawn) in enumerate(_map(_permute_worker, tasks, workers), 1):
            for index, perm_rows in enumerate(drawn):
                permuted[index] += [ArmTrade(ticker, strategy, horizon, date, outcome, None, None)
                                    for date, strategy, horizon, outcome in perm_rows
                                    if lo <= date <= hi]
            pct = 100 * done // len(tasks) if tasks else 100
            progress.write_text(f"{done}/{len(tasks)} tickers ({pct}%)\n")
            print(f"[{done}/{len(tasks)}] {ticker} ({pct}%)", flush=True)
    finally:
        progress.unlink(missing_ok=True)
    return permuted


def cmd_permute(args) -> int:
    run_dir = Path(args.out_root) / "run2"
    meta_path = run_dir / "run.json"
    if not meta_path.exists():
        print("REFUSED -- no run2 replay to permute", flush=True)
        return 4
    meta = json.loads(meta_path.read_text())
    rows = sm.in_window(read_rows(run_dir), sm.VALIDATION_WINDOW)
    baseline, real = sm.arm_trades(rows, sm.BASELINE), sm.arm_trades(rows, args.cell)
    tickers = sorted({row.trade.ticker for row in rows})
    tasks = [(t, args.cache_dir, args.cell, meta["horizons"], sm.PERMUTATION_N, sm.PERMUTATION_SEED)
             for t in tickers]
    permuted = _collect_permutations(tasks, args.workers, run_dir / "progress.txt")
    result = {**sm.permutation_p(baseline, real, permuted), "seed": sm.PERMUTATION_SEED,
              "cell": args.cell, "window": list(sm.VALIDATION_WINDOW)}
    _write_text(args.out_json, json.dumps(result, indent=1))
    print(f"permutation p = {result['p_value']}", flush=True)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cell_ids = [cell.cell_id for cell in sm.CELLS]
    workers = max(1, os.cpu_count() or 1)

    def command(name):
        p = sub.add_parser(name)
        p.add_argument("--cache-dir", default=str(CACHE_DIR))
        p.add_argument("--out-root", default=str(OUT_ROOT))
        return p

    p = command("replay")
    p.add_argument("--run", choices=RUNS, required=True)
    p.add_argument("--tickers"); p.add_argument("--horizons"); p.add_argument("--stage2-doc")
    p.add_argument("--workers", type=int, default=workers)
    command("summary").add_argument("--out-md", required=True)
    p = command("select")
    p.add_argument("--out-md"); p.add_argument("--out-json")
    p = command("arms")
    p.add_argument("--stage", choices=("mde", "walkforward", "validation"), required=True)
    p.add_argument("--cell", choices=cell_ids, required=True); p.add_argument("--out", required=True)
    p = command("permute")
    p.add_argument("--cell", choices=cell_ids, required=True); p.add_argument("--out-json", required=True)
    p.add_argument("--workers", type=int, default=workers)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    handler = {"replay": cmd_replay, "summary": cmd_summary, "select": cmd_select,
               "arms": cmd_arms, "permute": cmd_permute}[args.command]
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_structure_arm.py`
Expected: `VERDICT: PASS  11 passed` (the two `slow` replays included — `file` runs the slow tier). The pinned replay numbers (`armed 5`, one `issued` on `2019-07-12`, one `regate_no_target`, three `expired`) were measured on the prototype on 2026-10-02; if they differ, stop and report rather than re-pinning.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C scripts/backtest/measure_structure_arm.py`
Expected: at most `F ... cmd_replay - C (11)`; nothing at or above 15.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/measure_structure_arm.py tests/scripts/test_measure_structure_arm.py
git commit -m "feat(v126): measure_structure_arm.py -- sharded replay, selection, arms, permutation"
```

---

### Task V126-6: Full-suite verification and merge

**Files:** none created; verifies Phases 1–2.

- [ ] **Step 1: v88/v90 are byte-identical**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-02-v126-structure-break-armed-entries diff --stat main -- swingbot/core/backtesting/armed_replay.py swingbot/core/backtesting/armed_measurement.py scripts/backtest/measure_armed_entries.py swingbot/core/market/reaction.py tests/backtesting/test_armed_replay.py tests/backtesting/test_armed_measurement.py tests/scripts/test_measure_armed_entries.py
```

Expected: **no output.** Any diff is a violation of the spec's §3.2 — revert it and move the change into `structure_arm.py`.

- [ ] **Step 2: Complexity over everything this plan wrote**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/structure_arm.py swingbot/core/backtesting/structure_measurement.py scripts/backtest/measure_structure_arm.py`
Expected: only `cmd_replay - C (11)`.

- [ ] **Step 3: Run the full suite once**

Dispatch the `test-runner` subagent (or run `python scripts/dev/testrun.py full`) once, over V126-1..5. Expect `0 failed`, `0 xfailed`, and the whole-repo pyflakes undefined-name gate clean. **If it is not green, fix forward from those failures** — they are this plan's regressions, and the task is not done until the run is. The one non-obvious caller to check if something fails outside the files above: anything globbing `data/v*/run1/*.jsonl` generically (the arm records are `.arms.json` precisely to stay out of such globs).

- [ ] **Step 4: Merge the worktree branch to `main`**

Per `docs/claude/document-lifecycle.md` and the `worktree-lifecycle` skill (other sessions are active — check `git -C E:/Documents/Private/Projects/Discord-Bot status` first and stage nothing of theirs). A conflict-free merge is not re-run; a merge that resolved conflicts gets one run.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-10-02-v126-structure-break-armed-entries -m "Merge branch '2026-10-02-v126-structure-break-armed-entries'"
```

Do not remove the worktree yet — V126-12 closes the plan out.

---

# Phase 3 — Measurement runs (on `main`, after V126-6's merge)

Every task here runs on `main` in the main tree. `<run-date>` is the date (`YYYY-MM-DD`) the command in that task finishes; `<cell>` is the cell id V126-8 selects. **Commit each result as written before reading anything into it.** A verdict that ends the measurement goes straight to V126-12 — the grid, windows, rule and constants never change. Every long command is dispatched to `backtest-runner`: it is resumable (re-running skips finished tickers), flushes `done/total tickers (pct%)` to stdout and to `data/v126/<run>/progress.txt`, and deletes that file on completion.

### Task V126-7: Run 1 replay

**Files:**
- Create (local, not committed): `data/v126/run1/*.jsonl`, `*.counts.json`, `*.arms.json`, `run.json`
- Create: `docs/superpowers/results/<run-date>-v126-structure-run1.md`

**Interfaces:**
- Consumes: the merged code; `data/backtest_cache/*.csv`.
- Produces: Run 1 rows (entries 2018-06-01..2023-12-31) for the baseline and all 12 cells, and arm records in the same window.

- [ ] **Step 1: Confirm the cache**

```bash
python -c "import pandas as pd, glob; f=sorted(glob.glob('data/backtest_cache/*.csv')); d=[pd.read_csv(p, index_col='Date', parse_dates=True).index for p in f]; print(len(f), 'files', min(i.min() for i in d).date(), '->', min(i.max() for i in d).date())"
```

Expected (observed 2026-10-02): `75 files 2018-06-01 -> 2025-12-30`. `run.json` pins the file list, so the cache must not change between here and V126-11. **If the count or the range differs, stop and report — do not refetch on your own**; other plans read this cache. (The 2025-12-31 bar is absent from today's cache; V126-11's doc records that as observed.)

- [ ] **Step 2: Dispatch the replay to `backtest-runner`**

Brief: run `python scripts/backtest/measure_structure_arm.py replay --run run1` from the repo root (main tree); it is resumable; answer progress questions from `data/v126/run1/progress.txt`; report the final `complete: N rows` line, the elapsed time, and any traceback verbatim.

Expected: exit 0, `complete: <N> rows`, no `progress.txt` left behind. Budget ~1h–1h30 (v88's 24 cells took 1h41m over 88 tickers; this is 12 cells over 75).

- [ ] **Step 3: Summarise, sanity-check and commit**

```bash
python scripts/backtest/measure_structure_arm.py summary --out-md docs/superpowers/results/<run-date>-v126-structure-run1.md
```

The summary reads the selection window only. Sanity check before committing: every cell's `armed` must be non-zero, and both `issued` and `cancelled_zone_failed` must be non-zero in at least one MSB and one HL cell. If any of that is zero across the grid, the walk did not take effect — stop and debug rather than reading numbers. Do not open any shard for fold-year dates.

```bash
git add docs/superpowers/results/<run-date>-v126-structure-run1.md
git commit -m "docs(v126): run 1 replay complete"
```

---

### Task V126-8: Stage 1 — selection

**Files:**
- Create: `docs/superpowers/results/<run-date>-v126-structure-stage1.md` and `.json`

**Interfaces:**
- Consumes: Run 1 rows and arm records, selection window only.
- Produces: `<cell>` and its selection-window `delta_win_rate_pp`, or a terminal verdict.

- [ ] **Step 1: Run the pre-registered selection**

```bash
python scripts/backtest/measure_structure_arm.py select --out-md docs/superpowers/results/<run-date>-v126-structure-stage1.md --out-json docs/superpowers/results/<run-date>-v126-structure-stage1.json
echo $?
```

Expected: `verdict: SELECTED; selected: <cell>` (exit 0), or `NO_ELIGIBLE_CELL` / `SPIKE` (exit 1), or exit 2 if the window holds no rows (a broken run — stop and debug; that is not a verdict). Capture the exit code directly, not through a pipe.

The doc carries, per spec §6: the full 12-cell table, the plateau reports on `N` and `k`, both trigger rows at the pick's `N`/`k`, the rule quoted, `LIMITATIONS`, and the population disclosure (per cell: armed / issued / regated / `cancelled_zone_failed` / expired / unresolved, and the alert-volume ratio vs baseline). Confirm all six sections are present before committing.

- [ ] **Step 2: Commit the result as written**

```bash
git add docs/superpowers/results/<run-date>-v126-structure-stage1.md docs/superpowers/results/<run-date>-v126-structure-stage1.json
git commit -m "docs(v126): stage 1 selection -- <verdict as printed>"
```

- [ ] **Step 3: Branch on the verdict**

- `SELECTED` → read `<cell>`'s `delta_win_rate_pp` from the JSON's `scores` list (`<effect>`); carry both to V126-9.
- `NO_ELIGIBLE_CELL` or `SPIKE` → go to V126-12 with that verdict.

Read the population disclosure before moving on and quote the selected (or best) cell's alert-volume ratio in V126-12's row — the v88 volume blow-up (ratios ~5.9) must be visible if it recurred.

---

### Task V126-9: Stage 0 — minimum detectable effect

**Files:**
- Create (local): `data/v126/arms_mde.json`
- Create: `docs/superpowers/results/<run-date>-v126-structure-stage0.md`

**Interfaces:**
- Consumes: `<cell>` and `<effect>` from V126-8.
- Produces: `RESOLVABLE` (continue) or `REFUSED` (budget intact).

- [ ] **Step 1: Build the selection-window arms**

```bash
python scripts/backtest/measure_structure_arm.py arms --stage mde --cell <cell> --out data/v126/arms_mde.json
```

Expected: exit 0.

- [ ] **Step 2: Run the MDE gate**

```bash
python scripts/backtest/validate_component.py --stage mde --arms data/v126/arms_mde.json --title "v126 structure-break armed entries <cell>" --window "2018-06-01..2020-12-31" --train-effect-pp <effect> --observed-days 945 --target-days 730 --bespoke-instrument "structure_arm: v126 armed structure-break replay (measure_arms.py has no armed-entry engine)"
```

Expected: first line `BESPOKE INSTRUMENT: structure_arm: ...`, then the observed/projected N and the paired and unpaired MDE, ending in `RESOLVABLE -- the shot may proceed.` (exit 0) or `REFUSED -- ...` (exit 1). The gate uses the paired MDE when the arms share keys (v100's instrument, which does not reopen anything).

- [ ] **Step 3: Write and commit the record**

Create `docs/superpowers/results/<run-date>-v126-structure-stage0.md`:

```markdown
# v126 structure-break armed entries — Stage 0 (MDE)

**Verdict: <RESOLVABLE | REFUSED>**

Cell: <cell>. Window: 2018-06-01..2020-12-31. Train effect: <effect>pp.
Observed/target days: 945 / 730. Instrument: bespoke (`structure_arm`), reason printed below.

<LIMITATIONS, quoted verbatim from armed_measurement.LIMITATIONS>

## Gate output (verbatim)

<paste the command's full stdout>
```

```bash
git add docs/superpowers/results/<run-date>-v126-structure-stage0.md
git commit -m "docs(v126): stage 0 MDE -- <verdict>"
```

`REFUSED` → V126-12, budget intact.

---

### Task V126-10: Stage 2 — walk-forward

**Files:**
- Create (local): `data/v126/arms_walkforward.json`
- Create: `docs/superpowers/results/<run-date>-v126-structure-stage2.md` and `.json`

**Interfaces:**
- Consumes: `<cell>`; Run 1 rows for 2021, 2022, 2023 — **first read of the fold years by anyone**.
- Produces: `**Overall: PASS**` (unlocks V126-11's replay) or FAIL.

- [ ] **Step 1: Build the fold arms**

```bash
python scripts/backtest/measure_structure_arm.py arms --stage walkforward --cell <cell> --out data/v126/arms_walkforward.json
```

Expected: exit 0, three folds (`2021`, `2022`, `2023`) each carrying a baseline and a component arm.

- [ ] **Step 2: Run the walk-forward gate**

```bash
python scripts/backtest/validate_component.py --stage walkforward --arms data/v126/arms_walkforward.json --title "v126 structure-break armed entries <cell>" --window "2021..2023" --out-json docs/superpowers/results/<run-date>-v126-structure-stage2.json --bespoke-instrument "structure_arm: v126 armed structure-break replay (measure_arms.py has no armed-entry engine)"
```

Expected: `PASS -- stage 2 walkforward win-rate consistency gate` (exit 0) or `FAIL -- ...` (exit 1), against the pre-registered clause — **>= 2 of 3 folds improving, no fold worse than −1.0pp, per-fold N >= 30**. A fold with N < 30 fails the clause; it is not dropped to rescue the average.

- [ ] **Step 3: Write and commit the record**

Create `docs/superpowers/results/<run-date>-v126-structure-stage2.md`. V126-11's replay reads this file for the literal marker `**Overall: PASS**`, so write `PASS` there only if the gate printed `PASS`:

```markdown
# v126 structure-break armed entries — Stage 2 (walk-forward)

**Overall: <PASS | FAIL>**

Cell: <cell>. Fold-test years: 2021 / 2022 / 2023.
Clause: >= 2 of 3 folds improving, no fold worse than −1.0pp, per-fold N >= 30.

| fold | N | ΔWR pp |
|---|---|---|
| 2021 | <n> | <dwr> |
| 2022 | <n> | <dwr> |
| 2023 | <n> | <dwr> |

<LIMITATIONS, quoted verbatim>

## Gate output (verbatim)

<paste the command's full stdout>
```

Fill the table from the JSON's `folds` list (`test_years`, `n`, `delta_win_rate_pp`).

```bash
git add docs/superpowers/results/<run-date>-v126-structure-stage2.md docs/superpowers/results/<run-date>-v126-structure-stage2.json
git commit -m "docs(v126): stage 2 walk-forward -- <PASS|FAIL>"
```

FAIL → V126-12, budget intact.

---

### Task V126-11: Stage 3 — VALIDATION, one shot

**Files:**
- Create (local): `data/v126/run2/*`, `data/v126/arms_validation.json`, `data/v126/permutation.json`
- Create: `docs/superpowers/results/<run-date>-v126-structure-stage3.md` and `.json`

**Interfaces:**
- Consumes: `<cell>`; V126-10's Stage 2 doc reading `**Overall: PASS**`.
- Produces: the plan's terminal verdict.

**This is the one shot. It runs once, on a window no one has inspected for structure-break behaviour. Do not run it to "see", and do not re-run it after reading it.**

- [ ] **Step 1: Replay the VALIDATION window**

Dispatch to `backtest-runner`:

```bash
python scripts/backtest/measure_structure_arm.py replay --run run2 --stage2-doc docs/superpowers/results/<run-date>-v126-structure-stage2.md
```

Expected: exit 0, `complete: <N> rows`, no `progress.txt` left. The script refuses (exit 3) unless the Stage 2 doc contains `**Overall: PASS**`; that refusal is the integrity guard working, not a bug to route around.

- [ ] **Step 2: Build the arms and the permutation**

```bash
python scripts/backtest/measure_structure_arm.py arms --stage validation --cell <cell> --out data/v126/arms_validation.json
python scripts/backtest/measure_structure_arm.py permute --cell <cell> --out-json data/v126/permutation.json
```

`permute` is long (200 draws over every triggered arm, memoised per arm-bar); dispatch it to `backtest-runner` too. Expected: `permutation p = <p>`. A `None` p means no valid permuted ΔWR — it is carried forward as missing, which Step 3 turns into a FAIL.

- [ ] **Step 3: Run the gate**

```bash
P=$(python -c "import json; v=json.load(open('data/v126/permutation.json'))['p_value']; print('' if v is None else v)")
python scripts/backtest/validate_component.py --stage validation --arms data/v126/arms_validation.json --title "v126 structure-break armed entries <cell>" --window "2024-01-01..2025-12-31" ${P:+--permutation-p $P} --bespoke-instrument "structure_arm: v126 armed structure-break replay (measure_arms.py has no armed-entry engine)" --out-md docs/superpowers/results/<run-date>-v126-structure-stage3.md --out-json docs/superpowers/results/<run-date>-v126-structure-stage3.json
```

Expected: clauses 1–5 each resolved; clause 6 (`mechanism`) reports `SKIPPED` ("not a subset feature") and never blocks. Without `--permutation-p` the permutation clause reads `FAIL -- no permutation p supplied`, and that is the verdict — **a missing p is a FAIL, not a skip.**

- [ ] **Step 4: Complete and commit the record**

Append to the generated `docs/superpowers/results/<run-date>-v126-structure-stage3.md`: the permutation JSON (`p_value`, `n`, `n_valid`, `seed`), `LIMITATIONS` quoted verbatim, and one line recording the cache's last common date as observed in V126-7 Step 1.

```bash
git add docs/superpowers/results/<run-date>-v126-structure-stage3.md docs/superpowers/results/<run-date>-v126-structure-stage3.json
git commit -m "docs(v126): stage 3 VALIDATION -- <PASS|FAIL>"
```

---

### Task V126-12: Close-out

Runs whatever verdict ended the measurement.

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (closed pre-registrations table)
- Modify: `docs/superpowers/specs/2026-10-02-v126-structure-break-armed-entries-design.md` (§4.4 outcome line)
- Move: the three plan parts `docs/superpowers/plans/2026-10-02-v126-structure-break-armed-entries_{0-index,1-replay-and-grid,2-script-and-runs}.md` and the spec → `implemented/` (the code reached `main`, so not `no-lift/`)

- [ ] **Step 1: Add the closed-table row**

Append a row to `### Closed pre-registrations — do not re-run these` in `docs/claude/backtest-methodology.md`, in the table's existing three-column shape (see the v88/v90 rows). The component cell reads `Structure-break armed entries — MSB / HL after the zone test, one arm per touch episode (v126)`. The outcome cell states, in order: the verdict in bold with `budget intact` or `budget spent`; the stage it ended at; the selected cell (or that none was selected, and the rule's pick); the numbers that decided it (Stage 1: the pick's cut %, ΔWR, ΔExpR, its plateau rows on `N` and `k`, both trigger rows, and its alert-volume ratio; Stage 2: per-fold ΔWR and N; Stage 3: every clause's detail line and the permutation p); and one sentence on what reopening would need (**a genuinely new mechanism**, not a looser threshold or another grid over these knobs). The record cell lists every results doc by path.

- [ ] **Step 2: Record the outcome in the spec**

Append to the spec's §4.4: `**Outcome (<date>):** <verdict> at <stage>; the live ARMED lifecycle <is not written | is brainstormed next>.` If the verdict is PASS, say so in the close-out commit message so the next session picks it up.

- [ ] **Step 3: Amend `Edge:` only if the prediction was wrong**

A negative measurement stays `Edge: expectancy` with `Bump: none`. Change nothing unless the work turned out to buy something other than predicted, and then say why in one clause.

- [ ] **Step 4: Move the documents and commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot mv docs/superpowers/plans/2026-10-02-v126-structure-break-armed-entries_0-index.md docs/superpowers/plans/implemented/
git -C E:/Documents/Private/Projects/Discord-Bot mv docs/superpowers/plans/2026-10-02-v126-structure-break-armed-entries_1-replay-and-grid.md docs/superpowers/plans/implemented/
git -C E:/Documents/Private/Projects/Discord-Bot mv docs/superpowers/plans/2026-10-02-v126-structure-break-armed-entries_2-script-and-runs.md docs/superpowers/plans/implemented/
git -C E:/Documents/Private/Projects/Discord-Bot mv docs/superpowers/specs/2026-10-02-v126-structure-break-armed-entries-design.md docs/superpowers/specs/implemented/
git -C E:/Documents/Private/Projects/Discord-Bot add docs/claude/backtest-methodology.md docs/superpowers/specs/implemented/2026-10-02-v126-structure-break-armed-entries-design.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v126): close out structure-break armed entries -- <verdict>"
```

Verify with `git show --stat HEAD` that the spec's §4.4 edit is in the commit — a `git mv` of a file edited in the same breath can land the rename without the edit. The `backtest-methodology.md` change is a `docs/claude/` edit: per `working-conventions.md` § Codex mirror, add the condensed row to root `AGENTS.md` in the same commit if `AGENTS.md` mirrors the closed table (`grep -n "v90" AGENTS.md` — if it lists v90's closure, add v126's the same way; if not, nothing to mirror).

- [ ] **Step 5: Remove the worktree**

Per `document-lifecycle.md`: confirm the branch is merged (`git -C E:/Documents/Private/Projects/Discord-Bot rev-list --count main..2026-10-02-v126-structure-break-armed-entries` prints `0`), then `git -C E:/Documents/Private/Projects/Discord-Bot worktree remove .claude/worktrees/2026-10-02-v126-structure-break-armed-entries`. The branch name contains neither `backup` nor `stable-`; still, deleting the branch is the human partner's call — leave it.
