# v114 — Scenario stop band 1.5-2.0% Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/no-lift/2026-09-30-v114-scenario-stop-band-design.md` (final partner decision, commit `fa8288a0`)
**Bump:** bot minor if it ships; none on a NO-LIFT
**Edge:** volume

**Closed 2026-09-30 -- abandoned before any build (partner's call, `/close-out v114`).** No branch, worktree, code or test was written; no task below was started, so every box is open by design, and no TRAIN, walk-forward or VALIDATION run was made -- the one VALIDATION shot is unspent and no pre-registration row is owed. `Bump:` resolved to none: no release commit. Unrelated to this plan, production's `MIN_STOP_DISTANCE_PCT` was set to 1.0 by `9a3a8757`, mirrored in `.env.example`; this plan's 1.5 floor was never applied.

**Goal:** Lower the scenario stop floor from 2.0% to 1.5%, so the admission band becomes 1.5-2.0% at real support/resistance levels. Admission is capped at the 2.0% planned-loss cap, identically in the live scan and in replay. The flip ships to production only if a pre-registered TRAIN, walk-forward and one-shot VALIDATION run passes.

**Architecture:** Phase A adds integrity tests, makes one shared admission function (`gating.admission_gates`) that both `analyze._scan_one` and replay call (ceiling = `HARD_MAX_PLANNED_LOSS_PCT`), and moves the config default and the replay defaults together. Phase B builds the instrument: rows stratified by `tight_stop`, and a volume-edge gate made only from existing acceptance clauses. Phase C pre-registers, then runs the funnel through `backtest-runner`. Phase D ships on a pass (production `.env`, mirror, release) or files a NO-LIFT.

**Tech Stack:** Python 3.11, pytest, pandas/numpy, `scripts/backtest/measure_arms.py` + `validate_component.py` (v100 funnel), Docker Compose on the Hetzner VM.

## Global Constraints

- **One threshold changes:** `MIN_STOP_DISTANCE_PCT` 2.0 -> **1.5**. `MIN_RISK_REWARD_RATIO` stays **1.5**. `MIN_REWARD_PCT` stays **2.0** (production). `HARD_MAX_PLANNED_LOSS_PCT` stays **2.0**. Every other setting stays as it is.
- Stops stay at **real support/resistance levels**. Nothing in this plan puts a stop at a fixed percentage or moves one toward a percentage.
- Scenario admission ceiling = `HARD_MAX_PLANNED_LOSS_PCT` (read from `swingbot/core/risk_limits.py`), in the live scan and in every replay path. It replaces `max(MAX_STOP_LOSS_PCT, horizon max_risk_pct)` (7-11%).
- `armed_replay.arm_candidates` keeps `min_stop_distance_pct=0.0` at arm time (spec Design §3).
- No change to the cap, sizing, reward floor, risk:reward, `STRUCTURAL_STOP_SCOPE` (stays empty), strategy entry logic, or where stops sit (spec Non-goals).
- **Integrity (not subject to validation):** no plan is issued with a planned loss above 2.0%, for any horizon or direction. The `risk_cap` reject in `attach_plan_v2` stays as the backstop. Open positions and plans keep the stops they were issued with.
- Every function written or changed ends at radon cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>`). `analyze._scan_one` is legacy (currently E 39); it must not score higher after this plan.
- NO-LOOKAHEAD: every as-of computation in this plan reads `df.iloc[:i + 1]` only.
- **Production is not touched until V114-15, and only on a PASS.** Until then production keeps rejecting everything the current band rejects.
- One VALIDATION shot, ever. A failed stage closes the spec as NO-LIFT. No re-run without the partner, and no loosened threshold.
- Code lives on the worktree branch `2026-09-30-v114-scenario-stop-band` (`.claude/worktrees/2026-09-30-v114-scenario-stop-band/`). Results documents under `docs/superpowers/results/` are committed on `main`.
- Commits are small and single-purpose (never bundle unrelated files). Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Per-task checks use `python scripts/dev/testrun.py file <test>` (or `... fast` where noted). The full suite runs once, in V114-15.

## Parallelisation

- **Sequential:** V114-01 before everything. It creates the worktree every other task works in, and its inventory is the list later tasks edit.
- **Group 1 (parallel):** V114-02, V114-03, V114-06. Their files do not overlap (02: new `tests/planning/test_v114_cap_integrity.py`. 03: `gating.py`, `analyze.py`, `tests/scanning/test_gating.py`, the new parity test, the two `scripts/dev/diagnose_funnel*.py`, and the scan tests it has to loosen. 06: `acceptance.py`, `arms/confluence_engine.py`, `tests/backtesting/arms/test_confluence_engine.py`), and none of them uses a symbol another one introduces.
- **Group 2 (parallel, after Group 1):** V114-04, V114-05, V114-07. Their files do not overlap. V114-04 must come after V114-03: it reclassifies `MAX_STOP_LOSS_PCT` because V114-03 removed that setting from admission. V114-05 must come after V114-03: its lockstep test reads replay gates through the shared function. V114-07 must come after V114-06: it reads `ArmTrade.tight_stop`.
- **Sequential:** V114-08 after V114-07 (it imports `evaluate_volume`, `walkforward_verdict` and the render helpers). V114-09 after all code tasks: the pre-registration pins the branch HEAD that every stage runs on. V114-10 -> V114-11 -> V114-12 run strictly in order, and each one is gated on the one before. Exactly one of V114-13 (NO-LIFT) or V114-14 (PASS) runs. V114-15 runs last.

---
## Parts

| Part | Phases | Tasks |
|---|---|---|
| `2026-09-30-v114-scenario-stop-band_1-build.md` | A — integrity and the shared admission band; B — the instrument | V114-01 … V114-08 |
| `2026-09-30-v114-scenario-stop-band_2-measure-ship.md` | C — pre-registration and measurement; D — NO-LIFT or ship | V114-09 … V114-15 |

Pull one task at a time: `grep -n "^### Task V114-03" -A 120 docs/superpowers/plans/no-lift/2026-09-30-v114-scenario-stop-band_*.md`.
