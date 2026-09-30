# v105 PENDING daily range continuation — Part 2a: arms and shadow telemetry (Tasks 6–7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Header, global constraints, review focus and parallelisation live in
`2026-09-25-v105-pending-range-continuation_0-index.md`. Parts 1a–1b (Tasks 1–5)
must be merged into the working branch first. Every task below consumes its
symbols.

**File map for this part**

| File | Task | Responsibility |
|---|---|---|
| `swingbot/core/backtesting/range_arms.py` | 6, 9 | provenance, paired arms, fold arms, cell selection, holdout guards |
| `scripts/backtest/measure_pending_range.py` | 6, 9 | pilot / collect / select / arms / prereg / holdout CLI |
| `swingbot/core/scanning/range_shadow.py` | 7 | append-only shadow events, `ShadowBook`, summary |
| `scripts/reports/range_shadow_report.py` | 7 | read-only markdown report |
| `swingbot/core/scanning/scan_run.py` | 7 | record shadow telemetry after the range pass |
| `swingbot/commands/scanning/loops.py` | 7 | record `range_pending` deliveries |
| `docs/superpowers/results/…-v105-*.md` | 8, 9, 10 | TRAIN finding, pre-registration, holdout verdict |

# Phase 2 — Measurement and forward evidence

### Task 6: Produce paired, stamped measurement arms

**Files:**
- Create: `swingbot/core/backtesting/range_arms.py`
- Create: `scripts/backtest/measure_pending_range.py`
- Test: `tests/backtesting/test_pending_range_arms.py`

**Interfaces:**
- Consumes: `range_replay.replay_ranges`, `candidates_by_index`, `SCORABLE`, `EXIT_LIMITATION` (Task 4);
  `acceptance.ArmTrade`, `win_rate`, `expectancy_r`, `NON_INFERIORITY_R`, `CLOSED`;
  `scripts/data/fetch_backtest_data.load_cached(ticker)`; `backtest_cache.CACHE_DIR`;
  `universe.liquidity_reason(df)`, `universe.data_quality_issues(df, symbol)`.
- Produces:
  - `TRAIN = ("2020-01-01","2023-12-31")`, `FOLD_TEST_YEARS = ("2021","2022","2023")`,
    `FORBIDDEN_WINDOWS`, `REQUIRED_META`, `HASHED_SOURCES`, `MIN_COMPONENT_N = 30`
  - `code_hash(root) -> str`, `cache_manifest(paths) -> str`, `git_state(root) -> tuple[str, bool]`
  - `provenance(*, root, cache_dir, cache_files, universe, horizons, window) -> dict`
  - `check_provenance(meta)`, `refuse_forbidden(window)`
  - `to_arm_trade(row: dict) -> ArmTrade | None`
  - `paired_arms(rows, meta, *, cell, direction, window, path="per_horizon") -> {"baseline": [...], "component": [...]}`
  - `fold_arms(rows, meta, *, cell, direction, path="per_horizon") -> {"folds": [...]}`
  - `score_arms(arms) -> dict`, `neighbours(cell) -> list`, `select_cell(scores) -> dict`
  - `enumerate_units(tickers) -> list[tuple]`
  - rows are `ReplayRow.to_dict()` plus `"path": "per_horizon" | "live"`; `cell` is `(n, d)`.

- [ ] **Step 1: Write the failing tests**

`tests/backtesting/test_pending_range_arms.py`:

```python
"""v105 Task 6: paired, provenance-stamped arms for the range source."""
import subprocess
import sys
from pathlib import Path

import pytest

from swingbot.core.backtesting import range_arms as ra
from swingbot.core.backtesting import range_replay as rr
from swingbot.core.planning import range_source
from tests.market.range_fixtures import FLAT, fixed_levels, long_frame, short_frame

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "backtest" / "measure_pending_range.py"


@pytest.fixture(autouse=True)
def _levels(monkeypatch):
    monkeypatch.setattr(range_source, "range_target_levels", fixed_levels)


def _meta(**kw):
    base = dict(code_hash="c" * 64, git_commit="a" * 40, git_dirty=False, cache_dir="x",
                cache_manifest="m" * 64, universe=["AAA", "BBB"], horizons=["4w"],
                window=["2023-01-01", "2023-12-31"], exit_model=rr.EXIT_LIMITATION,
                cells=[[20, 0.75]])
    base.update(kw)
    return base


def _rows(frame, ticker):
    cands, cache, rows = rr.candidates_by_index(ticker, frame, 20), {}, []
    for pressure in (False, True):
        res = rr.replay_ranges(ticker, frame, ("4w",), n=20, d=0.75, require_pressure=pressure,
                               candidates=cands, build_cache=cache)
        rows += [dict(r.to_dict(), path="per_horizon") for r in res.rows]
    return rows


def _arms(rows, direction="bullish"):
    return ra.paired_arms(rows, _meta(), cell=(20, 0.75), direction=direction,
                          window=("2023-01-01", "2023-12-31"))


def test_pressure_changes_acceptance_not_shared_trade_arithmetic():
    arms = _arms(_rows(long_frame([FLAT] * 6), "AAA"))
    base = {tuple(t[k] for k in ("ticker", "strategy", "horizon_key", "entry_date")): t for t in arms["baseline"]}
    shared = [t for t in arms["component"]
              if (t["ticker"], t["strategy"], t["horizon_key"], t["entry_date"]) in base]
    assert shared
    for t in shared:
        twin = base[(t["ticker"], t["strategy"], t["horizon_key"], t["entry_date"])]
        assert (t["outcome"], t["r_multiple"], t["planned_rr"]) == (
            twin["outcome"], twin["r_multiple"], twin["planned_rr"])


def test_long_and_short_arms_are_separate():
    rows = _rows(long_frame([FLAT] * 6), "AAA") + _rows(short_frame([FLAT] * 6), "BBB")
    bull, bear = _arms(rows, "bullish"), _arms(rows, "bearish")
    assert bull["component"] and bear["component"]
    assert all("bullish" in t["strategy"] for t in bull["baseline"] + bull["component"])
    assert all("bearish" in t["strategy"] for t in bear["baseline"] + bear["component"])


def test_unscorable_outcomes_never_enter_an_arm():
    row = dict(_rows(long_frame([FLAT] * 6), "AAA")[0], outcome="unresolved", r_multiple=None)
    assert ra.to_arm_trade(row) is None
    assert ra.to_arm_trade(dict(row, outcome="cancelled_risk_cap")) is None


def test_full_universe_enumeration():
    units = ra.enumerate_units(["AAA", "BBB"])
    assert len(units) == 2 * 3 * 10 * 3 * 2
    assert len(set(units)) == len(units)


@pytest.mark.parametrize("kw", [dict(code_hash=""), dict(cache_manifest=None), dict(universe=[]),
                                dict(git_dirty=True)])
def test_refuses_missing_or_dirty_provenance(kw):
    with pytest.raises(ValueError):
        ra.paired_arms([], _meta(**kw), cell=(20, 0.75), direction="bullish",
                       window=("2023-01-01", "2023-12-31"))


def test_refuses_rows_dated_after_the_stamped_window():
    rows = _rows(long_frame([FLAT] * 6), "AAA")
    with pytest.raises(ValueError, match="after the stamped window"):
        ra.paired_arms(rows, _meta(window=["2022-01-01", "2022-12-31"]), cell=(20, 0.75),
                       direction="bullish", window=("2022-01-01", "2022-12-31"))


@pytest.mark.parametrize("window", [("2023-06-01", "2024-02-01"), ("2026-03-01", "2026-04-01")])
def test_forbidden_windows_are_refused(window):
    with pytest.raises(ValueError, match="forbidden"):
        ra.refuse_forbidden(window)


def test_train_window_is_allowed():
    ra.refuse_forbidden(ra.TRAIN)


def _score(n, d_wr, d_exp):
    return {"n_component": n, "d_wr": d_wr, "d_exp": d_exp}


def test_select_cell_needs_a_plateau():
    scores = {(n, d): _score(10, -1.0, -0.1) for n in (10, 15, 20) for d in (0.25, 0.5, 0.75)}
    scores[(15, 0.5)] = _score(40, 2.0, 0.05)
    assert ra.select_cell(scores)["cell"] is None
    for cell in ((10, 0.5), (15, 0.25)):
        scores[cell] = _score(40, 1.0, 0.02)
    picked = ra.select_cell(scores)
    assert (picked["cell"], picked["reason"]) == ((15, 0.5), "plateau")


def test_select_cell_ties_go_to_smaller_d_then_larger_n():
    scores = {(n, d): _score(40, 1.0, 0.03) for n in (10, 15, 20) for d in (0.25, 0.5, 0.75)}
    assert ra.select_cell(scores)["cell"] == (20, 0.25)


def test_score_arms_reports_deltas():
    arms = _arms(_rows(long_frame([FLAT] * 6), "AAA"))
    score = ra.score_arms(arms)
    assert set(score) >= {"n_baseline", "n_component", "wr_baseline", "wr_component",
                          "d_wr", "exp_baseline", "exp_component", "d_exp", "removed"}


def test_measure_script_help_and_dry_run():
    help_run = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert help_run.returncode == 0 and "collect" in help_run.stdout
    dry = subprocess.run([sys.executable, str(SCRIPT), "collect", "--out", "unused.jsonl",
                          "--tickers", "AAA,BBB", "--dry-run"], capture_output=True, text=True, cwd=ROOT)
    assert dry.returncode == 0, dry.stderr
    assert "units: 360" in dry.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_pending_range_arms.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'swingbot.core.backtesting.range_arms'`.

- [ ] **Step 3: Implement the arms module**

`swingbot/core/backtesting/range_arms.py`:

```python
"""v105: paired, provenance-stamped measurement arms for the range source.

v100's ArmEngine has not landed (docs/superpowers/results/2026-09-25-v105-asof-contract.md),
so this is the bespoke adapter. It emits exactly the arms JSON
scripts/backtest/validate_component.py reads, so the v72 gate is unchanged.
Baseline = pressure off, component = pressure on, same (N, d), same code,
same exit model. Pressure only removes candidates; it never re-prices a
shared one (range_replay caches one plan per (n, bar, horizon)).
"""
from __future__ import annotations

import dataclasses
import hashlib
import subprocess
from pathlib import Path

from swingbot.core.backtesting.acceptance import (
    CLOSED, NON_INFERIORITY_R, ArmTrade, expectancy_r, win_rate)
from swingbot.core.backtesting.range_replay import SCORABLE
from swingbot.core.market.range_candidate import D_GRID, N_GRID, STRATEGY_NAME
from swingbot.core.market.strategy_types import HORIZONS

TRAIN = ("2020-01-01", "2023-12-31")
FOLD_TEST_YEARS = ("2021", "2022", "2023")
#: Spent or reserved windows no v105 selection or validation may touch:
#: the used 2024-25 VALIDATION window, and v104's 2026 holdout (which may
#: extend to 2026-12-31 under its thin-holdout rule).
FORBIDDEN_WINDOWS = (("2024-01-01", "2025-12-31"), ("2026-01-01", "2026-12-31"))
REQUIRED_META = ("code_hash", "git_commit", "cache_dir", "cache_manifest", "universe",
                 "horizons", "window", "exit_model", "cells")
HASHED_SOURCES = (
    "swingbot/core/market/range_candidate.py", "swingbot/core/planning/range_builder.py",
    "swingbot/core/planning/range_source.py", "swingbot/core/backtesting/range_replay.py",
    "swingbot/core/backtesting/range_arms.py", "swingbot/core/planning/exit_sim.py",
    "swingbot/core/planning/lifecycle.py", "swingbot/core/planning/targets.py",
    "swingbot/core/market/levels.py", "swingbot/core/risk_limits.py",
    "scripts/backtest/measure_pending_range.py")
MIN_COMPONENT_N = 30
PATHS = ("per_horizon", "live")


def code_hash(root) -> str:
    digest = hashlib.sha256()
    for rel in HASHED_SOURCES:
        digest.update(rel.encode())
        digest.update((Path(root) / rel).read_bytes())
    return digest.hexdigest()


def cache_manifest(paths) -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(p) for p in paths):
        digest.update(path.name.encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def git_state(root) -> tuple[str, bool]:
    def git(*args):
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              check=True).stdout.strip()
    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain", "--", "swingbot", "scripts"))


def provenance(*, root, cache_dir, cache_files, universe, horizons, window) -> dict:
    from swingbot.core.backtesting.range_replay import EXIT_LIMITATION, EXIT_SCALE_OUT
    commit, dirty = git_state(root)
    return {"code_hash": code_hash(root), "git_commit": commit, "git_dirty": dirty,
            "cache_dir": str(cache_dir), "cache_manifest": cache_manifest(cache_files),
            "universe": sorted(universe), "horizons": list(horizons), "window": list(window),
            "exit_model": f"simulate_exit scale_out={EXIT_SCALE_OUT}; {EXIT_LIMITATION}",
            "cells": [[n, d] for n in N_GRID for d in D_GRID]}


def check_provenance(meta: dict) -> None:
    missing = [k for k in REQUIRED_META if meta.get(k) in (None, "", [])]
    if missing:
        raise ValueError(f"arm provenance missing {missing}: an unstamped arm is not scorable")
    if meta.get("git_dirty") is not False:
        raise ValueError("arms from a dirty (or unknown) tree are not scorable")


def refuse_forbidden(window) -> None:
    for lo, hi in FORBIDDEN_WINDOWS:
        if window[0] <= hi and window[1] >= lo:
            raise ValueError(f"window {window[0]}..{window[1]} overlaps forbidden {lo}..{hi}")


def to_arm_trade(row: dict) -> ArmTrade | None:
    """Scorable rows only: unresolved entry bars and paper risk-cap cancels
    are counted in the report, never scored as wins or losses."""
    if row["outcome"] not in SCORABLE:
        return None
    return ArmTrade(ticker=row["ticker"], strategy=f"{STRATEGY_NAME} {row['direction']} N{row['n']}",
                    horizon_key=row["horizon_key"], entry_date=row["signal_date"],
                    outcome=row["outcome"], r_multiple=row["r_multiple"], planned_rr=row["planned_rr"])


def _select(rows, *, cell, direction, window, path, pressure) -> list[dict]:
    n, d = cell
    trades = (to_arm_trade(r) for r in rows
              if r["path"] == path and r["n"] == n and r["d"] == d
              and r["require_pressure"] is pressure and r["direction"] == direction
              and window[0] <= r["signal_date"] <= window[1])
    return [dataclasses.asdict(t) for t in trades if t is not None]


def paired_arms(rows, meta, *, cell, direction, window, path="per_horizon") -> dict:
    check_provenance(meta)
    refuse_forbidden(window)
    late = [r for r in rows if r["signal_date"] > meta["window"][1]]
    if late:
        raise ValueError(f"{len(late)} row(s) dated after the stamped window end {meta['window'][1]}")
    kw = dict(cell=cell, direction=direction, window=window, path=path)
    return {"baseline": _select(rows, pressure=False, **kw),
            "component": _select(rows, pressure=True, **kw)}


def fold_arms(rows, meta, *, cell, direction, path="per_horizon") -> dict:
    return {"folds": [dict(test_year=year, **paired_arms(
        rows, meta, cell=cell, direction=direction, window=(f"{year}-01-01", f"{year}-12-31"), path=path))
        for year in FOLD_TEST_YEARS]}


def _delta(a, b):
    return None if a is None or b is None else b - a


def score_arms(arms: dict) -> dict:
    base = [ArmTrade(**t) for t in arms["baseline"]]
    comp = [ArmTrade(**t) for t in arms["component"]]
    kept = {t.key for t in comp}
    removed = [t for t in base if t.key not in kept]
    wr_b, wr_c, ex_b, ex_c = win_rate(base), win_rate(comp), expectancy_r(base), expectancy_r(comp)
    return {"n_baseline": sum(t.outcome in CLOSED for t in base),
            "n_component": sum(t.outcome in CLOSED for t in comp),
            "wr_baseline": wr_b, "wr_component": wr_c, "d_wr": _delta(wr_b, wr_c),
            "exp_baseline": ex_b, "exp_component": ex_c, "d_exp": _delta(ex_b, ex_c),
            "removed": {"n": sum(t.outcome in CLOSED for t in removed),
                        "win_rate": win_rate(removed), "expectancy_r": expectancy_r(removed)}}


def _eligible(score: dict) -> bool:
    return (score["n_component"] >= MIN_COMPONENT_N and score["d_wr"] is not None
            and score["d_wr"] > 0 and score["d_exp"] is not None
            and score["d_exp"] >= NON_INFERIORITY_R)


def neighbours(cell) -> list:
    n_i, d_i = N_GRID.index(cell[0]), D_GRID.index(cell[1])
    out = []
    for dn, dd in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        if 0 <= n_i + dn < len(N_GRID) and 0 <= d_i + dd < len(D_GRID):
            out.append((N_GRID[n_i + dn], D_GRID[d_i + dd]))
    return out


def select_cell(scores: dict) -> dict:
    """Frozen TRAIN selection (v105 as-of note): eligible = component n >= 30,
    dWR > 0, dExpR >= NON_INFERIORITY_R; plateau = eligible with >= 2 eligible
    grid neighbours; highest dExpR; ties -> smaller d, then larger N."""
    ok = {cell for cell, score in scores.items() if _eligible(score)}
    plateau = [cell for cell in ok if sum(nb in ok for nb in neighbours(cell)) >= 2]
    if not plateau:
        return {"cell": None, "reason": "no-eligible-cell", "eligible": sorted(ok), "plateau": []}
    best = min(plateau, key=lambda c: (-scores[c]["d_exp"], c[1], -c[0]))
    return {"cell": best, "reason": "plateau", "eligible": sorted(ok), "plateau": sorted(plateau)}


def enumerate_units(tickers) -> list[tuple]:
    return [(t, n, hk, d, p) for t in tickers for n in N_GRID for hk in HORIZONS
            for d in D_GRID for p in (False, True)]
```

- [ ] **Step 4: Implement the measurement command**

`scripts/backtest/measure_pending_range.py`:

```python
#!/usr/bin/env python3
"""v105 PENDING range continuation -- TRAIN measurement (never the holdout).

Read docs/claude/backtest-methodology.md and .claude/skills/backtest-gate
before running. Subcommands:
  pilot    bounded ticker subset: reachability, issued/filled counts, runtime
  collect  full cached universe x 10 horizons x N x d x pressure -> rows JSONL
  select   score the 9 cells per direction on TRAIN and apply select_cell
  arms     write validate_component arms JSON (--stage mde | walkforward)
Every run prints flushed `[k/N] P% ticker` progress. Rows and a
`<out>.meta.json` provenance stamp are written next to each other.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data")]

import pandas as pd  # noqa: E402

from fetch_backtest_data import load_cached  # noqa: E402
from swingbot.core.backtesting import range_arms as ra  # noqa: E402
from swingbot.core.backtesting import range_replay as rr  # noqa: E402
from swingbot.core.market.range_candidate import D_GRID, N_GRID  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.core.marketdata import backtest_cache  # noqa: E402
from swingbot.core.marketdata.universe import data_quality_issues, liquidity_reason  # noqa: E402

TAIL_DAYS = 400      # outcome bars read past the window end (exit walk only)


class Progress:
    """Flushed `[k/N] P% label` lines: the percent answers "how far along"."""

    def __init__(self, total):
        self.total, self.done, self.t0 = max(total, 1), 0, time.monotonic()

    def tick(self, label):
        self.done += 1
        pct = self.done / self.total * 100
        eta = (time.monotonic() - self.t0) / self.done * (self.total - self.done)
        print(f"[{self.done}/{self.total}] {pct:.0f}% {label} eta {eta / 60:.1f}m", flush=True)


def _universe(tickers_arg=None) -> list[str]:
    if tickers_arg:
        return tickers_arg.split(",")
    return sorted(p.stem for p in backtest_cache.CACHE_DIR.glob("*.csv"))


def _frame(ticker, window):
    df = load_cached(ticker)
    if df is None or liquidity_reason(df) is not None or data_quality_issues(df, ticker):
        return None
    return df.loc[: pd.Timestamp(window[1]) + pd.Timedelta(days=TAIL_DAYS)]


def _ticker_rows(args) -> tuple[str, list, dict]:
    from swingbot.scan_params import ScanParams
    ticker, window = args
    df = _frame(ticker, window)
    if df is None:
        return ticker, [], {"screened_out": 1}
    params = ScanParams.from_config()     # once per ticker, frozen for every arm
    rows, counts = [], Counter()
    for n in N_GRID:
        cands, cache = rr.candidates_by_index(ticker, df, n), {}
        counts[f"N{n}|candidates"] += sum(window[0] <= c.asof <= window[1] for c in cands.values())
        for path, horizon_sets in (("per_horizon", [(hk,) for hk in HORIZONS]), ("live", [tuple(HORIZONS)])):
            for horizons in horizon_sets:
                for d in D_GRID:
                    for pressure in (False, True):
                        res = rr.replay_ranges(ticker, df, horizons, n=n, d=d, require_pressure=pressure,
                                               params=params, candidates=cands, build_cache=cache)
                        tag = f"{path}|N{n}|d{d:.2f}|P{int(pressure)}"
                        counts.update({f"{tag}|{k}": v for k, v in res.counts.items()})
                        rows += [dict(r.to_dict(), path=path) for r in res.rows
                                 if window[0] <= r.signal_date <= window[1]]
    return ticker, rows, dict(counts)


def _collect(tickers, window, out, workers) -> dict:
    ra.refuse_forbidden(window)
    progress, counts = Progress(len(tickers)), Counter()
    out_path = Path(out)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh, ProcessPoolExecutor(max_workers=workers) as pool:
        for ticker, rows, ticker_counts in pool.map(_ticker_rows, [(t, window) for t in tickers]):
            for row in rows:
                fh.write(json.dumps(row, default=str) + "\n")
            counts.update(ticker_counts)
            progress.tick(f"{ticker} rows={len(rows)}")
    tmp.replace(out_path)
    files = [backtest_cache.CACHE_DIR / f"{t}.csv" for t in tickers
             if (backtest_cache.CACHE_DIR / f"{t}.csv").exists()]
    meta = ra.provenance(root=ROOT, cache_dir=backtest_cache.CACHE_DIR, cache_files=files,
                         universe=tickers, horizons=list(HORIZONS), window=window)
    meta["counts"] = dict(counts)
    Path(f"{out}.meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def _load(rows_path) -> tuple[list, dict]:
    rows = [json.loads(line) for line in Path(rows_path).read_text(encoding="utf-8").splitlines() if line]
    meta = json.loads(Path(f"{rows_path}.meta.json").read_text(encoding="utf-8"))
    return rows, meta


def _cmd_pilot(args):
    tickers = _universe(args.tickers)[: args.max_tickers]
    print(f"pilot units: {len(ra.enumerate_units(tickers))}", flush=True)
    if args.dry_run:
        return
    meta = _collect(tickers, ra.TRAIN, args.out, args.workers)
    rows, _ = _load(args.out)
    filled = Counter((r["path"], r["direction"], r["n"], r["d"], r["require_pressure"])
                     for r in rows if r["entry_date"] is not None)
    print(json.dumps({"counts": meta["counts"], "filled": {str(k): v for k, v in sorted(filled.items())}},
                     indent=1), flush=True)


def _cmd_collect(args):
    tickers = _universe(args.tickers)
    print(f"units: {len(ra.enumerate_units(tickers))}", flush=True)
    if args.dry_run:
        return
    _collect(tickers, ra.TRAIN, args.out, args.workers)


def _cmd_select(args):
    rows, meta = _load(args.rows)
    scores = {}
    for n in N_GRID:
        for d in D_GRID:
            arms = ra.paired_arms(rows, meta, cell=(n, d), direction=args.direction,
                                  window=ra.TRAIN, path=args.path)
            scores[(n, d)] = ra.score_arms(arms)
            print(f"N{n} d{d:.2f}: {json.dumps(scores[(n, d)], default=str)}", flush=True)
    picked = ra.select_cell(scores)
    Path(args.out).write_text(json.dumps({"direction": args.direction, "path": args.path,
                                          "scores": {f"N{n}-d{d:.2f}": s for (n, d), s in scores.items()},
                                          **picked}, indent=1, default=str), encoding="utf-8")
    print(f"selection: {picked['reason']} {picked['cell']}", flush=True)


def _cmd_arms(args):
    rows, meta = _load(args.rows)
    cell = (int(args.n), float(args.d))
    if args.stage == "walkforward":
        payload = ra.fold_arms(rows, meta, cell=cell, direction=args.direction, path=args.path)
    else:
        payload = ra.paired_arms(rows, meta, cell=cell, direction=args.direction,
                                 window=ra.TRAIN, path=args.path)
    Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"arms written: {args.out}", flush=True)


COMMANDS = {"pilot": _cmd_pilot, "collect": _cmd_collect, "select": _cmd_select, "arms": _cmd_arms}


def _parser():
    parser = argparse.ArgumentParser(description="v105 PENDING range continuation TRAIN measurement")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("pilot", "collect"):
        command = sub.add_parser(name)
        command.add_argument("--out", required=True)
        command.add_argument("--tickers", help="comma-separated subset")
        command.add_argument("--workers", type=int, default=4)
        command.add_argument("--dry-run", action="store_true")
    sub.choices["pilot"].add_argument("--max-tickers", type=int, default=25)
    for name in ("select", "arms"):
        command = sub.add_parser(name)
        command.add_argument("--rows", required=True)
        command.add_argument("--direction", required=True, choices=("bullish", "bearish"))
        command.add_argument("--path", default="per_horizon", choices=ra.PATHS)
        command.add_argument("--out", required=True)
    sub.choices["arms"].add_argument("--n", required=True, choices=[str(n) for n in N_GRID])
    sub.choices["arms"].add_argument("--d", required=True, choices=[f"{d:.2f}" for d in D_GRID])
    sub.choices["arms"].add_argument("--stage", required=True, choices=("mde", "walkforward"))
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v105 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Every other `scripts/backtest/*.py` imports `load_cached` the same way
(`scripts/data` on `sys.path`). If `measure_armed_entries.py` shows a
different idiom, match it.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_pending_range_arms.py`
Expected: `0 failed`, `0 xfailed`.

- [ ] **Step 6: Check complexity and commit**

```bash
python -m radon cc -s -n C swingbot/core/backtesting/range_arms.py scripts/backtest/measure_pending_range.py
git status --short
git add swingbot/core/backtesting/range_arms.py scripts/backtest/measure_pending_range.py tests/backtesting/test_pending_range_arms.py
git commit -m "feat(v105): paired provenance-stamped range arms, frozen cell selection, TRAIN measure command"
```

Expected radon: `_ticker_rows` is the only candidate for ≥ C. If it reaches
15, pull the `for d … for pressure …` body into `_arm_rows(ticker, df, horizons,
path, n, cands, cache, window, counts)`.

**Verification:** narrow run and the `--help` / `--dry-run` smoke inside it.

### Task 7: Capture prospective alert lead and broker divergence

**Files:**
- Create: `swingbot/core/scanning/range_shadow.py`
- Create: `scripts/reports/range_shadow_report.py`
- Modify: `swingbot/core/scanning/scan_run.py` (`_maybe_run_range_pass`, Task 5)
- Modify: `swingbot/commands/scanning/loops.py:523-537` (`_post_plan_events`)
- Test: `tests/backtesting/test_pending_range_shadow.py`

**Interfaces:**
- Consumes: `RangePassResult.shadow` / `.plans`, `RangeCell.cell_id`, `fresh_quote` (Task 5);
  `may_rearm` (Task 2); `plan_manager.RANGE_PENDING`, `Delivery`;
  `infra.jsonio.atomic_write_json(path, obj)`, `read_json(path, default)`;
  `strategy_pass.completed_frame`; `session.session_date(now)`.
- Produces:
  - `EVENT_KINDS`, `QUOTE_MAX_AGE_S = 15`
  - `append_event(kind, *, identity, ticker, at, detail=None, poll_interval_s=None, path=None) -> bool`
  - `class ShadowBook(state_file=None, events_file=None)` with `observe_ready(plan, cell_id, quote, *, at, poll_interval_s) -> bool`,
    `observe_quote(key, quote, *, at, session, session_open, poll_interval_s)`,
    `observe_bar(key, bar_date, high, low, close)`, `sweep(fresh_data, *, now, quote_fn, poll_interval_s)`,
    `record_notice(plan, kind, at)`, `save()`
  - `record_deliveries(events, deliveries, *, at=None, path=None) -> int`
  - `read_events(path=None) -> list[dict]`, `summarise(events) -> dict`, `render_markdown(summary) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/backtesting/test_pending_range_shadow.py`:

```python
"""v105 Task 7: prospective shadow telemetry for PENDING range plans."""
import json
import logging

import pytest

from swingbot.core.planning import range_source
from swingbot.core.planning.plan_manager import RANGE_PENDING, Delivery, PlanEvent
from swingbot.core.scanning import range_shadow as rs
from tests.market.range_fixtures import fixed_levels, long_frame

AT0, AT1, AT2 = "2026-10-05T14:00:00+00:00", "2026-10-05T15:30:00+00:00", "2026-10-06T13:35:00+00:00"


@pytest.fixture
def plan(monkeypatch):
    monkeypatch.setattr(range_source, "range_target_levels", fixed_levels)
    return range_source.range_plan_at(long_frame(), ticker="AAA", horizon_key="2w", n=20).plan


@pytest.fixture
def book(tmp_path):
    return rs.ShadowBook(state_file=str(tmp_path / "state.json"), events_file=str(tmp_path / "ev.jsonl"))


def _events(book):
    return rs.read_events(book.events_file)


def _key(plan, cell="N20-d0.75-P0"):
    return f"{plan.entry_context['range']['identity']}|{cell}"


def test_clock_order_and_lead_time(book, plan):
    assert book.observe_ready(plan, "N20-d0.75-P0", plan.trigger_price - 0.3, at=AT0, poll_interval_s=900)
    book.observe_quote(_key(plan), plan.trigger_price + 0.05, at=AT1, session="2026-10-05",
                       session_open=plan.trigger_price - 0.4, poll_interval_s=900)
    kinds = [e["kind"] for e in _events(book)]
    assert kinds == ["candidate_ready", "trigger_observed"]
    trig = _events(book)[1]
    assert trig["detail"]["lead_s"] == 5400 and trig["detail"]["late"] is False
    assert [e["at"] for e in _events(book)] == sorted(e["at"] for e in _events(book))


def test_duplicate_and_rolling_window_suppression(book, plan):
    assert book.observe_ready(plan, "N20-d0.75-P0", 105.9, at=AT0, poll_interval_s=900)
    assert not book.observe_ready(plan, "N20-d0.75-P0", 105.9, at=AT1, poll_interval_s=900)
    rolled = dict(plan.entry_context["range"], range_start=plan.created_at,
                  identity=plan.entry_context["range"]["identity"] + "-rolled")
    plan.entry_context = dict(plan.entry_context, range=rolled)
    assert not book.observe_ready(plan, "N20-d0.75-P0", 105.9, at=AT2, poll_interval_s=900)
    assert [e["kind"] for e in _events(book)] == ["candidate_ready"]


def test_stale_quote_records_nothing(book, plan):
    book.observe_ready(plan, "N20-d0.75-P0", 105.9, at=AT0, poll_interval_s=900)
    book.observe_quote(_key(plan), None, at=AT1, session="2026-10-05", session_open=None, poll_interval_s=900)
    assert [e["kind"] for e in _events(book)] == ["candidate_ready"]


def test_overnight_trigger_before_the_paper_poll_is_late(book, plan):
    book.observe_ready(plan, "N20-d0.75-P0", 105.9, at=AT0, poll_interval_s=900)
    book.observe_quote(_key(plan), plan.trigger_price + 1.0, at=AT2, session="2026-10-06",
                       session_open=plan.trigger_price + 0.8, poll_interval_s=900)
    kinds = [e["kind"] for e in _events(book)]
    assert kinds == ["candidate_ready", "gap_open", "trigger_observed"]
    assert _events(book)[-1]["detail"]["late"] is True


def test_daily_bar_catches_an_unpolled_trigger_and_close_back(book, plan):
    book.observe_ready(plan, "N20-d0.75-P0", 105.9, at=AT0, poll_interval_s=900)
    upper = plan.entry_context["range"]["upper"]
    book.observe_bar(_key(plan), "2099-01-02", plan.trigger_price + 0.3, upper - 1.0, upper - 0.2)
    by_kind = {e["kind"]: e for e in _events(book)}
    assert by_kind["trigger_observed"]["detail"]["source"] == "daily_bar"
    assert by_kind["plan_state"]["detail"]["close_back_inside"] is True


def test_expiry_and_no_broker_cancellation_claim(book, plan):
    book.observe_ready(plan, "N20-d0.75-P0", 105.9, at=AT0, poll_interval_s=900)
    for day in ("2099-01-02", "2099-01-03", "2099-01-04", "2099-01-05", "2099-01-06"):
        book.observe_bar(_key(plan), day, plan.trigger_price - 0.5, plan.stop_loss + 0.2, plan.trigger_price - 0.6)
    events = _events(book)
    assert events[-1]["kind"] == "expired"
    assert all(e["broker_status"] == "unknown" for e in events)


def test_missing_and_late_notice_are_visible(tmp_path, plan):
    path = str(tmp_path / "ev.jsonl")
    book = rs.ShadowBook(state_file=str(tmp_path / "s.json"), events_file=path)
    book.record_notice(plan, "notice_attempted", AT0)
    other = type(plan)(**{**plan.__dict__, "plan_id": "other"})
    book.record_notice(other, "notice_attempted", AT0)
    assert rs.record_deliveries([PlanEvent(plan.plan_id, RANGE_PENDING, {})],
                                [Delivery(plan.plan_id, "notice", RANGE_PENDING)], at=AT1, path=path) == 1
    summary = rs.summarise(rs.read_events(path))
    assert (summary["notices_attempted"], summary["notices_delivered"], summary["undelivered"]) == (2, 1, 1)
    assert summary["delivery_parity"] == 0.5


def test_append_failure_is_logged_not_silent(tmp_path, caplog):
    with caplog.at_level(logging.ERROR):
        ok = rs.append_event("candidate_ready", identity="x", ticker="AAA", at=AT0, path=str(tmp_path))
    assert ok is False
    assert "telemetry has a gap" in caplog.text


def test_unknown_kind_is_refused(tmp_path):
    with pytest.raises(ValueError):
        rs.append_event("broker_cancelled", identity="x", ticker="AAA", at=AT0, path=str(tmp_path / "e.jsonl"))


def test_summary_and_rendered_report(book, plan):
    book.observe_ready(plan, "N20-d0.75-P0", 105.9, at=AT0, poll_interval_s=900)
    book.observe_quote(_key(plan), plan.trigger_price + 0.05, at=AT1, session="2026-10-05",
                       session_open=plan.trigger_price - 0.4, poll_interval_s=900)
    summary = rs.summarise(_events(book))
    assert summary["ready"] == 1 and summary["triggers"] == 1
    assert summary["lead_minutes_median"] == 90.0 and summary["late_rate"] == 0.0
    text = rs.render_markdown(summary)
    assert "| Lead time, median" in text and "unknown" in text.lower()


def test_state_survives_a_reload(tmp_path, plan):
    kw = dict(state_file=str(tmp_path / "s.json"), events_file=str(tmp_path / "e.jsonl"))
    first = rs.ShadowBook(**kw)
    first.observe_ready(plan, "N20-d0.75-P0", 105.9, at=AT0, poll_interval_s=900)
    first.save()
    assert not rs.ShadowBook(**kw).observe_ready(plan, "N20-d0.75-P0", 105.9, at=AT1, poll_interval_s=900)
    assert json.loads((tmp_path / "s.json").read_text())["open"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_pending_range_shadow.py`
Expected: FAIL, `ImportError: cannot import name 'range_shadow'`.

- [ ] **Step 3: Implement the telemetry module**

`swingbot/core/scanning/range_shadow.py`:

```python
"""v105: append-only, timestamped prospective telemetry for range plans.

Records what daily bars cannot: when a candidate became ready, when its
PENDING notice was attempted and delivered, when the trigger was first
observed (and whether the session had already opened through it, i.e. it
fired before the bot's poll), gaps, same-day close-back, expiry and
invalidation. Every event carries broker_status "unknown": the bot never
has broker evidence, so no record may claim a broker order was cancelled.

PriceQuote carries no timestamp. A fresh quote is bounded by the 15 s price
TTL (QUOTE_MAX_AGE_S); poll_interval_s records how often the scan looks.
"""
from __future__ import annotations

import json
import logging
import os
import statistics
from datetime import datetime

from swingbot import config
from swingbot.core.infra.jsonio import atomic_write_json, read_json
from swingbot.core.market.session import session_date
from swingbot.core.planning.plan_manager import RANGE_PENDING
from swingbot.core.scanning.strategy_pass import completed_frame

log = logging.getLogger(__name__)

EVENT_KINDS = ("candidate_ready", "notice_attempted", "notice_delivered", "trigger_observed",
               "gap_open", "expired", "invalidated", "plan_state")
MAX_BYTES = 50 * 1024 * 1024
QUOTE_MAX_AGE_S = 15


def events_path() -> str:
    return os.path.join(config.DATA_DIR, "range_shadow_events.jsonl")


def state_path() -> str:
    return os.path.join(config.DATA_DIR, "range_shadow_state.json")


def append_event(kind, *, identity, ticker, at, detail=None, poll_interval_s=None, path=None) -> bool:
    if kind not in EVENT_KINDS:
        raise ValueError(f"unknown range shadow event {kind!r}")
    path = path or events_path()
    record = {"kind": kind, "identity": identity, "ticker": ticker, "at": at,
              "quote_max_age_s": QUOTE_MAX_AGE_S, "poll_interval_s": poll_interval_s,
              "broker_status": "unknown", "detail": detail or {}}
    try:
        if os.path.exists(path) and os.path.getsize(path) >= MAX_BYTES:
            os.replace(path, path + ".1")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except OSError:
        log.error("range shadow: could not append %s for %s -- telemetry has a gap",
                  kind, identity, exc_info=True)
        return False
    return True


def read_events(path=None) -> list[dict]:
    path = path or events_path()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _seconds(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()


def _crossed(entry, price) -> bool:
    return price >= entry["trigger"] if entry["direction"] == "bullish" else price <= entry["trigger"]


def _through_stop(entry, price) -> bool:
    return price <= entry["stop"] if entry["direction"] == "bullish" else price >= entry["stop"]


def _session_open(raw, session):
    if raw is None or len(raw) == 0 or raw.index[-1].date().isoformat() != session:
        return None
    return float(raw["Open"].iloc[-1])


class ShadowBook:
    """Open shadow candidates keyed by `identity|cell_id`, persisted atomically.
    `last_created` applies range_candidate.may_rearm per (ticker, cell) so a
    rolling window cannot re-record the same range under a new identity."""

    def __init__(self, state_file=None, events_file=None):
        self.state_file = state_file or state_path()
        self.events_file = events_file or events_path()
        state = read_json(self.state_file, {})
        self.open = state.get("open", {})
        self.last_created = state.get("last_created", {})

    def _emit(self, kind, key, ticker, at, detail=None, poll_interval_s=None):
        append_event(kind, identity=key, ticker=ticker, at=at, detail=detail,
                     poll_interval_s=poll_interval_s, path=self.events_file)

    def observe_ready(self, plan, cell_id, quote, *, at, poll_interval_s) -> bool:
        rng = plan.entry_context["range"]
        key, lane = f"{rng['identity']}|{cell_id}", f"{plan.ticker}|{cell_id}"
        prior = self.last_created.get(lane)
        if key in self.open or (prior is not None and rng["range_start"] <= prior):
            return False
        self.last_created[lane] = plan.created_at
        self.open[key] = {"ticker": plan.ticker, "direction": plan.direction,
                          "trigger": plan.trigger_price, "stop": plan.stop_loss, "tp1": plan.tp1,
                          "upper": rng["upper"], "lower": rng["lower"],
                          "created_at": plan.created_at, "expiry_bars": plan.expiry_bars,
                          "ready_at": at, "status": "open", "sessions_seen": []}
        self._emit("candidate_ready", key, plan.ticker, at, {
            "cell": cell_id, "plan_id": plan.plan_id, "trigger": plan.trigger_price,
            "quote": quote, "pressure": rng["pressure"], "asof": plan.created_at}, poll_interval_s)
        return True

    def observe_quote(self, key, quote, *, at, session, session_open, poll_interval_s) -> None:
        entry = self.open.get(key)
        if entry is None or entry["status"] != "open" or quote is None:
            return
        if not _crossed(entry, quote):
            if _through_stop(entry, quote):
                entry["status"] = "invalidated"
                self._emit("invalidated", key, entry["ticker"], at, {"quote": quote}, poll_interval_s)
            return
        late = session_open is not None and _crossed(entry, session_open)
        if late:
            self._emit("gap_open", key, entry["ticker"], at, {"session_open": session_open,
                                                               "session": session}, poll_interval_s)
        entry.update(status="triggered", triggered_at=at)
        self._emit("trigger_observed", key, entry["ticker"], at, {
            "source": "poll", "quote": quote, "late": late, "session": session,
            "lead_s": _seconds(entry["ready_at"], at)}, poll_interval_s)

    def observe_bar(self, key, bar_date, high, low, close) -> None:
        """One completed daily bar after creation: an unpolled trigger, same-day
        close-back and unresolved stop/TP1 ordering, then expiry counting."""
        entry = self.open.get(key)
        if entry is None or bar_date <= entry["created_at"] or bar_date in entry["sessions_seen"]:
            return
        entry["sessions_seen"].append(bar_date)
        bull = entry["direction"] == "bullish"
        touched = high >= entry["trigger"] if bull else low <= entry["trigger"]
        if touched and entry["status"] == "open":
            entry["status"] = "triggered"
            self._emit("trigger_observed", key, entry["ticker"], bar_date,
                       {"source": "daily_bar", "late": True, "lead_s": None, "session": bar_date})
        if touched:
            self._bar_state(key, entry, bar_date, high, low, close)
        if entry["status"] == "open" and len(entry["sessions_seen"]) >= entry["expiry_bars"]:
            entry["status"] = "expired"
            self._emit("expired", key, entry["ticker"], bar_date,
                       {"sessions": len(entry["sessions_seen"])})

    def _bar_state(self, key, entry, bar_date, high, low, close) -> None:
        bull = entry["direction"] == "bullish"
        back = close < entry["upper"] if bull else close > entry["lower"]
        stop_hit = low <= entry["stop"] if bull else high >= entry["stop"]
        tp_hit = high >= entry["tp1"] if bull else low <= entry["tp1"]
        self._emit("plan_state", key, entry["ticker"], bar_date, {
            "session": bar_date, "close_back_inside": bool(back),
            "unresolved": bool(stop_hit and tp_hit)})

    def sweep(self, fresh_data, *, now, quote_fn, poll_interval_s) -> None:
        at, session, quotes = now.isoformat(), session_date(now), {}
        for key, entry in list(self.open.items()):
            raw = fresh_data.get(entry["ticker"])
            if raw is None or len(raw) == 0 or entry["status"] != "open":
                continue
            frame = completed_frame(raw, now)
            for ts, bar in frame.loc[frame.index > entry["created_at"]].iterrows():
                self.observe_bar(key, ts.date().isoformat(), float(bar["High"]),
                                 float(bar["Low"]), float(bar["Close"]))
            if entry["status"] != "open":
                continue
            ticker = entry["ticker"]
            if ticker not in quotes:
                quotes[ticker] = quote_fn(ticker)
            self.observe_quote(key, quotes[ticker], at=at, session=session,
                               session_open=_session_open(raw, session), poll_interval_s=poll_interval_s)

    def record_notice(self, plan, kind, at) -> None:
        append_event(kind, identity=plan.plan_id, ticker=plan.ticker, at=at,
                     detail={"range_identity": plan.entry_context["range"]["identity"]},
                     path=self.events_file)

    def save(self) -> None:
        live = {k: v for k, v in self.open.items() if v["status"] in ("open", "triggered")}
        atomic_write_json(self.state_file, {"open": live, "last_created": self.last_created})


def record_deliveries(events, deliveries, *, at=None, path=None) -> int:
    """notice_delivered for each acknowledged range_pending delivery."""
    at = at or datetime.now().astimezone().isoformat()
    tickers = {e.plan_id: e.detail.get("ticker") for e in events}
    count = 0
    for delivery in deliveries:
        if delivery.kind == "notice" and delivery.value == RANGE_PENDING:
            append_event("notice_delivered", identity=delivery.plan_id,
                         ticker=tickers.get(delivery.plan_id), at=at, path=path)
            count += 1
    return count


def _median(values):
    return float(statistics.median(values)) if values else None


def _p10(values):
    return float(sorted(values)[max(0, int(len(values) * 0.1) - 1)]) if values else None


def _share(part, whole):
    return round(part / whole, 4) if whole else None


def summarise(events) -> dict:
    by = {kind: [e for e in events if e["kind"] == kind] for kind in EVENT_KINDS}
    triggers = by["trigger_observed"]
    leads = [e["detail"]["lead_s"] / 60 for e in triggers if e["detail"].get("lead_s") is not None]
    attempted = {e["identity"] for e in by["notice_attempted"]}
    delivered = {e["identity"] for e in by["notice_delivered"]}
    ready = {e["identity"] for e in by["candidate_ready"]}
    states = by["plan_state"]
    return {
        "ready": len(ready), "triggers": len(triggers),
        "lead_minutes_median": _median(leads), "lead_minutes_p10": _p10(leads),
        "late_rate": _share(sum(e["detail"]["late"] for e in triggers), len(triggers)),
        "gap_rate": _share(len(by["gap_open"]), len(triggers)),
        "close_back_rate": _share(sum(e["detail"]["close_back_inside"] for e in states), len(states)),
        "unresolved_entry_bars": sum(e["detail"]["unresolved"] for e in states),
        "expired": len(by["expired"]), "invalidated": len(by["invalidated"]),
        "notices_attempted": len(attempted), "notices_delivered": len(attempted & delivered),
        "undelivered": len(attempted - delivered),
        "delivery_parity": _share(len(attempted & delivered), len(attempted)),
        "missing_ready": len({e["identity"] for e in triggers} - ready),
    }


_RATE_KEYS = ("late_rate", "gap_rate", "close_back_rate", "delivery_parity")


def _fmt(key, value):
    if value is None:
        return "—"
    return f"{value:.1%}" if key in _RATE_KEYS else str(value)


def render_markdown(summary: dict) -> str:
    rows = [("Candidates ready", "ready"), ("Triggers observed", "triggers"),
            ("Lead time, median (min)", "lead_minutes_median"),
            ("Lead time, p10 (min)", "lead_minutes_p10"),
            ("Late (fired before the poll)", "late_rate"),
            ("Filled through a gap", "gap_rate"),
            ("Trigger day closed back inside", "close_back_rate"),
            ("Unresolved entry-bar ordering", "unresolved_entry_bars"),
            ("Expired", "expired"), ("Invalidated", "invalidated"),
            ("PENDING notices attempted", "notices_attempted"),
            ("PENDING notices delivered", "notices_delivered"),
            ("Delivery parity", "delivery_parity"),
            ("Triggers with no ready event (missing)", "missing_ready")]
    lines = ["| Measure | Value |", "|---|---|"] + [
        f"| {label} | {_fmt(key, summary[key])} |" for label, key in rows]
    lines.append("")
    lines.append("Broker order status is unknown for every event: this is paper telemetry.")
    return "\n".join(lines)
```

Rates are formatted as percentages by key (`_RATE_KEYS`), never by
magnitude: a 0.5-minute lead must not print as "50%".

- [ ] **Step 4: Implement the report script**

`scripts/reports/range_shadow_report.py`:

```python
#!/usr/bin/env python3
"""v105 read-only report of PENDING range shadow telemetry.

Reads data/range_shadow_events.jsonl (or --events) and prints markdown.
Never posts to a trade channel and never writes anything.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swingbot.core.scanning import range_shadow  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", help="events JSONL (default: config.DATA_DIR)")
    args = parser.parse_args(argv)
    print(range_shadow.render_markdown(range_shadow.summarise(range_shadow.read_events(args.events))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Wire telemetry into the scan and the feed**

In `swingbot/core/scanning/scan_run.py`, add below `_maybe_run_range_pass`:

```python
def _record_range_shadow(result, cell, *, fresh_data, now) -> None:
    """v105 Task 7: prospective telemetry; a failure is logged, never raised."""
    from swingbot.core.scanning import range_pass, range_shadow
    try:
        book = range_shadow.ShadowBook()
        at, poll = now.isoformat(), int(config.SCAN_INTERVAL_MINUTES) * 60
        for plan, cell_id, quote in result.shadow:
            book.observe_ready(plan, cell_id, quote, at=at, poll_interval_s=poll)
        for plan in result.plans:
            book.observe_ready(plan, cell.cell_id, plan.first_seen_price, at=at, poll_interval_s=poll)
            book.record_notice(plan, "notice_attempted", at)
        book.sweep(fresh_data, now=now, quote_fn=range_pass.fresh_quote, poll_interval_s=poll)
        book.save()
    except Exception:
        log.error("range shadow telemetry failed this scan -- the record has a gap", exc_info=True)
```

In `_maybe_run_range_pass`, capture `now = datetime.now(timezone.utc)` once,
pass `now=now` to `run_range_pass`, and after `alerts.extend(result.alerts)` add:

```python
    _record_range_shadow(result, cell, fresh_data=fresh_data, now=now)
```

In `swingbot/commands/scanning/loops.py:_post_plan_events`, directly before the
`try: await asyncio.to_thread(plan_manager.ack_notified, deliveries)` block:

```python
    try:
        from swingbot.core.scanning import range_shadow
        range_shadow.record_deliveries(plan_events, deliveries)
    except Exception as exc:
        log.warning("trade_monitor: range shadow delivery record failed: %s", exc)
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_pending_range_shadow.py
python scripts/dev/testrun.py file tests/scanning/test_pending_range_alerts.py
python scripts/reports/range_shadow_report.py --events tests/backtesting/fixtures/does-not-exist.jsonl
```

Expected: both runs `0 failed`. The report prints the table with zero
counts and `—` values (an empty feed renders; it does not crash).

- [ ] **Step 7: Inspect one synthetic rendered report**

```bash
python - <<'PY'
from datetime import datetime, timezone
from swingbot.core.planning import range_source
from swingbot.core.scanning import range_shadow as rs
from tests.market.range_fixtures import fixed_levels, long_frame
import tempfile, os
range_source.range_target_levels = fixed_levels
plan = range_source.range_plan_at(long_frame(), ticker="AAA", horizon_key="2w", n=20).plan
d = tempfile.mkdtemp()
book = rs.ShadowBook(state_file=os.path.join(d, "s.json"), events_file=os.path.join(d, "e.jsonl"))
book.observe_ready(plan, "N20-d0.75-P0", plan.trigger_price - 0.3, at="2026-10-05T14:00:00+00:00", poll_interval_s=900)
book.observe_quote(f"{plan.entry_context['range']['identity']}|N20-d0.75-P0", plan.trigger_price + 0.1,
                   at="2026-10-05T15:30:00+00:00", session="2026-10-05", session_open=None, poll_interval_s=900)
print(rs.render_markdown(rs.summarise(rs.read_events(book.events_file))))
PY
```

Expected: `Lead time, median (min) | 90.0`, `Late … | 0.0%`, and the
broker-unknown line.

- [ ] **Step 8: Check complexity and commit**

```bash
python -m radon cc -s -n C swingbot/core/scanning/range_shadow.py scripts/reports/range_shadow_report.py swingbot/core/scanning/scan_run.py swingbot/commands/scanning/loops.py
git status --short
git add swingbot/core/scanning/range_shadow.py scripts/reports/range_shadow_report.py swingbot/core/scanning/scan_run.py swingbot/commands/scanning/loops.py tests/backtesting/test_pending_range_shadow.py
git commit -m "feat(v105): prospective range shadow telemetry -- lead time, late triggers, gaps, close-back, delivery parity"
```

**Verification:** narrow runs and the synthetic report above.

