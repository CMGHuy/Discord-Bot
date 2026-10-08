# v129 — Acceptance-failure exits: pre-registration

Written before any measurement. Spec: `docs/superpowers/specs/implemented/2026-10-03-v129-acceptance-failure-exits-design.md`.
Gate: the v92 harvest gate (`acceptance_harvest.evaluate_harvest`). The v72 funnel is not used: this is an exit-only (`Edge: harvest`) change.

## Claim
Judging a level-leaning trade by acceptance (a daily close beyond its level)
rather than by an intrabar touch raises per-trade expectancy, under the v92
harvest gate, on the same entries.

## Arms and grids (two independent populations; a pass in one never carries the other)
- Arm Z: confluence plans. Intrabar stop moves to the disaster stop `max(level − m·ATR14, entry·0.98)` (bearish mirrored); close exit strictly beyond `level ∓ b·ATR14`. 1R = entry → disaster stop. Grid `m ∈ {0.5, 1.0, 1.5}` × `b ∈ {0, 0.25}`.
- Arm B: Break & Retest plans. Stop unchanged; close exit strictly beyond the broken level `∓ b·ATR14`. Grid `b ∈ {0, 0.25}`.
- `level` and ATR14 are frozen at the plan's creating bar.

## Population and instrument
- Universe: every ticker with a cached CSV in the main tree's `data/backtest_cache` (`BACKTEST_CACHE_DIR`), all `LEGACY_HORIZONS`, `scale_out=True`. Amended 2026-10-08, before any run: the watchlist is in Postgres and unreachable from the worktree, so the driver lists the cache directory (`cache_universe()`) instead of `measure_arms.cached_universe()`. Partner-approved.
- Arm Z entries: `replay_scenarios` with live `ScanParams`. Arm B entries: the plans `run_backtest("Break & Retest", exit_model="v2", scale_out=True, tp2_mode="levels")` builds.
- Entries are built once with `ACCEPTANCE_EXIT_ENABLED` off and re-simulated per cell (`acceptance_replay`), so the design is paired.
- A not-eligible arm Z plan (level beyond the 2% cap, or on the profit side of entry) keeps today's exit in both arms and stays in the population.
- A stop hit books −1.0R in both arms, gaps included.
- The disaster stop is capped at exactly 2% of entry (not the 1.75% live clamp); the difference is a pre-flip question, not part of this test.

## Windows
TRAIN 2020-01-01..2023-12-31. VALIDATION 2024-01-01..2025-12-31, one shot per arm.

## Stages (constants frozen in `acceptance_exit_funnel.py`)
- Stage 0: paired MDE (`mde_expectancy_r_paired`, power 0.80), `target_n` projected from TRAIN closed N over 1460 → 730 days. Any cell's MDE above +0.10R, or undefined, closes the arm `UNDERPOWERED`.
- Stage 1: a cell is eligible when `expectancy_gain`, `win_rate_floor` (−2.0pp) and `volume` all pass on TRAIN. Selected = the eligible cell with the highest lower-95% ΔExpR whose grid neighbours (±1 step in m or b; arm B: the other cell) are all eligible. Tie → the earlier cell in grid order. No such cell → `NO_ELIGIBLE_CELL`.
- Stage 2: four TRAIN calendar-year folds (2020–2023) for the selected cell. FAIL when more than half of the measurable folds have ΔExpR < 0, or none is measurable.
- Stage 3: one VALIDATION replay of the selected cell only. All four harvest clauses. `not_luck` = per-ticker arm-label swap on ΔExpR, n = 200, seed 42, p < 0.05.

## Disclosures (reported, never gating)
ΔWR, N, outcome flips both ways, exit mix by reason, planned-RR shift, arm Z not-eligible count and gap-through count, per-horizon N, entries only one arm triggered.

## On a pass
The arm's result is recorded and the float defaults are set to the selected cell. `ACCEPTANCE_EXIT_ENABLED` is **not** flipped by this plan: live exits run through `plan_manager`, which has no close exit yet (plan index, Spec correction 6). The flip is the partner's call.

## On a fail
A row in "Closed pre-registrations — do not re-run these". Never re-run as specified.
