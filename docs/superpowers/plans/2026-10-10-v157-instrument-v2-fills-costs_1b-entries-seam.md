# v157 Instrument v2, phase 2: fills and costs. Part 1b: v2 entries and the `simulate_exit` seam (FC5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md` (section 2 "Fills and costs", rule 1, "Testing")
**Bump:** bot minor
**Edge:** none (integrity)

> The second half of part 1 (Phase B), split off `2026-10-10-v157-instrument-v2-fills-costs_1-contract-fills-walk.md` only to keep each file under 1500 lines. Index, Global Constraints, Where to work, Parallelisation and the task ledger: `2026-10-10-v157-instrument-v2-fills-costs_0-index.md`. Every task here implicitly includes the index's Global Constraints. Pull the task with `grep -n "^### Task FC5" -A 500 docs/superpowers/plans/2026-10-10-v157-instrument-v2-fills-costs_1b-entries-seam.md`.

`$R` is the main tree's root, `$WT` = `$R/.claude/worktrees/2026-10-10-v157-instrument-v2-fills-costs`. Never `cd`; every command uses absolute paths or `git -C $WT`.

Worked numbers in the tests below were computed by running the code shown here against today's `main`; a mismatch is a bug in the implementation, not a reason to edit an expected value.

# Phase B (continued): v2 entries behind the seam

