# v212 — Confluence limit entry, part 3c: measurement (disclosures wiring)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [v212 — Confluence limit entry partway to the support](../specs/2026-11-06-v212-confluence-limit-entry.md)
**Index:** [`2026-11-06-v212-confluence-limit-entry_0-index.md`](2026-11-06-v212-confluence-limit-entry_0-index.md) — Goal, Architecture, **Global Constraints**, Review Focus, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.
**Brief:** `.superpowers/briefs/2026-11-06-v212-confluence-limit-entry.md`

Continuation of part 3b (`2026-11-06-v212-confluence-limit-entry_3b-measurement-stages.md`,
V212-13b .. V212-14b), split off because part 3b reached the 1500-line cap.
One task, V212-14c: the measure script's Stage 1 and Stage 3 runners print
the disclosures module's output (V212-14, V212-14b) and the touch-fill
sensitivity. Same worktree (`.claude/worktrees/2026-11-06-v212-confluence-limit-entry`);
the verification is the narrow run; no task runs the full suite or reads the database.

# Phase D — measurement (continued)

### Task V212-14c: Measure script prints the disclosures: Stage 1 and Stage 3 wrap, touch-fill sensitivity, SPY and earnings inputs

**Model:** sonnet — wiring a finished module into two stage runners; the one care point is that Stage 3 builds only for the selected cell and still writes its file once.

**Files:**
- Modify: `scripts/backtest/measure_confluence_limit.py` (import; a `# --- disclosures` section after `# --- ledger`, before `# --- CLI`)
- Test: `tests/backtest_scripts/test_measure_confluence_limit_stages.py` (modify; created by V212-13c: patch the two loaders in the autouse fixture; the two build-call assertions now include the census and touch builds; one new test)

**Interfaces:**
- Consumes: V212-14/14b `confluence_limit_disclosures.disclosures`, `render_disclosures`, `spy_changes`; V212-13 `rows_file`, `_load`, `_write`, `stage_path`, `WINDOWS`; V212-13c `_run_1`, `_run_3`, `_env`, `_rows`, `score_cell`, `STAGE_RUNNERS`; existing `measure_arms.load_frame`, `earnings_calendar.CsvSource().has_data(t)` / `.reports(t)` (`Report.date`, `earnings_calendar.py:24-92`).
- Produces (V212-16 reads it): `v212-stage1.json` and `v212-stage3.json` gain a `"disclosures"` key, `{"window": "train" | "validation", "cells": [disclosures(...) per cell], "touch": [score_cell(...)[0] per cell on the touch rows]}`; helpers `_spy() -> dict`, `_earnings(tickers) -> dict`, `_disclose(ctx, rows, census, cells, window_name, f_cells) -> dict`; `STAGE_RUNNERS[1]` / `[3]` replaced by `_run_1_disclosed` / `_run_3_disclosed` (verdicts unchanged).

**Decisions fixed here:**
- **The verdict is computed first and never reads the disclosures**: each wrapper calls V212-13c's runner, then adds the key. `run_stage` writes the file after the runner returns, so a crash while disclosing leaves no Stage 3 file and the same command resumes from the saved rows files (never a second shot).
- **Stage 1 (TRAIN, all three cells)** reuses the TRAIN rows and census files and builds the TRAIN touch rows once (`touch=True`, `F_GRID`). **Stage 3 (VALIDATION, selected cell only)** builds the VALIDATION census and touch rows for the selected `f` only (v139 precedent: nothing is replayed for an unselected cell).
- The touch sensitivity is scored by `score_cell` (own portfolio pass, same clauses) and printed; it never feeds `plateau` or a stage verdict.
- SPY comes from the training cache (`load_frame("SPY")`; an empty dict when absent, every fill then counted in `spy_missing`); earnings from `CsvSource` report dates, only for tickers that have a CSV.

- [ ] **Step 1: Update the stage test** `tests/backtest_scripts/test_measure_confluence_limit_stages.py`

Add two lines at the end of the autouse fixture `_open_caps`:

```python
    monkeypatch.setattr(mcl, "_spy", lambda: {"2021-03-01": -1.5})
    monkeypatch.setattr(mcl, "_earnings", lambda tickers: {})
```

In `test_the_full_chain_reads_validation_for_the_selected_cell_only`, replace the last four lines (from `validation = ...`) with:

```python
    validation = [c for c in calls if c[1] == mcl.VALIDATION]
    assert validation == [("rows", mcl.VALIDATION, False, (0.333,)),       # the shot
                          ("census", mcl.VALIDATION, False, (0.333,)),     # disclosures only
                          ("rows", mcl.VALIDATION, True, (0.333,))]        # touch sensitivity
    train_rows = [c for c in calls if c[0] == "rows" and c[1] == mcl.TRAIN]
    assert sorted(c[2] for c in train_rows) == [False, True]   # each TRAIN file built once
```

Append:

```python
def test_stages_1_and_3_carry_disclosures_that_never_change_the_verdict(tmp_path):
    from swingbot.core.backtesting.confluence_limit_disclosures import render_disclosures
    verdicts = [_run(stage, tmp_path, [])["verdict"] for stage in (-1, 0, 1, 2, 3)]
    assert verdicts == ["REACHABLE", "POWERED", "SELECTED", "PASS", "THIN"]
    blob = mcl._load(mcl.stage_path(tmp_path, 1))["disclosures"]
    assert blob["window"] == "train"
    assert [c["cell"] for c in blob["cells"]] == list(clr.CELLS)
    assert [t["cell"] for t in blob["touch"]] == list(clr.CELLS)
    assert blob["cells"][0]["paired"]["alerts"] == 300          # 100 alerts x 3 TRAIN years
    stage3 = mcl._load(mcl.stage_path(tmp_path, 3))["disclosures"]
    assert (stage3["window"], [c["cell"] for c in stage3["cells"]]) == ("validation", ["f0.333"])
    text = render_disclosures(blob)
    assert "D range" in text and "direction" in text
    assert "disclosures" not in mcl._load(mcl.stage_path(tmp_path, 2))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit_stages.py`
Expected: FAIL — `AttributeError: <module 'measure_confluence_limit' ...> has no attribute '_spy'` (the fixture's `monkeypatch.setattr`).

- [ ] **Step 3: Add the import** next to the other `swingbot.core.backtesting` imports in `scripts/backtest/measure_confluence_limit.py`

```python
from swingbot.core.backtesting import confluence_limit_disclosures as cld  # noqa: E402
```

- [ ] **Step 4: Add the disclosures section** after `# --- ledger` and before `# --- CLI`

```python
# --- disclosures (printed, never gating) ----------------------------------------

def _spy() -> dict:
    """SPY close-to-close % by ISO date from the training cache; {} when absent."""
    from measure_arms import load_frame
    frame = load_frame("SPY")
    return {} if frame is None or frame.empty else cld.spy_changes(frame)


def _earnings(tickers) -> dict:
    """Report dates per ticker from market_data/earnings/; tickers without a CSV
    are left out (the disclosure counts them)."""
    from swingbot.core.market.earnings_calendar import CsvSource
    source = CsvSource()
    return {t: [report.date.isoformat() for report in source.reports(t)]
            for t in sorted(tickers) if source.has_data(t)}


def _disclose(ctx, rows, census, cells, window_name, f_cells) -> dict:
    """Every cell's disclosures plus the touch-fill sensitivity, scored with
    the same clauses through its own portfolio pass."""
    inputs = {"spy": _spy(), "earnings": _earnings({r["ticker"] for r in rows})}
    ref = [r for r in rows if r["arm"] == "ref"]
    out = []
    for cell in cells:
        _, kept = score_cell(rows, cell, **_env(ctx))
        out.append(cld.disclosures([r for r in rows if r["arm"] == cell], ref, census,
                                   portfolio=kept, **inputs))
    touch_rows = _rows(ctx, "rows", window_name, touch=True, cells=f_cells)
    touch = [score_cell(touch_rows, cell, **_env(ctx))[0] for cell in cells]
    return {"window": window_name, "cells": out, "touch": touch}


def _run_1_disclosed(ctx):
    out = _run_1(ctx)
    out["disclosures"] = _disclose(ctx, _rows(ctx, "rows", "train"),
                                   _rows(ctx, "census", "train"), clr.CELLS, "train", clr.F_GRID)
    return out


def _run_3_disclosed(ctx):
    out = _run_3(ctx)
    selected = _load(stage_path(ctx["out"], 1))["selected"]
    f_cells = (selected["f"],)
    rows = _rows(ctx, "rows", "validation", cells=f_cells)
    census = _rows(ctx, "census", "validation", cells=f_cells)
    out["disclosures"] = _disclose(ctx, rows, census, [selected["cell"]], "validation", f_cells)
    return out


STAGE_RUNNERS.update({1: _run_1_disclosed, 3: _run_3_disclosed})
```

`_rows` reads a rows file when it exists, so Stage 3's `rows` call reuses the file `_run_3` just built; only the census and touch files are new. `_cmd_stage` needs no change: it calls `run_stage`, which looks the runner up in `STAGE_RUNNERS` at call time.

- [ ] **Step 5: Run the script tests and the module test**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit_stages.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit_clauses.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit.py
python scripts/dev/testrun.py file tests/backtesting/test_confluence_limit_disclosures.py
```
Expected: PASS. If `test_ledger_rows_one_per_look` or `test_stage3_is_one_shot` fails, the wrapper changed a verdict or the write order: fix the wrapper, never the assertion.

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: PASS (`_disclose` is the busiest new function, about 6).

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/measure_confluence_limit.py tests/backtest_scripts/test_measure_confluence_limit_stages.py
git commit -m "feat(v212): stages 1 and 3 print the disclosures and the touch-fill sensitivity (V212-14c)"
```
