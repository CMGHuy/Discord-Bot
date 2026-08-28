# v61 part 2 — `core/scanning/engine.py` + `embeds.py`

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `engine.py` (2347 lines) into six modules plus a facade, and
`embeds.py` (1109) into five plus a facade, moving whole functions without
editing any body.

**Architecture:** Both files stay in place as facades. `engine.py` already
re-exports ten symbols from `embeds.py` (lines 104–110) — that accidental
facade becomes a deliberate, `__all__`-bounded one. Moves go leaf-first.

**Tech Stack:** Python 3.11+, pandas, pytest. No new dependencies.

**Read first:** `_0-index.md` — Global Constraints C1–C7 apply to every task
and are not repeated. **Also read `docs/claude/known-traps.md` and
`docs/claude/architecture.md` before Task 1.**

**Prerequisite:** part `_1` merged. `scripts/dev/check_move_purity.py` comes
from `_1` Task 1 and is required here.

**Worktree:** `2026-08-25-v61-large-file-decomposition_2-core-scanning`

---

## Global Constraints

All of `_0-index.md`, plus:

**C9 — The crawl/analyze phase separation is law.** `engine.py`'s module
docstring (lines 6–18) states every scan runs CRAWL then ANALYZE, and that
"nothing in [ANALYZE] ever fetches anything itself." Splitting fetching into
`fetch.py` and analysis into `analyze.py` makes that boundary structural. **No
import may run backwards**: `fetch.py` must never import `analyze.py`. Task 8
adds the test that enforces it.

**C10 — NO-LOOKAHEAD is untouched.** Per `architecture.md` this is a law of
the codebase. No move may reorder anything inside `_scan_one`, and nothing in
this plan touches `entry_filters.py`. If a move appears to require reordering,
stop — it does not.

**Confirmed patch targets** (verified 2026-08-25; re-verify in Task 1). Under
C2 every caller reaches these through their module:

| Symbol | New home | Note |
|---|---|---|
| `ProcessPoolExecutor` | `fetch.py` | **Highest risk in the whole spec.** Tests swap it for `_InlineProcessPool`; if the patch misses, tests spawn real processes. |
| `get_daily_data`, `get_daily_data_batch` | `fetch.py` | imported from `marketdata.data` |
| `_load_cached_daily`, `_fetch_frames` | `fetch.py` | |
| `is_stop_requested`, `_STOP_FILE`, `_RUNNING_FILE` | `runstate.py` | |
| `TELEMETRY_PATH` | `telemetry.py` | |

**Shared singletons (C4):** `engine.py` lines 114–115 hold `state =
StateStore()` and `trade_log = TradeLog()`. `trade_log` is reached externally
as `scan_engine.trade_log`, and
`tests/planning/test_manager_singleton_staleness_repro.py` already guards its
relationship with `commands.scanning.trade_log`. **Both stay in the facade
(`engine.py`) and every submodule imports them from there** — the one
permitted exception to C3's "no submodule imports the facade", because moving
them anywhere else changes an identity the suite pins. Record this exception
in the facade's docstring.

---

## Target structure

**`swingbot/core/scanning/` after this part:**

| Module | Holds (current line in `engine.py`) | ~lines |
|---|---|---|
| `runstate.py` | `_STOP_FILE`, `_RUNNING_FILE`, `is_stop_requested` (135), `request_stop` (139), `_clear_stop` (146), `is_scan_running` (153), `_mark_running` (160) | ~60 |
| `telemetry.py` | `TELEMETRY_PATH`, `log_scan_telemetry` (440), `recent_telemetry` (451), `scan_slowdown` (460) | ~60 |
| `dedup.py` | `_plans_similar` (365), `dedup_scan_items` (375), `_item_ticker` (405), `dedup_sector_items` (413) | ~80 |
| `fetch.py` | `LRUFrames` (471), `_chunked` (634), `_run_bounded` (668), `_fetch_one_ticker` (731), `_fetch_cold_frames` (750), `_load_cached_daily` (809), `_crawl_latest_data` (832), `_fetch_live_prices` (915), `_etf_symbol_of_sector` (949), `_sector_etfs_for_tickers` (968), `_fetch_frames` (991), `_daily_frame_for` (1014), `map_tickers` (1088) | ~560 |
| `analyze.py` | `ScanItem` (173), `build_decision_context` (212), `_build_quality_inputs` (507), `attach_plan_v2` (557), `_check_near_close` (591), `_apply_sector_rs` (1029), `_scan_one` (1113) | ~700 |
| `scan_run.py` | `ScanProgress` (331), `get_regime` (355), `_sync_run_scan` (1511), `run_scan` (2275), `get_all_unrealized_pnl` (2317) | ~880 |
| `engine.py` | facade + `state` + `trade_log` | ~170 |

`scan_run.py` at ~880 and `analyze.py` at ~700 remain large. That is expected:
`_sync_run_scan` alone is ~800 lines and `_scan_one` ~400. Breaking those up is
Phase B and explicitly **not** attempted here.

**`embeds.py` splits into:** `snapshots.py` (`_load_scan_snapshots` 49,
`_save_scan_snapshots` 59, `_format_duration_hms` 67, `_snapshot_and_diff` 86)
· `requirements.py` (`RequirementCheck` 134, `confidence_color` 168,
`_sources_str` 173, `_build_requirement_checks` 177, `_confidence_block` 240) ·
`plan_table.py` (`plan_numbers_for_display` 246, `_ansi_bad` 256,
`_build_trade_plan_table` 261, `badge_field_for` 388, `quality_lines` 405,
`entry_line` 416, `leg_rows` 424, `_v2_plan` 452) · `alert_embeds.py`
(`build_embed` 459, `build_simple_alert` 704) · `lifecycle_embeds.py`
(`regenerate_chart_for_trade` 777, `build_closed_trade_embed` 841,
`notify_closed_trades` 967, `build_near_close_embed` 998, `notify_near_close`
1023, `build_plan_event_embed` 1056, `notify_plan_events` 1088)

---

### Task 1: Verify the surface, patch targets and baseline

No move happens here. This task replaces every assumption with a measurement.

**Files:** none modified. Output goes in the commit message and this plan's
tables.

- [ ] **Step 1: Re-derive the external surface**

```bash
git grep -ohE "scan_engine\.[a-zA-Z_]+" -- 'swingbot/' 'bot.py' 'scripts/' 'tests/' | sort -u
git grep -ohE "from swingbot\.core\.scanning\.engine import [a-zA-Z_, ]+" -- '*.py' | sort -u
git grep -ohE "from swingbot\.core\.scanning\.embeds import [a-zA-Z_, ]+" -- '*.py' | sort -u
```

Expected to include at least: `run_scan`, `ScanProgress`, `ScanItem`,
`request_stop`, `is_scan_running`, `get_regime`, `get_all_unrealized_pnl`,
`map_tickers`, `LRUFrames`, `build_decision_context`, `dedup_sector_items`,
`recent_telemetry`, `scan_slowdown`, `log_scan_telemetry`, `trade_log`,
`CONFIDENCE_COLORS`, `regenerate_chart_for_trade`. **If the grep finds more,
the grep wins.**

- [ ] **Step 2: Re-derive the patch targets**

```bash
git grep -nE "setattr\((scan_engine|engine|embeds_mod)," -- 'tests/'
git grep -n "monkeypatch.setattr\(\"swingbot.core.scanning" -- 'tests/'
```

Every symbol found must appear in the C-block table above with a new home. Any
that does not is an unplanned move — add it before proceeding.

- [ ] **Step 3: Record the green baseline**

Dispatch the `test-runner` subagent: `python scripts/dev/testrun.py full`.
Record the exact counts. This is the number Task 15 compares against.

- [ ] **Step 4: Commit the findings**

```bash
git commit --allow-empty -m "chore(v61): record verified scanning surface, patch targets and test baseline"
```

---

### Tasks 2–7: engine.py moves

**Shared procedure** — identical to `_1`'s Tasks 3–8 block. For symbol set `S`
into module `M`:

1. Create `swingbot/core/scanning/<M>.py` with a docstring naming what it owns
   and that it split from `engine.py` on 2026-08-25, the import block, then
   `S` in original relative order, bodies untouched.
2. Delete `S` from `engine.py`.
3. Add `from . import <M>` to `engine.py` and re-export any of `S` in the
   verified surface.
4. Fix callers — module-qualified per C2 for anything in the patch-target
   table.
5. `python scripts/dev/check_move_purity.py HEAD:swingbot/core/scanning/engine.py swingbot/core/scanning/<M>.py <symbols>`
6. Run the task's narrow tests.
7. One commit: `refactor(v61): move <concern> out of scanning/engine into <M>.py`

---

### Task 2: `runstate.py`

**Symbols:** `_STOP_FILE`, `_RUNNING_FILE`, `is_stop_requested`,
`request_stop`, `_clear_stop`, `is_scan_running`, `_mark_running`

**Interfaces:**
- Produces: `runstate.is_stop_requested() -> bool`, `runstate.request_stop() -> None`, `runstate.is_scan_running() -> bool`, `runstate._clear_stop()`, `runstate._mark_running(running: bool)`.
- Consumes: nothing. Leaf module.

`is_stop_requested` is patched by tests and is called from the crawl loop
(`_crawl_latest_data`, moving in Task 5) and the alert loop (`_sync_run_scan`,
Task 7). Both must call `runstate.is_stop_requested()`.

Keep the module docstring explaining *why* these are files and not an
in-memory flag (engine.py lines 122–130: the admin UI is a separate process
sharing only `data/`). Move that comment with the code — it is the reason the
design is what it is.

**Narrow tests:**
```bash
python scripts/dev/testrun.py file tests/admin/test_api_v1_system_scan.py
python scripts/dev/testrun.py file tests/scanning/test_cold_fetch_pool.py
```

---

### Task 3: `telemetry.py`

**Symbols:** `TELEMETRY_PATH`, `log_scan_telemetry`, `recent_telemetry`,
`scan_slowdown`

**Interfaces:**
- Produces: `telemetry.log_scan_telemetry(stats: dict, path: str | None = None)`, `telemetry.recent_telemetry(n: int = 50, path: str | None = None) -> list`, `telemetry.scan_slowdown(path: str | None = None) -> bool`.
- Consumes: nothing. Leaf module.

All three are in the external surface (`admin/api_v1/system.py` reads them) and
must be re-exported.

**Narrow tests:**
```bash
python scripts/dev/testrun.py file tests/admin/test_api_v1_system_scan.py
```

---

### Task 4: `dedup.py`

**Symbols:** `_plans_similar`, `dedup_scan_items`, `_item_ticker`,
`dedup_sector_items`

**Interfaces:**
- Produces: `dedup.dedup_scan_items(items: list) -> list`, `dedup.dedup_sector_items(items: list) -> list`, `dedup._plans_similar(plan_a, plan_b, tol_pct=config.DEDUP_TOLERANCE_PCT) -> bool`.
- Consumes: `ScanItem` is only type-hinted here, not imported — keep it that way to avoid a cycle with `analyze.py` (Task 6).

**Known trap:** `dedup_sector_items` read `g.ticker` — an attribute absent from
a real `ScanItem` — and was a latent scan-killing `AttributeError` fixed in
`b70027b`. Move the **fixed** body verbatim; do not "improve" the attribute
access.

**Narrow tests:**
```bash
python scripts/dev/testrun.py file tests/scanning/test_no_cross_ticker_mixing.py
python scripts/dev/testrun.py file tests/scanning/test_sector_rs.py
```

---

### Task 5: `fetch.py` — the highest-risk task in this plan

**Symbols:** `LRUFrames`, `_chunked`, `_run_bounded`, `_fetch_one_ticker`,
`_fetch_cold_frames`, `_load_cached_daily`, `_crawl_latest_data`,
`_fetch_live_prices`, `_etf_symbol_of_sector`, `_sector_etfs_for_tickers`,
`_fetch_frames`, `_daily_frame_for`, `map_tickers`

**Interfaces:**
- Produces: `fetch.map_tickers(fn, tickers, workers=None) -> list`, `fetch.LRUFrames`, `fetch._crawl_latest_data(tickers, progress=None) -> dict`, `fetch._fetch_live_prices(tickers, progress=None) -> dict`, `fetch._load_cached_daily(ticker)`, `fetch._fetch_frames(symbols: list) -> dict`, `fetch._daily_frame_for(symbol: str)`, `fetch._sector_etfs_for_tickers(tickers) -> tuple`.
- Consumes: `runstate.is_stop_requested` (Task 2).

- [ ] **Step 1: Move `ProcessPoolExecutor`'s import with its caller**

The `from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor,
wait as _futures_wait` on line 52 moves to `fetch.py`, because
`_fetch_cold_frames`/`map_tickers` are what use it.

Tests do `monkeypatch.setattr(scan_engine, "ProcessPoolExecutor",
_InlineProcessPool)`. After this move that patch hits the facade and **does
nothing** — the real pool spawns real processes in the test suite. Every such
test must be updated in this same commit to patch
`swingbot.core.scanning.fetch.ProcessPoolExecutor`.

Find them all first:
```bash
git grep -n "ProcessPoolExecutor" -- 'tests/'
```

- [ ] **Step 2: Move the data-access imports too**

`get_daily_data`, `get_daily_data_batch`, `get_current_price`,
`get_current_price_batch` (engine.py lines 72–73) move to `fetch.py`. The
first two are patched by tests — same treatment as Step 1.

- [ ] **Step 3: Preserve `_run_bounded`'s docstring verbatim**

It explains why *concurrent* yfinance calls are unsafe while batched ones are
fine — the pinned version is not reentrant across threads. That reasoning is
load-bearing and is referenced from the module docstring. Move it unchanged.

- [ ] **Step 4: Purity check**

```bash
python scripts/dev/check_move_purity.py \
  HEAD:swingbot/core/scanning/engine.py swingbot/core/scanning/fetch.py \
  LRUFrames _chunked _run_bounded _fetch_one_ticker _fetch_cold_frames \
  _load_cached_daily _crawl_latest_data _fetch_live_prices _etf_symbol_of_sector \
  _sector_etfs_for_tickers _fetch_frames _daily_frame_for map_tickers
```
Expected: `OK -- 13 symbol(s) moved unchanged`

- [ ] **Step 5: Narrow tests — all of them, this is the risky one**

```bash
python scripts/dev/testrun.py file tests/scanning/test_cold_fetch_pool.py
python scripts/dev/testrun.py file tests/scanning/test_crawl_cache_first.py
python scripts/dev/testrun.py file tests/scanning/test_sidelist_cache_first.py
python scripts/dev/testrun.py file tests/scanning/test_sector_rs.py
python scripts/dev/testrun.py file tests/marketdata/test_universe.py
```

**Watch the wall-clock time.** If a previously-fast test suddenly takes tens of
seconds, a `ProcessPoolExecutor` or `get_daily_data*` patch is missing its new
target and the test is doing real work. A passing-but-slow test is the failure
mode this task exists to prevent.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/fetch.py swingbot/core/scanning/engine.py tests/
git commit -m "refactor(v61): move the crawl/fetch layer into scanning/fetch.py"
```

---

### Task 6: `analyze.py`

**Symbols:** `ScanItem`, `build_decision_context`, `_build_quality_inputs`,
`attach_plan_v2`, `_check_near_close`, `_apply_sector_rs`, `_scan_one`

**Interfaces:**
- Produces: `analyze.ScanItem` (dataclass), `analyze.build_decision_context(item, dfs: dict, spy_df) -> dict`, `analyze._scan_one(ticker, df, horizons_to_scan, progress, ...)`, `analyze.attach_plan_v2(item, scenario, df, ticker, horizon_key, level_map=None)`, `analyze._apply_sector_rs(item, ticker, sector_of_ticker, ...)`.
- Consumes: `fetch._daily_frame_for` (Task 5), `dedup` types (Task 4), `runstate` (Task 2).

**C9 applies here.** `analyze.py` may import `fetch.py` for frame *lookup*
helpers, but nothing in `_scan_one` may trigger a network fetch — the ANALYZE
phase works only from what CRAWL already fetched. Moving must not change that;
Task 8 adds the import-direction test.

**C10 applies here.** Do not reorder anything inside `_scan_one`.

**Narrow tests:**
```bash
python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py
python scripts/dev/testrun.py file tests/scanning/test_mtf_gate.py
python scripts/dev/testrun.py file tests/scanning/test_rs_gate_wiring.py
python scripts/dev/testrun.py file tests/scanning/test_no_cross_ticker_mixing.py
python scripts/dev/testrun.py file tests/charts/test_decision_chart.py
```

---

### Task 7: `scan_run.py`

**Symbols:** `ScanProgress`, `get_regime`, `_sync_run_scan`, `run_scan`,
`get_all_unrealized_pnl`

**Interfaces:**
- Produces: `scan_run.run_scan(horizon_filter="all", require_confirmation=True, bot=None, progress=None, ...)` (async), `scan_run.ScanProgress` (dataclass), `scan_run.get_regime()`, `scan_run.get_all_unrealized_pnl() -> list`.
- Consumes: every module from Tasks 2–6.

- [ ] **Step 1: Module-qualify every patched call**

`_sync_run_scan` is the single largest consumer of this part's patch targets:

```python
from . import dedup, fetch, runstate, telemetry
from . import analyze

frames = fetch._crawl_latest_data(tickers, progress)
prices = fetch._fetch_live_prices(tickers, progress)
if runstate.is_stop_requested():
    ...
deduped = dedup.dedup_scan_items(scan_items)
telemetry.log_scan_telemetry(stats)
```

- [ ] **Step 2: Keep `_scan_lock` with `run_scan`**

`_scan_lock = asyncio.Lock()` (engine.py line 120) guards against an automatic
scan and a manual `!check` writing `trades.json`/`state.json` concurrently. It
is one object; two would defeat it entirely. It moves here, with `run_scan`.

- [ ] **Step 3: Purity check**

```bash
python scripts/dev/check_move_purity.py \
  HEAD:swingbot/core/scanning/engine.py swingbot/core/scanning/scan_run.py \
  ScanProgress get_regime _sync_run_scan run_scan get_all_unrealized_pnl
```
Expected: `OK -- 5 symbol(s) moved unchanged`

- [ ] **Step 4: Narrow tests**

```bash
python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_system_scan.py
python scripts/dev/testrun.py file tests/planning/test_manager_singleton_staleness_repro.py
python scripts/dev/testrun.py file tests/test_trade_monitor_task.py
```

- [ ] **Step 5: Commit**

---

### Task 8: engine facade + the guard tests

**Files:**
- Modify: `swingbot/core/scanning/engine.py`
- Create: `tests/scanning/test_scanning_package_structure.py`

- [ ] **Step 1: Reduce `engine.py` to a facade**

Only the docstring, `state`/`trade_log`, submodule imports, re-exports and
`__all__` remain. Record the C4 exception in the docstring:

```python
"""Facade for the scanning package.

Split from the 2347-line engine.py on 2026-08-25 (v61). The scan pipeline
now lives in runstate/telemetry/dedup/fetch/analyze/scan_run; this module
re-exports the external surface so ~30 call sites keep working unchanged.

`state` and `trade_log` deliberately live HERE, not in a submodule, and every
submodule imports them from this module. They are process-wide singletons
whose identity the suite pins -- see
tests/planning/test_manager_singleton_staleness_repro.py, which guards
engine.trade_log against commands.scanning.trade_log. This is the one
permitted exception to "no submodule imports the facade".
"""
```

- [ ] **Step 2: Write the structural guard tests**

```python
# tests/scanning/test_scanning_package_structure.py
"""Guards the v61 split: the facade must stay complete, imports must not run
backwards, and the singletons must stay single."""
import ast
import pathlib

import pytest

from swingbot.core.scanning import engine

PKG = pathlib.Path(engine.__file__).parent


def test_every_exported_name_resolves():
    for name in engine.__all__:
        assert getattr(engine, name, None) is not None, f"{name} in __all__ but not importable"


def test_no_submodule_imports_the_facade():
    # The C4 singletons are the sole exception and are imported by name, not
    # via `from . import engine`; this catches the cycle-forming form.
    offenders = []
    for path in PKG.glob("*.py"):
        if path.name == "engine.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in (None, "."):
                if any(a.name == "engine" for a in node.names):
                    offenders.append(path.name)
    assert offenders == [], f"import cycle risk -- these import the facade: {offenders}"


def test_fetch_does_not_import_analyze():
    """C9: the CRAWL phase must not depend on the ANALYZE phase."""
    tree = ast.parse((PKG / "fetch.py").read_text(encoding="utf-8"))
    imported = {
        a.name for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) for a in node.names
    }
    assert "analyze" not in imported


def test_trade_log_is_one_object():
    from swingbot.core.scanning import scan_run
    assert scan_run.trade_log is engine.trade_log
```

- [ ] **Step 3: Run them**

```bash
python scripts/dev/testrun.py file tests/scanning/test_scanning_package_structure.py
```

- [ ] **Step 4: Commit**

---

### Tasks 9–13: embeds.py moves

Same shared procedure, with `HEAD:swingbot/core/scanning/embeds.py` as the old
ref. One task each, in this order (leaf-first):

| Task | Module | Symbols |
|---|---|---|
| 9 | `snapshots.py` | `_load_scan_snapshots`, `_save_scan_snapshots`, `_format_duration_hms`, `_snapshot_and_diff` |
| 10 | `requirements.py` | `RequirementCheck`, `confidence_color`, `_sources_str`, `_build_requirement_checks`, `_confidence_block` |
| 11 | `plan_table.py` | `plan_numbers_for_display`, `_ansi_bad`, `_build_trade_plan_table`, `badge_field_for`, `quality_lines`, `entry_line`, `leg_rows`, `_v2_plan` |
| 12 | `alert_embeds.py` | `build_embed`, `build_simple_alert` |
| 13 | `lifecycle_embeds.py` | `regenerate_chart_for_trade`, `build_closed_trade_embed`, `notify_closed_trades`, `build_near_close_embed`, `notify_near_close`, `build_plan_event_embed`, `notify_plan_events` |

**Task 11 carries the one that matters.** `plan_numbers_for_display` is, per
`architecture.md`, THE cutover switch deciding whether alerts show legacy
scenario numbers or v2 plan numbers, and every new consumer of plan prices must
route through it. Give `plan_table.py` a docstring saying exactly that, so the
next person finds it by filename.

**Task 13 note:** `regenerate_chart_for_trade` is reached externally as
`scan_engine.regenerate_chart_for_trade` (from `commands/trades.py`) — it must
survive both facades, `embeds.py`'s and `engine.py`'s.

**Narrow tests for Tasks 9–13:**
```bash
python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py
python scripts/dev/testrun.py file tests/scanning/test_simple_alerts.py
python scripts/dev/testrun.py file tests/charts/test_trade_chart_v2.py
```

`embeds.py` is 57 KB of presentation code and `testrun.py fast` skips the
render-heavy tier — for Tasks 12 and 13 use `python scripts/dev/testrun.py
file` on each named file rather than the fast tier, so chart rendering is
actually exercised.

---

### Task 14: embeds facade

**Files:** Modify `swingbot/core/scanning/embeds.py`

- [ ] **Step 1: Reduce to a facade with `__all__`**

It must still export everything `engine.py` lines 104–110 import:
`CONFIDENCE_COLORS`, `confidence_color`, `_build_requirement_checks`,
`build_embed`, `build_simple_alert`, `plan_numbers_for_display`,
`regenerate_chart_for_trade`, `build_closed_trade_embed`,
`notify_closed_trades`, `build_near_close_embed`, `notify_near_close` — plus
`build_plan_event_embed` and `notify_plan_events`.

- [ ] **Step 2: Extend the structure test**

Add to `tests/scanning/test_scanning_package_structure.py`:

```python
def test_engine_still_reexports_the_embeds_surface():
    """engine.py's lines 104-110 re-export contract, pinned."""
    from swingbot.core.scanning import engine
    for name in ("CONFIDENCE_COLORS", "confidence_color", "build_embed",
                 "build_simple_alert", "plan_numbers_for_display",
                 "regenerate_chart_for_trade", "build_closed_trade_embed",
                 "notify_closed_trades", "build_near_close_embed",
                 "notify_near_close"):
        assert getattr(engine, name, None) is not None, f"engine lost {name}"
```

- [ ] **Step 3: Run and commit**

---

### Task 15: Full verification

- [ ] **Step 1: Confirm the shapes**

```bash
wc -l swingbot/core/scanning/*.py
git grep -n "from swingbot.core.scanning import engine" -- swingbot/core/scanning/
```
Expected: `engine.py` under ~170 lines, `embeds.py` under ~80, no module over
~900; second command returns nothing.

- [ ] **Step 2: Full suite via subagent**

Dispatch `test-runner`: `python scripts/dev/testrun.py full`.

Expected: `0 failed, 0 xfailed`, counts within a handful of Task 1's baseline.

**If the pass count rose or the run got much slower, do not celebrate —
investigate.** Both are symptoms of a `ProcessPoolExecutor` or
`get_daily_data*` patch that no longer binds, letting tests do real work.

- [ ] **Step 3: Merge and clean up**

Merge to `main`, remove the worktree and branch per
`docs/claude/document-lifecycle.md`. Do not re-run the suite after a
conflict-free merge.
