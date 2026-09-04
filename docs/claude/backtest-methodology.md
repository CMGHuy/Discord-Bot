# Backtest methodology (non-negotiable)

Referenced from the root `CLAUDE.md`. Read this before running or
interpreting any backtest, grid, or validation result.

- **Windows:** TRAIN = 2020-01-01..2023-12-31, VALIDATION = 2024-01-01..2025-12-31.
  Tune on TRAIN only. Validation is a **budget**: one pre-registered run per
  component, results recorded as-is, never retuned after — a config that fails
  train never gets a validation shot. Treat the 2024–2025 window as tainted
  for any selection decision.
- **Acceptance gates:** `win_rate >= 50`, `expectancy_r > 0`, `N >= 30`
  (train) / `N >= 15` (validation), scratches+timeouts ≤ 50% of closed trades.
  Win = TP1 touched; win_rate over win+loss only; expectancy over all closed
  trades; same-bar conservative ordering (stop before target). The win-rate
  floor was 80 before plan v31 (2026-08-17,
  `results/2026-08-17-structural-target-train.md`) — that number was
  calibrated to the fixed per-strategy reward:risk arithmetic v31 deleted
  (break-even win rate at reward:risk ratio X is `1/(1+X)`; at the old fixed
  0.30 floor that's 76.9%, which is why 80% was the bar). Every live plan
  now prices its target against the `MIN_RISK_REWARD_RATIO`/
  `MAX_RISK_REWARD_RATIO` band below, not a fixed ratio, so break-even
  moved with it: `1/(1+1.5) = 40%` at the band's floor, `1/(1+2.5) =
  28.6%` at its cap. 50% is a margin over the 40% floor-case break-even,
  the same way 80% was a margin over the old 76.9% — **do not restore 80%
  for any run against the current engine.**
- Frozen constants: `MIN_RISK_REWARD_RATIO = 1.5` / `MAX_RISK_REWARD_RATIO
  = 2.5` (the band `plan_engine.select_structural_target` picks every
  plan's target inside — replaces the pre-v31 per-strategy fixed
  reward:risk override table and its 0.30 floor, both deleted),
  `BREAKEVEN_TRIGGER_FRACTION = 0.5`, `tp1_fraction = 0.50`.
- **Evidence age.** Every registry row's `run_date` yields a read-time decay
  verdict (`registry.decay_for`): `fresh`, `aging` at 90 days, `stale` at 180
  days, `unknown` when the row carries no usable date — fail-closed, an
  unstamped row is never `fresh`. 90/180 are one and two missed quarterly
  re-verification cycles, not round numbers picked for feel. The verdict is
  **derived at read time and never persisted** (a stored verdict is wrong the
  day after it is written; only the raw `run_date` travels), and **it gates
  nothing** — no plan refused, no alert suppressed, no badge downgraded.
  Excluding stale evidence would change which plans get built, which needs its
  own pre-registered hypothesis. The Fibonacci / RSI / Support-Resistance
  footnote in the v31 row below still stands on its own: decay says a row is
  old, not that its arithmetic was deleted. Those are different facts.
- **Registry emit hard gates.** `run_backtest_range.py --emit-registry` writes
  **no row** for an unhealthy cell rather than one that looks like evidence,
  printing a stable token to stderr so the sweep's log records why a cell is
  missing: `hard-gate:zero-trades`, `hard-gate:below-min-n`,
  `hard-gate:nonfinite-metric`, `hard-gate:missing-window`. Refusal is per-row —
  one bad cell never discards the healthy cells beside it — and a refused cell
  is recovered by re-running it, never by hand-editing the JSON.
- **No ML in the live path** — numpy/logistic audits live in `scripts/` only,
  never imported by `swingbot/`.
- Grid/validation results are written to `docs/superpowers/results/*.md` with
  the full table, the pre-registered selection rule quoted, and an honest
  observations section (failures are recorded, not fixed).
- **A negative result closes a component; it does not re-open it.** "No
  configuration cleared the rule" is a finished measurement, and the empty
  table it produces is the answer — not a stub, not unfinished work. Re-running
  the same question with looser thresholds is the exact failure the one-shot
  budget exists to prevent. Reopening one needs a *new* pre-registered
  hypothesis and its own shot, never a re-read of the old table.

### Closed pre-registrations — do not re-run these

| Component | Outcome | Record |
|---|---|---|
| `REGIME_ALLOW` regime gate (v17 P2a) | **No gate justified** — 0 of 44 cells cleared the rule on TRAIN, so `strategy_types.REGIME_ALLOW` stays `{}` and `REGIME_GATES_ENABLED` stays off | `results/2026-08-08-regime-allow-train.md`, commit `95f5668` |
| `DATA_DRIVEN_STOPS_ENABLED` (edge-engine v4) | Scored 0.0000 and burned its shot — it reached `build_strategy_plan` but the backtest sized through `_trade_plan_at`, so it was unmeasurable by construction | v17 spec §7.1 |
| Level-lifecycle targets (v17 P1) | Inert; **stops** passed the fold gate and shipped default-on | `results/2026-08-08-level-lifecycle-stops-validation.md`, commit `6451d2c` |
| `RS_GATE` relative-strength gate (v34) | **PASS, and narrower than the plan asked for.** A symmetric gate was dead on TRAIN at every threshold in the grid; the bullish arm was negative at every threshold and ships disabled (`RS_LEADER_PERCENTILE=0`). The bearish-only arm at `RS_LAGGARD_PERCENTILE=25` on `rs_combined` cleared VALIDATION: 48.50% → 49.66% (+1.17pp) for a 4.07% alert-volume cut, **overlapping** intervals, so it is on by default but is not a demonstrated edge. 75.3% of the bearish population is RSI Divergence. Measured with a purpose-built instrument (`scripts/backtest/measure_rs_gate_effect.py`), **not** `run_backtest_range.py` — the replay harness never calls `scanning/engine.py` and cannot see this gate | `plans/implemented/v34-train-preregistration.md` (TRAIN grid + the appended VALIDATION result) |
| Structural target selection, strategy-source badges (v31) | TRAIN: 4 of 11 strategies had a qualifying (strategy, horizon) cell (Break & Retest, MACD, VWAP, Volume Profile). VALIDATION (pooled per strategy): **2 of 4 passed** — MACD and Volume Profile stay/become `VALIDATED`; Break & Retest and VWAP flip from their pre-v31 `VALIDATED` badge to `WEAK`. The other 7 strategies got no shot. Fibonacci/RSI/Support-Resistance keep a pre-v31 `VALIDATED` badge that now describes deleted arithmetic — flagged, not resolved, by this shot (see the results doc) | `results/2026-08-17-structural-target-train.md`, `results/2026-08-17-structural-target-validation.md` |
| `AVWAP_LEVELS_ENABLED` (v35) | **PASS on non-inferiority, budget spent (two shots).** First shot (E33, 2026-07-26) FAILED an improvement gate (pooled -0.0001R, 0 of 3 folds). v35 earned a fresh shot only because the component itself changed (52-week extreme anchors); its one-shot VALIDATION cleared all three pre-registered clauses — win rate -0.084pp (inside the 0.50pp non-inferiority margin), confluence-count delta +0.4854 (< +0.500 guard), trade count -0.04% — with heavily overlapping Wilson intervals. Default flipped `false` → `true`. **On because it degrades nothing, NOT because an edge was measured.** Do not re-run; reopening needs a genuinely new mechanism | `docs/superpowers/plans/implemented/v35-avwap-preregistration.md` |
| `LEVEL_TOUCH_STRENGTH` (v36) | **No lift, VALIDATION deliberately not spent, NOT merged to `main`.** TRAIN (15 tickers × 5 horizons, 550 evaluated trades): the strength-based target-selection tiebreak was byte-identical to baseline (its precondition — two candidates tied within 5% on the confluence path, both touch-graded — never occurred in this sample), and the confidence factor measured net negative (win rate 37.09%→36.32%, expectancy 0.0670R→0.0057R, alert volume −62.9%, past the plan's own 30% ceiling). Tasks 1–5's code was fully built and tested but, showing no benefit, was left on its worktree branch rather than landed inert — filed under `plans/no-lift/`, not `plans/implemented/` | `results/2026-08-22-level-touch-strength-train.md`, branch `worktree-2026-08-16-v36-level-touch-strength` |
| `EFFECTIVE_CONFLUENCE_ENABLED` (v49) | **Degenerate, VALIDATION deliberately NOT spent, NOT merged to `main`.** The measurement itself succeeded and confirmed the premise: 707,655 candidate prices over TRAIN 2020-2023 give an off-diagonal redundancy mean of 0.628 (Bollinger/Donchian 0.887, Fibonacci/Zigzag 0.838, EMA/VWAP/AVWAP 0.79-0.83; Rolling S/R the lone near-independent family at 0.235). But the participation-ratio reduction saturates below the gate: across **all 4,095 non-empty family subsets** `effective_count_int` returns **1**, max reachable `N_eff` being 1.746 against a pre-registered FLOOR. With `MIN_TARGET_CONFLUENCE_COUNT=2` the flag-on arm rejects every scenario, so both Phase 4 TRAIN cells yield zero alerts and VALIDATION clauses 3 (`N>=15`) and 4 (alert reduction `<=25%`) fail by construction. **The one-shot budget was not spent and remains available.** Do not re-run this as specified; floor->ceil, matrix rescaling or `MIN=1` are each a NEW hypothesis needing a NEW pre-registration | `results/2026-08-23-v49-confluence-redundancy.md`, `plans/no-lift/2026-08-22-v49-effective-confluence.md`, branch `worktree-2026-08-22-v49-effective-confluence` |
| `DEAD_CAT_BOUNCE_VETO` (v68) | **TRAIN passed (weak evidence), VALIDATION FAILED, budget spent, merged inert.** TRAIN (25 tickers x 5 horizons, one replay pass, 12 cells scored against it): `d15_gN_voff` (decline_pct=15, gap_required=False, volume_ratio=off) had the greatest pooled ExpR improvement (+0.0104R) among cells clearing N>=30 and alert-cut<=30% — but the mechanism was suspect (every axis improved toward *looser*, the gap-required arm net-negative at every decline threshold). VALIDATION on that one cell: WR 34.5% (<50 floor), ExpR delta **-0.0097R — opposite sign from TRAIN**. 2 of 4 gates failed. Default stays `false`; code ships merged and inert. Do not re-run this grid/rule; a genuinely different mechanism needs a new pre-registration | `results/2026-08-30-v68-dcb-veto-train.md`, `results/2026-08-30-v68-dcb-veto-validation.md` |
