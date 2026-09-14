# v86 — Cohort Risk Label Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot minor, ui patch
**Edge:** none (integrity)
**Spec:** `docs/superpowers/specs/2026-09-14-v86-cohort-risk-label-design.md`

**Goal:** Every confluence plan carries a label saying how trades under its own
conditions have actually closed, so a reader is warned off the cells that lose
money — without suppressing anything, and with the suppression decision
pre-registered for later.

**Architecture:** A second frozen registry (`cohort_registry.json`) beside
`validation_registry.json`, keyed on `direction × regime2` (8 cells), built by
blending the confluence backtest pool (prior) with the live book (update) under
Beta-binomial shrinkage. `stamp_cohort` stamps the label onto every plan the way
`stamp_badge` stamps the badge; a parallel `risk_features` dict captures
candidate discriminators at issuance for the later analysis. Render-only
surfaces; no gate, exit, fill or sizing rule moves.

**Tech Stack:** Python 3.11+, pandas/numpy, pytest, discord.py, Angular (one chip).

## Parts

| Part | Tasks | Covers |
|---|---|---|
| `_1-registry.md` | C1–C3 | Spec §3 — the registry module, its generator, and plan stamping |
| `_2-features-surfaces.md` | C4–C9 | Spec §4, §5, §8 — feature stamping, journal, report, surfaces, verification |

## Global Constraints

Copied verbatim from the spec — every task's requirements implicitly include
these.

- **Key:** `direction` (`bullish`/`bearish`) × `regime2` state
  (`bull_quiet`/`bull_volatile`/`bear_quiet`/`bear_volatile`) = **8 cells**.
  `confidence_level` is deliberately NOT a key dimension in v1 (spec §3.1).
- **Shrinkage:** `p_blend = (n_live·p_live + K·p_backtest) / (n_live + K)`,
  **`K = 100`**, applied identically to win rate and ExpR. Frozen, never tuned.
- **N floor:** `n_live + n_backtest < 50` ⇒ `COHORT_UNKNOWN`.
- **Banding margin:** **±0.15R against the pool mean.** `≤ pool_mean − 0.15R` ⇒
  `COHORT_POOR`; `≥ pool_mean + 0.15R` ⇒ `COHORT_STRONG`; else
  `COHORT_TYPICAL`. Frozen, never tuned.
- **Forward-only:** the registry carries `run_date`; plans persist
  `cohort_stats`; §6's verification reads only plans created strictly after the
  freeze.
- **NO-LOOKAHEAD:** every stamped feature is computed from the creating bar and
  earlier only (`docs/claude/architecture.md`).
- **Nothing is suppressed.** No task in this plan may change a gate, exit, fill
  or sizing rule. Pooled paper `ExpR` must be unchanged by construction.
- **`days_to_earnings` is opportunistic** — null when v82's calendar is absent.
  Never a hard dependency; no task may block on v82.

## Parallelisation

- **C1 → C2 → C3 are strictly sequential** (C2 consumes C1's pure functions; C3
  consumes C2's emitted JSON).
- **C4–C6 (features) share no file with C7–C8 (surfaces)** and may run in
  parallel worktrees once C3 is merged.
- **C9 runs last, alone.** It is the only task that runs the full suite.
- Per `docs/claude/skills-tools.md`, the default is one subagent at a time;
  parallel worktrees here are an option, not an instruction.

## Verification cadence

Per CLAUDE.md: each task runs only its own file
(`python scripts/dev/testrun.py file tests/...`, ~7s). **The full suite runs
exactly once, in C9**, and never again after a clean merge.
