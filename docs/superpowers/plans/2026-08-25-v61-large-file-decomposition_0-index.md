# v61 — Large-file decomposition: index and shared conventions

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement each part task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the three largest source files into focused modules by
relocating whole functions, with every moved body byte-identical.

**Spec:** `docs/superpowers/specs/2026-08-25-v61-large-file-decomposition-design.md`

**Architecture:** Each split file stays as a thin facade re-exporting its
verified external surface, so ~30 call sites never change. Inside each
package, modules import each other directly. Function *decomposition* is
explicitly out of scope — deferred to a Phase B spec.

**Tech Stack:** Python 3.11+, pytest, discord.py. No new dependencies.

## Parts

| Part | File(s) split | Tasks | Order |
|---|---|---|---|
| `_1` | `swingbot/commands/scanning.py` (1824) | 9 | first — cleanest seams, proves the pattern |
| `_2` | `swingbot/core/scanning/engine.py` (2347) + `embeds.py` (1109) | 15 | the main event |
| `_3` | `swingbot/core/planning/plan_engine.py` (1419) | 9 | last — shares the exit simulator with the backtest |

Each part executes in its own worktree named for that part's file stem, per
`docs/claude/document-conventions.md`, and merges before the next begins.

---

## Global Constraints

These apply to **every task in every part**. They are not repeated per task.

### C1 — The move invariant

> A moved function's body is byte-identical across the move. Only the module
> it lives in, and the import block at the top of that module, change.

No renames. No signature changes. No reordering of statements. No "while I'm
here" cleanups. No docstring edits — a moved docstring moves verbatim,
including a now-wrong relative path reference, which is fixed in a **separate
commit** if it matters.

If a move reveals a real bug, record it and fix it in its own commit, never
folded into a move. A move commit that also fixes something is a plan
violation, because it destroys the property that makes these diffs safe to
approve.

### C2 — Call moved-and-patched symbols through their module

Any symbol the test suite monkeypatches must be called through its module,
never imported by bare name:

```python
# WRONG -- binds the name at import; monkeypatching presence._foo won't reach here
from .presence import _refresh_presence
await _refresh_presence()

# RIGHT -- resolves through the module at call time; one patch point
from . import presence
await presence._refresh_presence()
```

**Why this matters more than it looks.** A facade re-export is a different
binding than the callee's module global. Under the wrong form, a test that
patches the definition site patches nothing, the real function runs, and the
test still passes — hitting the real network or spawning real processes. It
is a silent failure, which is worse than a loud one.

Each part lists its own confirmed patch targets. Treat those lists as
verified-as-of-2026-08-25, and re-run the enumeration as the part's first
task.

### C3 — Facades declare `__all__`

Each split file remains as a facade whose `__all__` is the verified external
surface. A name absent from `__all__` is internal; callers reach it at its
real home. No module inside a package may import its own facade — that is how
import cycles form.

### C4 — Singletons live in exactly one module

Module-level instances (`trade_log = TradeLog()`, `state = StateStore()`) must
be constructed once, in one module, and imported everywhere else. Two modules
each constructing their own means the scan writes to one and reads from the
other, silently.

This repo has been bitten by exactly this before — see
`tests/planning/test_manager_singleton_staleness_repro.py`, which already
guards the `engine.trade_log` / `commands.scanning.trade_log` relationship.
Read it before moving either.

### C5 — Verification cadence

Per task: the part's narrow test run, which is
`python scripts/dev/testrun.py file tests/<file>.py` (~7s each). Never a bare
`python -m pytest` over the suite.

Per part, once, as its final task: `python scripts/dev/testrun.py full`,
dispatched to the `test-runner` subagent so ~1150 progress lines never reach
the controlling context.

**Green is `0 failed` AND `0 xfailed`.** A changed pass/skip count is not a
failure; a new `xfailed` is. Reference baseline before this work:
`2360 passed, 66 skipped, 0 failed, 0 xfailed` (per the v59 spec, after
`ffb8297`). Re-derive it at the start of part `_1` rather than trusting this
number.

### C6 — Commit granularity

One commit per task. Never bundle multiple modules' moves into one commit —
the reviewable property of this work is that each diff is a pure relocation,
and that is only visible one move at a time.

### C7 — The move-purity check

Before committing any move task, confirm the bodies really are identical.
This helper exists for that and is created in part `_1`, Task 1:

```bash
python scripts/dev/check_move_purity.py <old-ref> <new-file> <symbol>...
```

It extracts each named function/class body from git's version of the old file
and from the new file on disk, normalises only leading indentation, and
reports any symbol whose body differs. A non-empty report blocks the commit.
