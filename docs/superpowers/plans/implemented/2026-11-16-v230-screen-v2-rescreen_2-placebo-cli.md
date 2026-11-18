# v230 Plan 1, Part 2 — the placebo CLI and the v1 measurement (stop gate 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V230-5" -A 200 <this file>`).

**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) (A1: "The pipeline's window constants, membership path and context loader take parameters", the output table, the v1 stop)
**Index:** [2026-11-16-v230-screen-v2-rescreen_0-index.md](2026-11-16-v230-screen-v2-rescreen_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there; every task below obeys them.
**Tasks:** V230-4..V230-5

What this part builds: the window parameters on `screen_idea`'s pipeline
(defaults byte-identical), the placebo CLI `scripts/backtest/screen_placebo.py`
that drives the existing v1 screen over Part 1's universes and triggers with
per-cell and per-ticker checkpoints (V230-4), and the first real run: the v1
placebo table and stop gate 1 (V230-5). V230-13 (Part 5) later adds the v2
runner and the planted check to the same CLI.

# Phase 2 — the placebo CLI and stop gate 1

### Task V230-4: Pipeline parameters, placebo universes on disk and the v1 cell runner

**Model:** sonnet — keyword pass-through with pinned defaults plus thin CLI library code over Part 1's finished contracts; no new statistics.

**Files:**
- Modify: `scripts/backtest/screen_idea.py` (`ticker_context` ~:344, `screen_ticker` ~:424, `_spy_calendar` ~:449, `_context_frame` ~:475, `load_context` ~:491, `_screen_or_resume` ~:579, `screen_universe` ~:610)
- Create: `scripts/backtest/screen_placebo.py`
- Create: `tests/backtest_scripts/test_screen_placebo.py`
- Modify: `tests/backtesting/instrument/test_date_literal_guard.py` (`ALLOW`)

**Interfaces:**
- Consumes: Part 1 `placebo.py` (`TRIGGERS`, `placebo_idea`, `trading_calendar`, `atr_pct_quartiles`, `gbm_universe`, `shuffled_universe`, `Cell`, `cell_from_rows`, `MANIFEST_FILE`, `MEMBERSHIP_FILE`, `INDEX_TICKER`, `GBM_TICKERS`); `screen_idea` constants, `load_universe`, `TickerScreen.events`.
- Produces: the `screen_idea` keywords of the ledger row (a non-default `event_start` adds an `event_start` key to the checkpoint manifest; the default manifest is unchanged); `screen_placebo.NULLS = ("v1", "v2")`, `KINDS = ("gbm", "shuffled")`, `DEFAULT_WORK`, `DEFAULT_JSON`, `universe_label(kind, size) -> str` (`gbm-<n>`, `shuffled-c<copies>`), `load_cells(path)`, `save_cell(path, cell)`, `run_cell_v1(universe_dir, trigger: PlaceboTrigger, *, checkpoint_dir) -> list[dict]`, `RUNNERS = {"v1": run_cell_v1}`, `build_universes(args) -> dict[str, Path]` (universes at `<work-dir>/universes/<label>/`, reused when `universe.json` exists). V230-4b adds the cell loop, the doc, the parser and `main`; until then the module has no `__main__`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest_scripts/test_screen_placebo.py`:

```python
"""v230 A1: screen_idea's window parameters (defaults byte-identical) and the
placebo CLI -- universes built once, cells upserted, a restart skips, the doc."""
import functools
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402
import screen_placebo  # noqa: E402

from swingbot.core.backtesting.screen import placebo  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402
from swingbot.core.backtesting.screen.placebo import Cell  # noqa: E402
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

ALWAYS = [("2000-01-01", "9999-12-31")]
IDEA = IDEAS["turn_of_month"]
EARLY = "2010-06-01"


def _quiet(*_args, **_kwargs):
    return None


@pytest.fixture(autouse=True)
def fast_cells(monkeypatch):
    monkeypatch.setattr(placebo, "cell_from_rows",
                        functools.partial(placebo.cell_from_rows, n_resamples=200))


def _write_csv(path, df):
    df.rename_axis("Date").to_csv(path)


def _source(tmp_path):
    """SPY plus three tickers on one calendar from 2010-01-04 as the source cache."""
    src = tmp_path / "src"
    if not src.exists():
        src.mkdir()
        for seed, ticker in enumerate(("SPY", "AAA", "BBB", "CCC"), start=1):
            _write_csv(src / f"{ticker}.csv", random_walk(520, seed=seed))
    return src


def _cell(universe, delta, *, trigger="p_high20", null="v1", low=None, high=None):
    low = delta - 0.01 if low is None else low
    high = delta + 0.01 if high is None else high
    return Cell(universe, trigger, null, 400, 0.1 + delta, 0.1, delta, low, high)


@pytest.mark.parametrize("fn, name, default", [
    ("ticker_context", "event_start", "EVENT_START"),
    ("screen_ticker", "event_start", "EVENT_START"),
    ("screen_universe", "event_start", "EVENT_START"),
    ("_spy_calendar", "start", "CONTEXT_START"),
    ("load_context", "context_start", "CONTEXT_START")])
def test_window_parameters_default_to_the_module_constants(fn, name, default):
    param = inspect.signature(getattr(screen_idea, fn)).parameters[name]
    assert param.default == getattr(screen_idea, default)


def test_ticker_context_default_is_byte_identical_and_event_start_moves_warm():
    df = random_walk(700, seed=3)
    default = screen_idea.ticker_context(IDEA, df, ALWAYS)
    explicit = screen_idea.ticker_context(IDEA, df, ALWAYS, event_start=screen_idea.EVENT_START)
    for key in ("raw", "member", "warm", "trend"):
        assert np.array_equal(default[key], explicit[key])
    early = screen_idea.ticker_context(IDEA, df, ALWAYS, event_start=EARLY)
    assert early["warm"].sum() > default["warm"].sum()
    assert not early["warm"][df.index < pd.Timestamp(EARLY)].any()


def test_screen_universe_threads_event_start_and_marks_only_a_changed_manifest(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(("AAA", "BBB"), start=1):
        _write_csv(cache / f"{ticker}.csv", random_walk(700, seed=seed))
    (tmp_path / "m.csv").write_text("ticker,start_date,end_date\nAAA,2000-01-01,\n"
                                    "BBB,2000-01-01,\n", encoding="utf-8")
    universe = screen_idea.load_universe(cache, tmp_path / "m.csv")
    screen_idea.screen_universe(IDEA, universe, cache, out=_quiet, checkpoint_dir=tmp_path / "a")
    assert "event_start" not in json.loads((tmp_path / "a" / "manifest.json").read_text())
    screens, _ = screen_idea.screen_universe(IDEA, universe, cache, out=_quiet,
                                             checkpoint_dir=tmp_path / "b", event_start=EARLY)
    assert json.loads((tmp_path / "b" / "manifest.json").read_text())["event_start"] == EARLY
    first = min(row["entry_date"] for s in screens for row in s.events)
    assert EARLY <= first < screen_idea.EVENT_START


def test_spy_calendar_and_load_context_take_a_start(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    _write_csv(cache / "SPY.csv", random_walk(400, seed=1, start="2009-01-02"))
    assert screen_idea._spy_calendar(cache, "2010-06-30").index[0] >= \
        pd.Timestamp(screen_idea.CONTEXT_START)
    data = screen_idea.load_context(cache, (), end="2010-06-30", context_start="2009-03-02")
    assert data.frames == {} and data.calendar.index[0] == pd.Timestamp("2009-03-02")


def test_universe_labels():
    assert screen_placebo.universe_label("gbm", 200) == "gbm-200"
    assert screen_placebo.universe_label("shuffled", 2) == "shuffled-c2"


def test_save_cell_upserts_atomically(tmp_path):
    path = tmp_path / "json" / "placebo-v1.json"
    assert screen_placebo.load_cells(path) == []
    for cell in (_cell("gbm-200", 0.30), _cell("gbm-200", 0.01, trigger="p_gap_up"),
                 _cell("gbm-200", 0.05)):
        screen_placebo.save_cell(path, cell)
    cells = screen_placebo.load_cells(path)
    assert sorted((c.trigger, c.delta) for c in cells) == [("p_gap_up", 0.01), ("p_high20", 0.05)]
    assert [p.name for p in path.parent.iterdir()] == ["placebo-v1.json"]


def test_build_universes_once_and_run_cell_v1(tmp_path, monkeypatch):
    args = SimpleNamespace(source_cache=_source(tmp_path), work_dir=tmp_path / "work",
                           universes=["gbm", "shuffled"], gbm_tickers=3, shuffled_copies=1)
    built = screen_placebo.build_universes(args)
    assert sorted(built) == ["gbm-3", "shuffled-c1"]
    manifest = json.loads((built["gbm-3"] / placebo.MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["kind"] == "gbm" and len(manifest["tickers"]) == 3
    monkeypatch.setattr(placebo, "gbm_universe", lambda *a, **k: pytest.fail("rebuilt"))
    monkeypatch.setattr(placebo, "shuffled_universe", lambda *a, **k: pytest.fail("rebuilt"))
    assert screen_placebo.build_universes(args) == built
    rows = screen_placebo.run_cell_v1(built["gbm-3"], placebo.TRIGGERS["p_high20"],
                                      checkpoint_dir=tmp_path / "ckpt")
    assert rows and {"ticker", "entry_date", "r_event", "r_null"} <= set(rows[0])
    assert min(r["entry_date"] for r in rows) >= screen_idea.EVENT_START
    assert {r["ticker"] for r in rows} <= {"G000", "G001", "G002"}
    assert (tmp_path / "ckpt" / "manifest.json").is_file()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_placebo.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'screen_placebo'` at collection.

- [ ] **Step 3: Thread the window parameters through `screen_idea`**

Every new keyword defaults to today's constant; bodies otherwise unchanged. In `scripts/backtest/screen_idea.py`:

```python
def ticker_context(idea: Idea, df: pd.DataFrame, spans, context: Mapping | None = None,
                   *, event_start: str = EVENT_START) -> dict:
    # docstring: append "v230: event_start moves the first event bar (placebo harness)."
    ...
    warm = race.warm_mask(atr, sma200) & (df.index >= pd.Timestamp(event_start))


def screen_ticker(idea: Idea, ticker: str, df: pd.DataFrame, spans, *,
                  slippage_bps=None, commission=None,
                  context: Mapping | None = None, event_start: str = EVENT_START) -> TickerScreen:
    costs = {"slippage_bps": slippage_bps, "commission": commission}
    ctx = ticker_context(idea, df, spans, context, event_start=event_start)
    ...


def _spy_calendar(cache_dir, end: str, start: str = CONTEXT_START) -> pd.DataFrame:
    # body: load_frame(path, start, end); the "no bar in" message prints {start}..{end}


def _context_frame(cache_dir, ticker: str, sessions: pd.DatetimeIndex, end: str,
                   kind: str = "z", start: str = CONTEXT_START):
    # body: both CONTEXT_START uses (load_frame and the "no bar in" message) become ``start``


def load_context(cache_dir, tickers: tuple[str, ...], *, end: str = WINDOW_END,
                 kind: str = "z", context_start: str = CONTEXT_START) -> screen_context.ContextData:
    """Every context frame an idea names, checked, from context_start to end."""
    calendar = _spy_calendar(cache_dir, end, start=context_start)
    frames, records = {}, {}
    for ticker in tickers:
        frames[ticker], records[ticker] = _context_frame(cache_dir, ticker, calendar.index, end,
                                                         kind, start=context_start)
    return screen_context.ContextData(frames=frames, calendar=calendar, records=records)
```

`_screen_or_resume(idea, ticker, universe, cache_dir, start, end, context, checkpoint, event_start=EVENT_START)` passes `event_start=event_start` to `screen_ticker` (every monkeypatched `screen_ticker` in the existing tests takes `**kwargs`). `screen_universe` gains `event_start: str = EVENT_START` after `checkpoint_dir`, and its manifest line becomes:

```python
    manifest = _checkpoint_manifest(idea, start, end, names, context, universe.intervals)
    if event_start != EVENT_START:      # v230: only a placebo run changes the manifest
        manifest["event_start"] = event_start
    checkpoint = _open_checkpoint(checkpoint_dir, manifest, out)
```

and the loop's lambda calls `_screen_or_resume(..., context, checkpoint, event_start)`.

- [ ] **Step 4: Write the CLI module's library half and its guard entry**

Create `scripts/backtest/screen_placebo.py`:

```python
#!/usr/bin/env python3
"""v230 A1 placebo harness: the screen's own pipeline over universes with no edge.

    python scripts/backtest/screen_placebo.py --null v1 --date <YYYY-MM-DD>

Builds (or reuses) the gbm and shuffled universes under --work-dir on the real
session calendar of the screen window, runs each placebo trigger through the
screen pipeline under --null and upserts one cell per universe x trigger into
<json-dir>/placebo-<null>.json as it finishes (a restart skips finished cells;
a cell checkpoints per ticker). Renders <results-dir>/<date>-v230-null-placebo.md
from every placebo-v*.json. Never touches the pre-registration ledger.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting.screen import placebo  # noqa: E402
from swingbot.core.backtesting.screen.placebo import Cell  # noqa: E402

NULLS = ("v1", "v2")
KINDS = ("gbm", "shuffled")
DEFAULT_WORK = Path(config.DATA_DIR) / "v230-placebo"
DEFAULT_JSON = screen_idea.RESULTS_DIR / "v230"


def universe_label(kind: str, size: int) -> str:
    """gbm-<tickers> / shuffled-c<copies>: an enlarged universe is a new label."""
    return f"gbm-{size}" if kind == "gbm" else f"{kind}-c{size}"


def load_cells(path) -> list[Cell]:
    path = Path(path)
    if not path.is_file():
        return []
    return [Cell.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]


def save_cell(path, cell: Cell) -> None:
    """Upsert by (universe, trigger, null); tmp file + os.replace, never a torn file."""
    path = Path(path)
    key = (cell.universe, cell.trigger, cell.null)
    cells = [c for c in load_cells(path) if (c.universe, c.trigger, c.null) != key] + [cell]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps([c.to_dict() for c in cells], indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def run_cell_v1(universe_dir, trigger, *, checkpoint_dir) -> list[dict]:
    """One placebo trigger through the v1 screen pipeline; its event rows."""
    udir = Path(universe_dir)
    manifest = json.loads((udir / placebo.MANIFEST_FILE).read_text(encoding="utf-8"))
    index = screen_idea.load_context(udir, (), end=screen_idea.WINDOW_END,
                                     context_start=manifest["calendar_start"]).calendar
    universe = screen_idea.load_universe(udir, udir / placebo.MEMBERSHIP_FILE)
    screens, _ = screen_idea.screen_universe(
        placebo.placebo_idea(trigger, index), universe, udir, start=screen_idea.WINDOW_START,
        end=screen_idea.WINDOW_END, checkpoint_dir=Path(checkpoint_dir),
        event_start=screen_idea.EVENT_START)
    return [row for screen in screens for row in screen.events]


RUNNERS: dict[str, Callable] = {"v1": run_cell_v1}


def _build_gbm(out, source, calendar, args):
    quartiles = placebo.atr_pct_quartiles(source, calendar)
    return placebo.gbm_universe(out, calendar, quartiles, n_tickers=args.gbm_tickers)


def _build_shuffled(out, source, calendar, args):
    return placebo.shuffled_universe(out, source, calendar, copies=args.shuffled_copies)


BUILDERS = {"gbm": (_build_gbm, "gbm_tickers"), "shuffled": (_build_shuffled, "shuffled_copies")}


def build_universes(args) -> dict[str, Path]:
    """Every requested universe, built once; one with a universe.json is reused."""
    source = Path(args.source_cache)
    calendar = placebo.trading_calendar(source / f"{placebo.INDEX_TICKER}.csv",
                                        screen_idea.WINDOW_START, screen_idea.WINDOW_END)
    built = {}
    for kind in args.universes:
        build, size_attr = BUILDERS[kind]
        label = universe_label(kind, getattr(args, size_attr))
        out = Path(args.work_dir) / "universes" / label
        reuse = (out / placebo.MANIFEST_FILE).is_file()
        print(f"[placebo] universe {label}: {'reused' if reuse else 'building'}", flush=True)
        if not reuse:
            build(out, source, calendar, args)
        built[label] = out
    return built
```

`run_cell_v1` loads the synthetic index through `load_context` with `context_start` at the universe's first session, so the market-scope triggers read the universe's own equal-weight `SPY.csv`.

In `tests/backtesting/instrument/test_date_literal_guard.py`, add to `ALLOW` directly after the `screen_idea.py` entry:

```python
    "scripts/backtest/screen_placebo.py": "v230 null placebo; runs on screen_idea's pre-registered window constants, takes no --instrument",
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_placebo.py`
Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_checkpoint.py`
Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
Run: `python scripts/dev/testrun.py file tests/backtesting/instrument/test_date_literal_guard.py`
Expected: PASS, 0 failed, 0 xfailed. The checkpoint and context-runner files prove the defaults byte-identical. Complexity: `python scripts/dev/complexity_gate.py` passes (every new function < 15).

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/screen_idea.py tests/backtesting/instrument/test_date_literal_guard.py
git commit -m "feat(v230): window parameters on the screen pipeline, defaults byte-identical"
git add scripts/backtest/screen_placebo.py tests/backtest_scripts/test_screen_placebo.py
git commit -m "feat(v230): placebo universes on disk, cell store and the v1 cell runner"
```

### Task V230-4b: Placebo CLI: the cell loop, the gate, the results doc and `main`

**Model:** sonnet — Markdown rendering and an argparse entry point over V230-4's library half and Part 1's acceptance arithmetic.

**Files:**
- Modify: `scripts/backtest/screen_placebo.py`
- Modify: `tests/backtest_scripts/test_screen_placebo.py`

**Interfaces:**
- Consumes: V230-4 `NULLS`, `KINDS`, `DEFAULT_WORK`, `DEFAULT_JSON`, `load_cells`, `save_cell`, `RUNNERS`, `build_universes`, test helpers `_source`, `_cell`; Part 1 `placebo.PLACEBO_CAP`, `TRIGGERS`, `GBM_TICKERS`, `MANIFEST_FILE`, `cell_from_rows`, `accept_cell`, `v1_premise_holds`, `acceptance`; `screen_idea.DEFAULT_CACHE`, `RESULTS_DIR`, `_utf8_stdout`.
- Produces (rest of the ledger row): `latest_cells(cells) -> list[Cell]` (largest universe per kind × trigger × null), `v1_gate(cells) -> str | None` (`BIAS` / `NO-BIAS`), `render_doc(cells, *, date, manifests, planted=None, acceptance=None) -> str` (`planted`: the planted `Cell`; `acceptance`: `placebo.acceptance(...)`'s dict — V230-13 passes both), `write_doc(args, *, planted=None, acceptance=None) -> Path`, `build_parser()`, `main(argv=None) -> int`; flags `--null {v1,v2}`, `--universes`, `--triggers`, `--work-dir`, `--source-cache`, `--gbm-tickers`, `--shuffled-copies`, `--date`, `--results-dir`, `--json-dir`. Per-ticker checkpoints at `<work-dir>/checkpoints/<null>/<label>/<trigger>/`.

`latest_cells` exists because an enlarged universe gets its own label: its cell sits beside the noisy one, and the gate (and V230-13's acceptance) must read only the largest, or a superseded NOISY cell keeps returning ENLARGE (index Decisions).

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_screen_placebo.py`:

```python
def _argv(tmp_path, *extra):
    return ["--source-cache", str(_source(tmp_path)), "--work-dir", str(tmp_path / "work"),
            "--json-dir", str(tmp_path / "json"), "--results-dir", str(tmp_path / "results"),
            "--date", "2026-11-20", "--gbm-tickers", "3", *extra]


def test_latest_cells_and_the_inclusive_v1_gate():
    cells = [_cell("gbm-200", 0.30), _cell("gbm-400", 0.01), _cell("shuffled-c1", -0.02),
             _cell("gbm-200", 0.50, null="v2")]
    latest = {(c.universe, c.null) for c in screen_placebo.latest_cells(cells)}
    assert latest == {("gbm-400", "v1"), ("shuffled-c1", "v1"), ("gbm-200", "v2")}
    assert screen_placebo.v1_gate(cells) == "NO-BIAS"          # 0.30 is superseded
    assert screen_placebo.v1_gate(cells + [_cell("shuffled-c1", 0.0201, trigger="x")]) == "BIAS"
    assert screen_placebo.v1_gate([_cell("gbm-200", 0.5, null="v2")]) is None


def test_main_writes_cells_and_doc_then_a_restart_skips(tmp_path, monkeypatch, capsys):
    argv = _argv(tmp_path, "--triggers", "p_high20", "p_month_turn")
    assert screen_placebo.main(argv) == 0
    cells = screen_placebo.load_cells(tmp_path / "json" / "placebo-v1.json")
    assert sorted((c.universe, c.trigger) for c in cells) == [
        ("gbm-3", "p_high20"), ("gbm-3", "p_month_turn"),
        ("shuffled-c1", "p_high20"), ("shuffled-c1", "p_month_turn")]
    assert (tmp_path / "work" / "checkpoints" / "v1" / "gbm-3" / "p_high20"
            / "manifest.json").is_file()
    doc = (tmp_path / "results" / "2026-11-20-v230-null-placebo.md").read_text(encoding="utf-8")
    assert "## Stop gate 1 (v1)" in doc and "| gbm-3 | p_high20 | v1 |" in doc
    assert "| shuffled-c1 | shuffled | 3 |" in doc
    assert "gate: " in capsys.readouterr().out
    monkeypatch.setitem(screen_placebo.RUNNERS, "v1",
                        lambda *a, **k: pytest.fail("re-ran a finished cell"))
    assert screen_placebo.main(argv) == 0


def test_main_refuses_a_null_without_a_runner(tmp_path, monkeypatch, capsys):
    monkeypatch.delitem(screen_placebo.RUNNERS, "v2", raising=False)
    assert screen_placebo.main(_argv(tmp_path, "--null", "v2")) == 2
    assert "refused" in capsys.readouterr().err


def test_render_doc_gate_hashes_planted_and_acceptance():
    manifests = {"shuffled-c1": {"kind": "shuffled", "seed": 42, "tickers": ["AAA"],
                                 "calendar_start": "2010-01-04", "calendar_end": "2019-12-31",
                                 "copies": 1, "source_sha256": {"AAA.csv": "ab" * 32}}}
    bias = screen_placebo.render_doc([_cell("shuffled-c1", 0.3)], date="2026-11-20",
                                     manifests=manifests)
    assert bias.startswith("# v230 null placebo — 2026-11-20\n")
    assert "Gate: **BIAS**" in bias and "shuffled-c1/p_high20 (+0.3000)" in bias
    assert "| shuffled-c1 | shuffled | 1 |" in bias and "`AAA.csv` `" + "ab" * 32 in bias
    calm = screen_placebo.render_doc([_cell("gbm-200", 0.02)], date="d", manifests={})
    assert "Gate: **NO-BIAS**" in calm and "premise of spec v230 is wrong" in calm
    assert "## Stop gate 2" not in calm and "## Planted edge" not in calm
    passing = _cell("gbm-200", 0.0, null="v2")
    planted = _cell("planted-gbm-200", 0.4, trigger="p_high20_planted", null="v2")
    verdict = placebo.acceptance([passing], planted, 0.4)
    doc = screen_placebo.render_doc([passing], date="d", manifests={}, planted=planted,
                                    acceptance=verdict)
    assert "## Planted edge" in doc and "p_high20_planted" in doc
    assert "Verdict: **ACCEPT**" in doc and "| gbm-200/p_high20 | PASS |" in doc
    assert "## Stop gate 1" not in doc
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_placebo.py`
Expected: FAIL — `AttributeError: module 'screen_placebo' has no attribute 'latest_cells'` (and `main`, `render_doc`); V230-4's tests still pass.

- [ ] **Step 3: Write the implementation**

In `scripts/backtest/screen_placebo.py`, extend the imports (`import argparse`, `import datetime`, `import re` beside the existing ones) and add below the existing constants:

```python
SPEC_LINK = "../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md"
_SIZE = re.compile(r"(\d+)$")
HEADER = ("| Universe | Trigger | Null | N | mean R event | mean R null | Δ | 95% interval "
          "| half-width | rule |", "|---|---|---|---:|---:|---:|---:|---|---:|---|")
GATE_TEXT = {
    "BIAS": "At least one cell has |Δ| > 0.02R: the v1 bias is measured; the plan continues "
            "to the v2 null (V230-6).",
    "NO-BIAS": "Every cell has |Δ| ≤ 0.02R: the premise of spec v230 is wrong. V230-6..V230-18 "
               "do not run; Parts B and C proceed on the v1 null."}
```

Append to the module:

```python
def _label_key(label: str) -> tuple[str, int]:
    match = _SIZE.search(label)
    return label.split("-", 1)[0], int(match.group(1)) if match else 0


def latest_cells(cells) -> list[Cell]:
    """The largest universe per (kind, trigger, null); an enlarged run supersedes."""
    best: dict[tuple, Cell] = {}
    for cell in cells:
        kind, size = _label_key(cell.universe)
        key = (kind, cell.trigger, cell.null)
        if key not in best or size >= _label_key(best[key].universe)[1]:
            best[key] = cell
    return list(best.values())


def v1_gate(cells) -> str | None:
    v1 = [c for c in latest_cells(cells) if c.null == "v1"]
    if not v1:
        return None
    return "BIAS" if placebo.v1_premise_holds(v1) else "NO-BIAS"


def _run_cells(universes: dict[str, Path], args) -> None:
    path = Path(args.json_dir) / f"placebo-{args.null}.json"
    done = {(c.universe, c.trigger) for c in load_cells(path)}
    todo = [(label, name) for label in universes for name in args.triggers]
    for i, (label, name) in enumerate(todo, start=1):
        tag = f"[placebo {args.null}] cell {i}/{len(todo)} {label}/{name}"
        if (label, name) in done:
            print(f"{tag}: finished earlier, skipped", flush=True)
            continue
        print(f"{tag} ({100.0 * (i - 1) / len(todo):.0f}% of cells done)", flush=True)
        ckpt = Path(args.work_dir) / "checkpoints" / args.null / label / name
        rows = RUNNERS[args.null](universes[label], placebo.TRIGGERS[name], checkpoint_dir=ckpt)
        save_cell(path, placebo.cell_from_rows(label, name, args.null, rows))


def _num(x, sign: bool = True) -> str:
    return "—" if x is None else (f"{x:+.4f}" if sign else f"{x:.4f}")


def _cell_row(c: Cell) -> str:
    interval = "—" if c.ci_low is None else f"[{c.ci_low:+.4f}, {c.ci_high:+.4f}]"
    return (f"| {c.universe} | {c.trigger} | {c.null} | {c.n} | {_num(c.mean_r_event)} | "
            f"{_num(c.mean_r_null)} | {_num(c.delta)} | {interval} | "
            f"{_num(c.half_width, sign=False)} | {placebo.accept_cell(c)} |")


def _detail(m: dict) -> str:
    if "quartiles" in m:
        return "ATR% quartiles " + ", ".join(f"{q:.4f}" for q in m["quartiles"])
    return f"copies {m.get('copies', 1)}, {len(m.get('source_sha256', {}))} source files"


def _universe_lines(manifests: dict) -> list[str]:
    lines = ["## Universes", "", "| Label | Kind | Tickers | Calendar | Seed | Detail |",
             "|---|---|---:|---|---:|---|"]
    hashes: list[str] = []
    for label, m in sorted(manifests.items()):
        lines.append(f"| {label} | {m['kind']} | {len(m['tickers'])} | "
                     f"{m['calendar_start']}..{m['calendar_end']} | {m['seed']} | {_detail(m)} |")
        if m.get("source_sha256"):
            hashes += ["", f"<details><summary>Source file sha256 ({label})</summary>", "",
                       *(f"- `{f}` `{d}`" for f, d in sorted(m["source_sha256"].items())),
                       "", "</details>"]
    return lines + hashes + [""]


def _cell_lines(cells) -> list[str]:
    lines: list[str] = []
    for null in sorted({c.null for c in cells}):
        rows = sorted((c for c in cells if c.null == null), key=lambda c: (c.universe, c.trigger))
        lines += [f"## Cells, null {null}", "", *HEADER, *map(_cell_row, rows), ""]
    return lines


def _gate_lines(cells) -> list[str]:
    gate = v1_gate(cells)
    if gate is None:
        return []
    beyond = sorted(f"{c.universe}/{c.trigger} ({c.delta:+.4f})" for c in latest_cells(cells)
                    if c.null == "v1" and placebo.v1_premise_holds([c]))
    tail = ["", "Cells past 0.02R: " + ", ".join(beyond) + "."] if beyond else []
    return ["## Stop gate 1 (v1)", "", f"Gate: **{gate}**", "", GATE_TEXT[gate], *tail, ""]


def _verdict_lines(planted: Cell | None, acceptance: dict | None) -> list[str]:
    lines = [] if planted is None else ["## Planted edge", "", *HEADER, _cell_row(planted), ""]
    if acceptance is None:
        return lines
    p = acceptance["planted"]
    return lines + ["## Stop gate 2 (v2)", "", f"Verdict: **{acceptance['verdict']}**", "",
                    "| Cell | Rule |", "|---|---|",
                    *(f"| {k} | {v} |" for k, v in sorted(acceptance["cells"].items())), "",
                    f"Planted value {_num(p['value'])} R; recovered: {p['recovered']}; "
                    f"noisy: {p['noisy']}.", ""]


def render_doc(cells, *, date: str, manifests: dict, planted: Cell | None = None,
               acceptance: dict | None = None) -> str:
    head = [f"# v230 null placebo — {date}", "", f"**Spec:** [v230]({SPEC_LINK}) A1",
            "**Script:** `scripts/backtest/screen_placebo.py`", "",
            f"Every trigger races long, fixed (stop 1.5 x ATR14, target 3 x ATR14), next-open "
            f"entry, cap {placebo.PLACEBO_CAP} bars, base costs, against the screen's matched "
            f"null (K = 20). Δ = mean R event − mean R null, week-clustered 95% interval. "
            f"Rule: PASS iff |Δ| ≤ 0.02R and half-width ≤ 0.02R (inclusive); only the "
            f"largest universe per kind and trigger is judged.", ""]
    body = (_universe_lines(manifests) + _cell_lines(cells) + _gate_lines(cells)
            + _verdict_lines(planted, acceptance))
    return "\n".join(head + body).rstrip("\n") + "\n"


def _all_cells(json_dir) -> list[Cell]:
    return [c for p in sorted(Path(json_dir).glob("placebo-v*.json")) for c in load_cells(p)]


def write_doc(args, *, planted: Cell | None = None, acceptance: dict | None = None) -> Path:
    manifests = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in
                 sorted((Path(args.work_dir) / "universes").glob(f"*/{placebo.MANIFEST_FILE}"))}
    path = Path(args.results_dir) / f"{args.date}-v230-null-placebo.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_doc(_all_cells(args.json_dir), date=args.date, manifests=manifests,
                               planted=planted, acceptance=acceptance),
                    encoding="utf-8", newline="\n")
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--null", choices=NULLS, default="v1")
    p.add_argument("--universes", nargs="+", choices=KINDS, default=list(KINDS))
    p.add_argument("--triggers", nargs="+", choices=list(placebo.TRIGGERS),
                   default=list(placebo.TRIGGERS))
    p.add_argument("--work-dir", type=Path, default=DEFAULT_WORK)
    p.add_argument("--source-cache", type=Path, default=screen_idea.DEFAULT_CACHE)
    p.add_argument("--gbm-tickers", type=int, default=placebo.GBM_TICKERS)
    p.add_argument("--shuffled-copies", type=int, default=1)
    p.add_argument("--date", default=datetime.date.today().isoformat())
    p.add_argument("--results-dir", type=Path, default=screen_idea.RESULTS_DIR)
    p.add_argument("--json-dir", type=Path, default=DEFAULT_JSON)
    return p


def main(argv=None) -> int:
    screen_idea._utf8_stdout()
    args = build_parser().parse_args(argv)
    if args.null not in RUNNERS:
        print(f"refused: no {args.null} runner yet (V230-13 adds it)", file=sys.stderr)
        return 2
    _run_cells(build_universes(args), args)
    print(f"[placebo] wrote {write_doc(args)}", flush=True)
    gate = v1_gate(_all_cells(args.json_dir))
    if gate is not None:
        print(f"gate: {gate}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

The `shuffled-c1` row in the end-to-end test shows 3 tickers: the source cache's AAA, BBB, CCC (SPY is the index, never a ticker).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_placebo.py`
Run: `python scripts/dev/testrun.py file tests/backtesting/instrument/test_date_literal_guard.py`
Expected: PASS, 0 failed, 0 xfailed. Complexity: `python scripts/dev/complexity_gate.py` passes (`_run_cells`, the largest, is far under 15).

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/screen_placebo.py tests/backtest_scripts/test_screen_placebo.py
git commit -m "feat(v230): placebo CLI -- checkpointed cell loop, stop gate 1, results doc"
```

### Task V230-5: Run: the v1 placebo measurement (stop gate 1)

**Model:** sonnet — a scripted, checkpointed run and a transcription of its gate; no code changes and no judgement beyond the fixed rule.

**Files:**
- Create: `docs/superpowers/results/<date>-v230-null-placebo.md` (rendered by the CLI, never hand-edited: V230-13 re-renders it)
- Create: `docs/superpowers/results/v230/placebo-v1.json`
- Modify: `docs/superpowers/plans/2026-11-16-v230-screen-v2-rescreen_0-index.md` (`## Handoff`, created at the end of the file if absent)

**Interfaces:**
- Consumes: V230-4/4b `scripts/backtest/screen_placebo.py` (`--null v1`, the cells JSON, `gate: BIAS|NO-BIAS` as its last stdout line); Part 1's universes and triggers; the real cache `data/backtest_cache_ext` (`SPY.csv` for the calendar and the ATR% quartiles; every ticker with a bar on every 2010–2019 session for `shuffled`).
- Produces: the recorded v1 table (12 cells: `gbm-200` and `shuffled-c1` × six triggers) and the gate outcome `BIAS` (V230-6 runs next) or `NO-BIAS` (V230-6..V230-18 do not run). The `<date>` used here is recorded in the Handoff: V230-13 re-renders the same doc with the same `--date`.

No real idea is read here: the placebo triggers are unregistered, the run never touches `preregistration-ledger.jsonl`, and `screen_idea.py`'s CLI is not invoked (the guardrail hook stays out of play).

- [ ] **Step 1: Pre-flight (seconds, no screening)**

Run in the worktree:

```bash
python -c "from swingbot.core.backtesting.screen import placebo; print(sorted(placebo.TRIGGERS))"
python scripts/backtest/screen_placebo.py --help
ls data/backtest_cache_ext/SPY.csv
```

Expected: the six trigger names (`p_gap_up`, `p_high20`, `p_market_down`, `p_month_turn`, `p_rsi2_dip`, `p_sweep20`), the CLI usage with `--null {v1,v2}`, and the SPY file present. A missing cache stops the task: `python scripts/data/fetch_backtest_data.py` is a network step the partner runs, not this task.

- [ ] **Step 2: Dispatch the run to `backtest-runner` (long, checkpointed)**

Dispatch the `backtest-runner` agent (one at a time, in the plan's worktree, named explicitly) with this command and the instruction to run it in the background and re-run the identical command after any crash (finished cells are skipped, a cell in progress resumes from its per-ticker checkpoint, built universes are reused):

```bash
mkdir -p logs
python scripts/backtest/screen_placebo.py --null v1 --date <YYYY-MM-DD> > logs/v230-placebo-v1.log 2>&1
```

`<YYYY-MM-DD>` is the run's start date (`date -u +%F`), passed explicitly so a restart after midnight writes the same doc. Progress lines: `[placebo] universe <label>: building|reused`, `[placebo v1] cell i/12 <label>/<trigger> (NN% of cells done)`, and `screen_universe`'s per-25-ticker percent lines. Twelve cells over 200 `gbm` tickers and the full-calendar `shuffled` tickers; expect tens of minutes. The runner reports back only: exit code, the last 5 log lines, and `grep -c '"trigger"' docs/superpowers/results/v230/placebo-v1.json`.

Expected: exit 0; 12 cells; the last line `gate: BIAS` or `gate: NO-BIAS`.

- [ ] **Step 3: Check the record before reading it**

```bash
python - <<'EOF'
import json
cells = json.load(open("docs/superpowers/results/v230/placebo-v1.json", encoding="utf-8"))
assert len(cells) == 12, len(cells)
assert {c["universe"] for c in cells} == {"gbm-200", "shuffled-c1"}
assert all(c["null"] == "v1" for c in cells)
for c in sorted(cells, key=lambda c: (c["universe"], c["trigger"])):
    print(c["universe"], c["trigger"], c["n"], c["delta"], c["ci_low"], c["ci_high"])
EOF
grep -n "^Gate:" docs/superpowers/results/*-v230-null-placebo.md
```

Expected: 12 lines, every `n` > 0. A cell with `n` = 0 is recorded as found (its Δ is `—` and it cannot move the gate); it is named in the Handoff, never re-run with other parameters.

- [ ] **Step 4: Record the gate in the index `## Handoff`**

Append to `docs/superpowers/plans/2026-11-16-v230-screen-v2-rescreen_0-index.md` (create the `## Handoff` heading at the end of the file if it is absent; never edit other sections):

```markdown
## Handoff

- **V230-5 (<YYYY-MM-DD>): stop gate 1 = <BIAS | NO-BIAS>.** v1 placebo, 12 cells
  (`gbm-200`, `shuffled-c1` × six triggers), results in
  `docs/superpowers/results/<YYYY-MM-DD>-v230-null-placebo.md` and
  `docs/superpowers/results/v230/placebo-v1.json`. Largest |Δ|: <universe>/<trigger>
  <Δ> R [<ci_low>, <ci_high>]; cells past 0.02R: <list, or none>. V230-13 re-renders
  the doc with `--date <YYYY-MM-DD>`.
- <BIAS:> Next task V230-6 (Part 3).
- <NO-BIAS:> The spec's premise is wrong: V230-6..V230-18 do not run; Parts B and C
  (Plan 2) proceed on the v1 null; the controller decides the close-out.
```

Fill every `<...>` from Step 3's output and the doc's `Gate:` line; keep only the one outcome bullet that applies.

- [ ] **Step 5: Commit (worktree branch)**

```bash
git add docs/superpowers/results/*-v230-null-placebo.md docs/superpowers/results/v230/placebo-v1.json docs/superpowers/plans/2026-11-16-v230-screen-v2-rescreen_0-index.md
git commit -m "results(v230): v1 null placebo measurement -- stop gate 1 <BIAS|NO-BIAS>"
```

`data/v230-placebo/` (universes and checkpoints) stays uncommitted (`data/` is gitignored); V230-13 reuses the universes from it.

