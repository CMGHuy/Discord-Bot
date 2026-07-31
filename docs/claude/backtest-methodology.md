# Backtest methodology (non-negotiable)

Referenced from the root `CLAUDE.md`. Read this before running or
interpreting any backtest, grid, or validation result.

- **Windows (widened by plan v8 Task V6, 2026-07-31):** TRAIN =
  1999-01-01..2023-12-31, VALIDATION = 2024-01-01..2025-12-31. The old TRAIN
  started 2020-01-01; every current parameter was therefore fitted on a
  bull-heavy 4-year window using a fraction of the ~25 years of daily history
  already on disk. Tune on TRAIN only. Validation is a **budget**: one
  pre-registered run per component, results recorded as-is, never retuned
  after — a config that fails train never gets a validation shot. Treat the
  2024–2025 window as tainted for any selection decision.
  **Mind the gap: `--train` in the scripts still means 2020-01-01.** Nine
  call sites hardcode `TRAIN = ("2020-01-01", "2023-12-31")`
  (`run_backtest_range.py`, `tune_strategy.py`, `tune_exit_v2.py`,
  `tune_confluence_gates.py`, `audit_quality_score.py`, `parity_exits.py`,
  `parity_sizing.py`, `swingbot/admin/jobs.py`, and a comment in
  `strategy_types.py`). Until plan v8 Task V46 reconciles them, pass
  `--from 1999-01-01 --to 2023-12-31` explicitly for any run meant to use
  the widened window — a bare `--train` silently gives you the old one.
- **Acceptance gate (replaced by plan v8 Task V6 — the old `win_rate >= 80`
  bar is VOID).** It was set when a "win" meant touching a ~0.85% target;
  under a 2.5% floor it is measuring a different event and cannot carry over.
  Pre-registered replacement, human-partner directive 2026-07-31 —
  **maximise win rate, not trade count**:

      OBJECTIVE   maximise win_rate
      SUBJECT TO  every win >= MIN_TARGET_PCT (2.5%)
                  expectancy_r > 0
                  scratches + timeouts <= 50% of closed trades
      STRETCH     win_rate >= 90%
      FLOOR       reject any config with expectancy_r <= 0 regardless of WR

  **Trade volume is explicitly NOT an objective.** A config producing 20
  trades at 85% WR beats one producing 400 at 60%. Do not tie-break on
  frequency. Unchanged mechanics: win = TP1 touched; win_rate over win+loss
  only; expectancy over all closed trades; same-bar conservative ordering
  (stop before target).
- **Sample size, and the honesty clause.** Proving WR > 90% at ~95% observed
  needs **N ≥ 59** (the G1 math already used in gatekeeper G95). Report
  Wilson lower bounds everywhere, never point estimates, and state N beside
  every rate — a 90% WR on N=12 is a hypothesis, not a finding; treat any
  cohort with N < 59 as provisional however good it looks. The 90% stretch
  and the 2.5% floor pull in **opposite directions**: measured from the live
  journal, every cohort reaches ~90% only at the tiny targets this work is
  removing (tier A: 90% at 0.35R, 53% at 1.25R), and tier A at 2.5% sits
  near 65% on an estimate that runs ~0.3R optimistic. The expected honest
  outcome is a small, highly selective cohort in the **65–80%** band at
  ≥2.5% wins with positive expectancy. So: **if the frontier tops out below
  90%, record the achieved number and stop.** Do not relax
  `MIN_TARGET_PCT`, re-cut cohorts post hoc, or drop losing trades from the
  denominator to reach a headline. An honest 72% at 2.5% is a result; a
  manufactured 90% is not.
- **Frozen constants:** `BREAKEVEN_TRIGGER_FRACTION = 0.5`, `tp1_fraction =
  0.50`. **Explicitly unfrozen by plan v8 Task V6:** `STRATEGY_RR_OVERRIDE`
  and the `RR_FLOOR = 0.30` floor. Rationale is live evidence, not
  preference — 479 closed paper trades over 26 days produced a 55.6% win
  rate against a **63.2%** breakeven requirement, because `TP1 = entry ±
  risk_distance × rr` with every override at 0.30–0.40 banks ~0.35R on a win
  while a loss costs the full 1R **by construction** (median designed target
  0.85% against a 2.19% median stop; cumulative −142.5%). These two are what
  produced that geometry, so they are what gets retuned. Note the knock-on:
  unfreezing rr invalidates the badge registry that the old 80%-WR
  validation underpinned — badges are stale until the registry is re-emitted.
- **No ML in the live path** — numpy/logistic audits live in `scripts/` only,
  never imported by `swingbot/`.
- Grid/validation results are written to `docs/superpowers/results/*.md` with
  the full table, the pre-registered selection rule quoted, and an honest
  observations section (failures are recorded, not fixed).
