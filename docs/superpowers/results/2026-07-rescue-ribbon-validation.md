# MA Ribbon rescue gate — VALIDATION (Task 103)

## Outcome: no validation run — permanent WEAK

Task 102's TRAIN grid (`docs/superpowers/results/2026-07-rescue-ribbon-train.md`)
found **0/6** `(min_width_pctile, require_expanding)` configs qualifying
under the pre-registered rule (`win_rate>=80, expectancy_r>0, n_eval>=30,
excluded_share<=0.5`). Per the plan's pre-registered rescue policy, a
strategy that does not clear TRAIN does not get a validation-window look —
the one-look budget per rescue exists to confirm a real candidate
out-of-sample, not to re-test something already rejected.

Consequently:

- **No run** of `scripts/run_backtest_range.py --validation` was made for
  MA Ribbon under this rescue.
- **No change** to `swingbot/core/entry_filters.py`'s `DEFAULT_PARAMS["MA
  Ribbon"]` — it remains `ext_pct=8.0, min_width_pctile=None,
  require_expanding=False` (gate present but off, as shipped in Task 101).
- **No change** to `swingbot/core/validation_registry.json` — MA Ribbon's
  existing `WEAK` record (from round 1) stands unmodified.
- **No change** needed in `tests/test_registry.py` — it carries no MA
  Ribbon-specific assertion (checked: only `Fibonacci` VALIDATED and `RSI`
  WEAK are asserted by name; `test_all_eleven_strategies_present` just
  counts strategies present, unaffected either way).

**MA Ribbon stays WEAK, permanently, under this rescue attempt** — the
expansion gate explored in Tasks 101-102 does not rescue it. This is the
honest, pre-registered outcome of a gate that failed to clear TRAIN, not an
oversight or a skipped step.
