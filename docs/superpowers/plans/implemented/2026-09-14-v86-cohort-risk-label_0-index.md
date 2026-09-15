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

## Progress

- [x] C1–C3 (registry module, generator, plan stamping) — merged to `main`
  2026-09-15 (commit `7d5d4d3a`)
- [x] C4–C9 — merged to `main` 2026-09-15 (commit `9aa6f1c6`), via
  subagent-driven-development, one task-scoped review + fix loop per task,
  then a final whole-branch review that caught two Critical bugs no
  task-scoped review could see (see below), fixed in one wave and
  re-reviewed clean. Full suite green post-merge (3254 passed under load;
  the 8 transient failures under `-n4` all passed individually — parallel-
  worker contention, not a regression; `plan_manager.py`/`scan_run.py`
  auto-merged cleanly against v67's same-day landing on `main`, verified).

**Findings recorded 2026-09-15, full detail in the SDD ledger**
(`.superpowers/sdd/2026-09-14-v86-cohort-risk-label_2-features-surfaces/progress.md`,
deleted from the worktree at close-out per convention — this summary is
what survives):

1. C4's own reference code guessed two nonexistent attribute names
   (`item.target_confluence_count`, `scenario.level_price`) and a third
   field (`dist_to_level_atr`) turned out to be mathematically identical to
   `stop_width_atr` in this codebase (the confirming S/R level's price IS
   the stop price, no buffer) — dropped by human ruling rather than kept as
   a fake second discriminator.
2. C5's brief covered only `journal.py`'s read side; the write side
   (copying `plan.cohort_label`/`cohort_stats`/`risk_features` onto the
   trade record at all) didn't exist anywhere and had to be added,
   mirroring the existing `badge` parameter on `TradeLog.log_trade`.
3. C6's forward-only eligibility filter compared a full ISO timestamp
   (re-stamped on every journal write) against a bare date string, making
   every same-day entry unconditionally eligible; fixed to use the
   immutable `opened_at`, date-only.
4. **The final whole-branch review (the safety net a per-task review
   structurally cannot be) found two Critical bugs after all six tasks had
   individually passed review:** `cohort_line()`'s return value was
   appended as a bare string where `build_embed` expects a 3-tuple —
   crashing every Discord alert built from a real (non-`{}`-stats) v2 plan,
   since no per-task test had ever exercised a non-empty `cohort_stats`.
   And `scripts/backtest/emit_cohort_registry.py` (Part 1, C2) guessed
   field names against the live trade schema (`"CLOSED"` vs real lowercase
   statuses, `created_at` vs real `opened_at`, a nonexistent `r_realized`
   key) — meaning it could never actually count the live book. Both fixed;
   see the fix-wave commits between `c46273c3` and `3575c444` on the merged
   branch history for detail.
5. **`cohort_registry.json` does not exist yet.** C2 Step 5 (run the
   generator, commit the JSON) was never executed — deliberately: doing so
   sets the pre-registration's real freeze date, which is the human
   partner's call to time, not the agent's. Until it's generated, every
   plan reads `COHORT_UNKNOWN` and no alert ever shows a POOR/STRONG line.
   **This is the one remaining step before the feature does anything
   visible.** Run `scripts/backtest/emit_cohort_registry.py` (now fixed
   against the real schema) against real `data/trades.json` +
   `data/journal.json` + a confluence-replay JSON, verify its
   `pool_mean_r ≈ −0.136` sanity check, commit the JSON, and only then does
   the forward-only clock in the `backtest-methodology.md` pre-registration
   row start.
6. Per human-partner decision, `COHORT_POOR`'s alert copy no longer says
   "Reduced size, manual confirmation" (directive sizing advice on an
   unscored hypothesis) — replaced with neutral framing that states the
   numbers without telling the reader what to do with them.
