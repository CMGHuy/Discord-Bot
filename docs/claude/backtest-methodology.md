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
| Structural target selection, strategy-source badges (v31) | TRAIN: 4 of 11 strategies had a qualifying (strategy, horizon) cell (Break & Retest, MACD, VWAP, Volume Profile). VALIDATION (pooled per strategy): **2 of 4 passed** — MACD and Volume Profile stay/become `VALIDATED`; Break & Retest and VWAP flip from their pre-v31 `VALIDATED` badge to `WEAK`. The other 7 strategies got no shot. Fibonacci/RSI/Support-Resistance keep a pre-v31 `VALIDATED` badge that now describes deleted arithmetic — flagged, not resolved, by this shot (see the results doc) | `results/2026-08-17-structural-target-train.md`, `results/2026-08-17-structural-target-validation.md` |
