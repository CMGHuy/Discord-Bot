# Test-Suite Cost Reduction — Implementation Plan (v7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute in order T1→T12.

**Goal:** Cut the per-change cost of the **1145-test** suite along both axes — wall-clock (180s → ~40-60s gate, ~27s inner loop) and agent context (hundreds/thousands of tokens per run → ~50) — per `docs/superpowers/specs/2026-08-07-test-cost-reduction-design.md`.

**Architecture:** A single wrapper `scripts/testrun.py` becomes the only entry point any agent calls. It owns worker count (`-n 4`, measured-optimal), tier selection (`slow` marker), auto-escalation on chart/template edits, and — critically — output discipline: full pytest output to a gitignored log, progress to stderr, and a 1-3 line verdict to stdout. A `test-runner` subagent wraps it so full-suite output never enters the main context. The bare `python -m pytest` default is left semantically unchanged so the recorded baseline stays comparable.

**Tech Stack:** pytest 9.1.1, pytest-xdist 3.8.0, PIL 12.3.0, matplotlib 3.11.0 (all already installed — this plan adds no dependencies).

## Progress

> Updated by the executing session after each task. Resume from the first unchecked task.
>
> - **Branch:** `main` (worked directly on main, per human partner's instruction 2026-08-07)
> - **Completed:** T1-T10. T10: all 24 `getsize` render proxies replaced with `assert_rendered`; slow tier green at production DPI (64 passed). The two non-proxy size assertions (decision_chart size *comparison*, shadow_log stays-small) deliberately preserved. Pre-existing unused imports (np, pd) left alone; the one `import os` my edit orphaned was removed.
> - **Next:** T11 (low-DPI autouse fixture) -- NOTE: box at 99% CPU from VS Code/Docker, timings unreliable

## Global Constraints

- **Do not add `-m "not slow"` or `-n` to `pytest.ini` `addopts`.** The bare `python -m pytest` must keep its current serial, full-scope semantics so it stays comparable to the recorded baseline. Tiering and parallelism are opt-in via the wrapper only. Violating this is the silent-no-op class of bug `docs/claude/known-traps.md` exists to catch.
- **Green means `0 failed, 1 xfailed` against 1145 collected** after T1. Before T1 it is `1 failed, 1008 passed, 136 skipped`. Note that CLAUDE.md and `/gate` currently record a *stale* baseline (`841 passed, 54 skipped`) that no longer matches the suite — do not compare against it; T12 fixes it.
- **`-q` suppresses pytest 9.1.1's summary count line**, and `pytest.ini` sets `addopts = -q`. Any tooling that parses counts must override `-q`. This bit during design.
- **Never "fix" `test_flag_on_polls_open_plans`** — quarantine only (T1). Forbidden side quest per CLAUDE.md.
- **Re-measurement requires a 20s cooldown between runs.** Back-to-back runs inflate each other by up to 4x; this invalidated a whole round of measurements during design.
- Windows dev machine: use `python`, never `python3`; no `%-d` strftime flags.
- Conventional commits, one per task. `git add <explicit paths>`, never `git add -A`.
- Each task ends green plus the py_compile loop before commit.

## File Structure

```
scripts/testrun.py                              NEW  the only entry point agents call (T4-T6)
.claude/agents/test-runner.md                   NEW  subagent wrapping the wrapper (T7)
pytest.ini                                      marker registration + corrected guidance (T3)
.gitignore                                      + .pytest-last-run.log, .pytest_cache/ (T3)
tests/test_trade_monitor_wiring.py              xfail quarantine (T1)
tests/conftest.py                               + assert_rendered(), low-DPI fixture (T9, T11)
tests/test_decision_chart.py                    pytestmark slow (T8); getsize -> assert_rendered (T10)
tests/test_plan_chart_overlays.py               same
tests/test_trade_chart_v2.py                    same
tests/test_portfolio_charts.py                  same
tests/test_chart_theme.py                       same
tests/test_analytics_charts.py                  same
tests/test_chart_cache.py                       same
tests/test_backtest_scenarios.py                pytestmark slow (T8)
tests/test_growth_command.py                    pytestmark slow (T8)
.claude/skills/gate/SKILL.md                    rewritten around wrapper + 0-failure baseline (T12)
CLAUDE.md                                       corrected numbers and commands (T12)
docs/claude/testing-cost.md                     NEW  measured baseline + how to re-derive (T2)
```

---

# Phase 0 — Baseline (T1–T2)

### Task T1: Quarantine the wall-clock failure

**Files:** Modify `tests/test_trade_monitor_wiring.py`

**Why first:** every later task's verification compares against a baseline. Making that baseline `0 failed` turns every subsequent check from a judgment call into a machine comparison.

- [x] **Step 1: Mark the test xfail**

```python
@pytest.mark.xfail(
    strict=False,
    reason="wall-clock/expiry dependent: run_manager_tick() goes through real "
           "dates, so the pending plan expires to cancelled_expired instead of "
           "filling. Pre-existing since Task E7. Quarantined, NOT fixed — see CLAUDE.md.",
)
def test_flag_on_polls_open_plans(tmp_path, monkeypatch):
```

Add `import pytest` if absent.

- [x] **Step 2: Verify the new baseline**

```powershell
python -m pytest tests/test_trade_monitor_wiring.py -q
```

Expect `1 passed, 1 xfailed`. `strict=False` is deliberate: if the wall-clock
conditions ever make it pass, that must be an `xpass`, not a new failure.

- [x] **Step 3: Record the full-suite baseline**

```powershell
python -m pytest tests/ -p no:cacheprovider -n 4
```

Omit `-q` — it suppresses the summary line in pytest 9.1.1. Expect
`0 failed, 1008 passed, 136 skipped, 1 xfailed` (1145 collected). Commit.

### Task T2: Record the measured baseline as a reference doc

**Files:** Create `docs/claude/testing-cost.md`

- [x] **Step 1: Write the doc** containing the design's measurement table (serial 180.4s, `-n 4` 40.2s, `-n auto` 60.0s, fast serial 27.1s), the 20s-cooldown requirement, and the one-liner for re-deriving the optimal worker count on different hardware:

```powershell
foreach ($n in 2,4,6,8) { Start-Sleep 20; Measure-Command { python -m pytest tests/ -q -n $n } }
```

- [x] **Step 2:** Commit. This is the artifact that stops the next session from re-deriving all of it.

---

# Phase 1 — The wrapper (T3–T7)

> This phase delivers ~90% of the wall-clock win (T3/T4) and the entire token win (T5–T7).

### Task T3: Register the marker and fix the documented guidance

**Files:** Modify `pytest.ini`, `.gitignore`

- [x] **Step 1: Register the `slow` marker in `pytest.ini`**

```ini
markers =
    slow: heavy render/backtest test (~85% of suite runtime); excluded from the fast tier
```

- [x] **Step 2: Correct the parallelism comment.** The existing comment recommends `-n auto`. Measured on this box, `-n auto` (12 workers, 60.0s) is *worse* than `-n 4` (40.2s). Replace the recommendation with `-n 4` and cite `docs/claude/testing-cost.md`. Keep the existing (correct) warning about contending with a live backtest.

- [x] **Step 3: `addopts` stays exactly `-q`.** Do not add `-n` or `-m` — see Global Constraints.

- [x] **Step 4: Add to `.gitignore`** (it currently has no pytest entries):

```
.pytest_cache/
.pytest-last-run.log
```

- [x] **Step 5:** Verify `python -m pytest tests/ -q` behaviour is unchanged. Commit.

### Task T4: `scripts/testrun.py` — core profiles

**Files:** Create `scripts/testrun.py`

**Interfaces — Produces:** the CLI every later task and the subagent depend on.

- [x] **Step 1: Implement the profiles**

| Command | pytest args | Expected |
| --- | --- | --- |
| `testrun.py fast` | `-m "not slow"`, serial | ~27s |
| `testrun.py full` | `-n 4` | ~40s |
| `testrun.py file <path>` | serial, that path | ~7s |
| `testrun.py lf` | `--lf`, serial | seconds |

Fast runs **serial on purpose** — measured 27.1s serial vs 27.2s at `-n 4`. It is at the fixed-overhead floor; workers only add startup cost.

- [x] **Step 2: Output discipline** (the whole point):
  - full pytest output → `.pytest-last-run.log`
  - progress → **stderr**, one flushed line per completed file
  - stdout → verdict only:
    ```
    VERDICT: PASS  862 passed, 54 skipped, 1 xfailed, 0 failed  in 40.2s
    ```
    On failure: summary + up to 10 failing node IDs + log path. **Never tracebacks.**
  - exit code mirrors pass/fail

- [x] **Step 3: Parse counts, defensively.** The wrapper must pass `-p no:cacheprovider` and **override `pytest.ini`'s `-q`**, because `-q` suppresses the summary count line entirely in pytest 9.1.1 — a naive parser sees no counts and must not interpret that as success. If the counts line cannot be parsed, exit non-zero with `VERDICT: UNKNOWN (could not parse pytest output)`. Never report PASS on an unparseable run.

- [x] **Step 4: Verify** each profile's timing and that a deliberately broken test produces a `VERDICT: FAIL` with node IDs and no traceback on stdout. Commit.

### Task T5: Auto-escalation on chart/template edits

**Files:** Modify `scripts/testrun.py`

- [x] **Step 1:** In the `fast` profile, run `git diff --name-only HEAD`. If any path matches `swingbot/core/charts/`, `swingbot/admin/templates/`, or `swingbot/admin/static/`, escalate to the `full` profile and print exactly one stdout line:

```
NOTE: charts/templates touched -> escalating to full tier
```

- [x] **Step 2: Verify** both branches (touch a chart file, confirm escalation; touch only `swingbot/core/edge/gates.py`, confirm no escalation). Handle the no-git / detached-HEAD case by defaulting to the full tier — fail safe, not fast. Commit.

### Task T6: Progress output for long runs

**Files:** Modify `scripts/testrun.py`

- [x] **Step 1:** Confirm the per-file stderr progress line actually flushes during a `full` run (CLAUDE.md's rule: any script running more than a couple of minutes must emit incremental progress). At ~40s the `full` profile is under that bar, but the serial `python -m pytest` passthrough is not.
- [x] **Step 2:** Verify by watching stderr live during a full run. Commit.

### Task T7: `test-runner` subagent

**Files:** Create `.claude/agents/test-runner.md`

- [x] **Step 1:** Mirror the existing `backtest-runner` agent definition. Tools: `Bash, Read, Grep`. Instructions: run `python scripts/testrun.py <profile>`, return **only** the verdict line plus any failing node IDs; never paste pytest output; on failure, read `.pytest-last-run.log` and summarise the failure in at most 3 sentences.
- [x] **Step 2: Verify** by dispatching it for a `full` run and confirming the returned report is a handful of lines. Commit.

---

# Phase 2 — Tiering (T8)

### Task T8: Mark the heavy files `slow`

**Files:** Modify the nine files listed below

- [x] **Step 1:** Add module-level `pytestmark = pytest.mark.slow` (one line per file, **not** per test) to:

```
test_decision_chart.py      test_plan_chart_overlays.py   test_trade_chart_v2.py
test_portfolio_charts.py    test_chart_theme.py           test_analytics_charts.py
test_backtest_scenarios.py  test_growth_command.py        test_chart_cache.py
```

These are ~153s of the 180.4s serial suite (85%).

- [x] **Step 2: Optional, measure before keeping.** Two individually-slow tests live in otherwise-fast files: `test_engine_v2_plans::test_sync_run_scan_parallel_dispatch_matches_serial` and `test_entry_filters::test_live_signals_agree_with_entry_filters`. The fast tier already hits 27.1s without excluding them, so only mark them if measurement shows a real gain.

- [x] **Step 3: Verify** `testrun.py fast` ~27s, `testrun.py full` ~40s, and that `fast` + the slow tier together collect the same total as `full`. Commit.

---

# Phase 3 — Chart-test refactor (T9–T11)

> Primarily an assertion-quality improvement. Most of the wall-clock benefit is already captured by `-n 4`. **T9 must land before T11.**

### Task T9: `assert_rendered()` helper

**Files:** Modify `tests/conftest.py`

- [x] **Step 1:** Add a resolution-independent helper (PIL 12.3.0 already installed):

```python
def assert_rendered(path, min_colors=16):
    """Assert `path` is a real rendered chart, not a blank canvas or stub.

    Replaces the `os.path.getsize(path) > N` proxy, which conflated "big file"
    with "actually drew something" and broke the moment render DPI changed.
    """
```

Assert: file exists, decodes as an image, has non-zero dimensions, and contains more than `min_colors` distinct colors.

- [x] **Step 2: Verify** it passes on a current full-DPI render and fails on a deliberately blank figure. Commit.

### Task T10: Replace the 24 `getsize` proxies

**Files:** the 7 chart test files carrying them

- [x] **Step 1:** Replace each `assert os.path.getsize(path) > N` with `assert_rendered(path)`. Locations recorded during design: `test_decision_chart.py` (10), `test_portfolio_charts.py` (5), `test_analytics_charts.py` (4), `test_trade_chart_v2.py` (2), `test_plan_chart_overlays.py` (2), `test_chart_theme.py` (1), `test_chart_cache.py` (1).

- [x] **Step 2: Leave two alone.** `test_decision_chart.py:80` compares two files' sizes to each other, and `test_shadow_log.py:29` asserts a file stays *small* — neither is a render proxy. Verify individually before touching.

- [x] **Step 3: Verify** the chart tier is green at production DPI (unchanged timing at this point). Commit.

### Task T11: Low-DPI test fixture

**Files:** Modify `tests/conftest.py`

- [ ] **Step 1:** Add an autouse fixture forcing `plt.figure`, `plt.subplots`, and `Figure.savefig` to dpi=30, honouring a `SWINGBOT_TEST_FULL_DPI=1` escape hatch for eyeballing generated PNGs.

- [ ] **Step 2: Verify.** Expect the 5-file chart tier to drop 84s → ~44s serial, with everything green. `test_heat_treemap_renders` is the canary: it failed at dpi=30 under the old `getsize(path) > 5_000` assertion during design, and must now pass because T10 replaced that proxy. If it still fails, T10 was incomplete.

- [ ] **Step 3:** Re-measure `full` and `fast` with the 20s cooldown; update `docs/claude/testing-cost.md`. Commit.

---

# Phase 4 — Documentation (T12)

### Task T12: Rewrite `/gate` and correct CLAUDE.md

**Files:** Modify `.claude/skills/gate/SKILL.md`, `CLAUDE.md`

- [ ] **Step 1: `/gate`** — replace Steps 2/4/5. The ~40 lines teaching how to distinguish the known failure from a real regression collapse to: run `python scripts/testrun.py full`, expect `0 failed, 1 xfailed`, any other result is yours. Keep Step 1 (CPU contention check) and Step 6 (narrow staging) as-is; both are still correct.

- [ ] **Step 2: CLAUDE.md** — correct these, all now measurably wrong:
  - "~3min" full suite → ~40s via the wrapper
  - the `841 passed, 54 skipped, 1 failed` baseline → post-T1 counts with `1 xfailed`
  - the "one permitted failure" paragraph → quarantined, verdict is machine-checkable
  - "Don't re-run the full suite to check a local change" → point at `testrun.py fast` / `file`
  - add the `test-runner` subagent to the tooling list

- [ ] **Step 3: Verify** by running `/gate` end to end. Commit.

---

## Verification Summary

| Measure | Before | Target | Task |
| --- | --- | --- | --- |
| Inner-loop run | 180s | <= 30s | T4, T8 |
| Pre-commit gate | 180s | <= 60s | T4 |
| Context per run | hundreds-thousands of tokens | ~50 | T4, T7 |
| Gate verdict | manual comparison vs stale baseline | machine-checkable, current | T1, T12 |
| Chart tier | 84s | ~44s | T11 |
| Chart assertions | 24 byte-count proxies | resolution-independent | T9, T10 |
