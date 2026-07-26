# Backtest methodology (non-negotiable)

Referenced from the root `CLAUDE.md`. Read this before running or
interpreting any backtest, grid, or validation result.

- **Windows:** TRAIN = 2020-01-01..2023-12-31, VALIDATION = 2024-01-01..2025-12-31.
  Tune on TRAIN only. Validation is a **budget**: one pre-registered run per
  component, results recorded as-is, never retuned after — a config that fails
  train never gets a validation shot. Treat the 2024–2025 window as tainted
  for any selection decision.
- **Acceptance gates:** `win_rate >= 80`, `expectancy_r > 0`, `N >= 30`
  (train) / `N >= 15` (validation), scratches+timeouts ≤ 50% of closed trades.
  Win = TP1 touched; win_rate over win+loss only; expectancy over all closed
  trades; same-bar conservative ordering (stop before target).
- Frozen constants: `STRATEGY_RR_OVERRIDE` + the 0.30 R:R floor,
  `BREAKEVEN_TRIGGER_FRACTION = 0.5`, `tp1_fraction = 0.50`.
- **No ML in the live path** — numpy/logistic audits live in `scripts/` only,
  never imported by `swingbot/`.
- Grid/validation results are written to `docs/superpowers/results/*.md` with
  the full table, the pre-registered selection rule quoted, and an honest
  observations section (failures are recorded, not fixed).
