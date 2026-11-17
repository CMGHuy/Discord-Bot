# v230 Plan 1, Part 5 — `screen_idea` on the v2 null, the v2 placebo acceptance and the fifth clause

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V230-13" -A 400 <this file>`).

**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) (A1 under `v2`: acceptance and the planted edge; A2 "What a v2 delta means"; A3 the fifth clause; A4 instrument and ids; Found while briefing: `INSTRUMENTS`, one BH family, descriptive blocks)
**Index:** [2026-11-16-v230-screen-v2-rescreen_0-index.md](2026-11-16-v230-screen-v2-rescreen_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there; every task below obeys them.
**Tasks:** V230-12..V230-14

What this part builds: V230-12 makes `screen_idea.py` run the v2 null
(`run_v2` behind a `TickerScreen` adapter), names the `screen-v2` instrument
and prints the v2 blocks from a new `screen/v2_report.py`; the existing
script tests pin themselves to v1 through one fixture. V230-13 adds the v2
runner and the planted check to the placebo CLI and runs stop gate 2.
V230-14 adds the fifth clause to `verdict.py` and makes the context
diagnostics' q one ledger-wide family.

**Runs only if V230-5 recorded `BIAS`**; V230-14 runs only if V230-13
recorded `ACCEPT` (index `## Handoff`).

**Contracts this part adds beyond the ledger rows** (Part 6 relies on them):

- `screen_idea._run_info(args, q)` adds `"null": NULL_VERSION` and
  `"instrument": instrument()` to the run dict; `_render_head` reads both with
  v1 defaults (`run.get("null", "v1")`, `run.get("instrument", INSTRUMENT)`),
  so a run dict without them (`long_golden.py`) renders the v1 head byte for byte.
- `screen_idea._run_screens(args, ...)` dispatches on `NULL_VERSION` at call
  time; under v2 it skips `with_shock_blocks`, adds `summary["v2"]`
  (`_v2_blocks`) and, from V230-14, calls
  `with_event_clause(summary, idea, gating=not getattr(args, "rescreen_v1", False))`.
  V230-15 only has to add the `--rescreen-v1` flag for the fifth clause to turn
  reported-only.
- `screen_idea.SECTOR_MAP = Path(config.DATA_DIR) / "universe" / "sp500_pit.json"`
  (monkeypatched in tests).
- Placebo: `screen_placebo.PLANTED_JSON = "placebo-planted.json"` in
  `--json-dir`, `{"base": "<gbm label>", "value": float | None, "cell": Cell.to_dict()}`;
  the planted universe lives at `<work-dir>/universes/planted-<gbm label>/`.
  `main` prints `acceptance: <ACCEPT|STOP|ENLARGE>` as its last line once v2 cells exist.

# Phase 5 — v2 wiring, stop gate 2, the fifth clause

