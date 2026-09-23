# v92 Hypothesis 2 — MAE/time stall-exit — TRAIN comparison

Plan v92 Task 14. Single TRAIN-window flag-off-vs-flag-on comparison for
Hypothesis 2 (`STALL_EXIT_ENABLED`) — no grid, since `stall_exit_day` is
journal-derived (`optimal_time_stop_days`), not a tuned constant
(`scripts/backtest/measure_stall_exit.py`). Raw per-ticker log archived at
`docs/superpowers/results/2026-09-23-measure_stall_exit.log`.

## Setup

- **Window:** TRAIN 2020-01-01..2023-12-31.
- **Tickers:** full 77-symbol watchlist.
- **Horizons x strategies:** all 10 horizons (`2w`…`9m`) x all 11
  `ALL_STRATEGIES`, `exit_model="v2"`, `scale_out=True` throughout — the
  stall-exit resolver only applies in that exit path.
- **Wall-clock:** 23.1 min (2 passes: baseline + component). Exit 0, no
  errors.

## Result

```
Baseline (flag off), 77 tickers...
  4258 closed trades
Stage 0 MDE (ExpR, target_n=4258): +0.2409R
Component (flag on), 77 tickers...
  4258 closed trades
  expectancy_gain: FAIL -- dExpR +0.0000R [+0.0000,+0.0000] p=1.0000
  win_rate_floor: PASS -- standardised dWR +0.00pp, lower bound +0.00pp vs floor -2.00pp
  volume: PASS -- alert cut +0.00% vs max 25.0% (4258 -> 4258)
  permutation: SKIPPED -- not required at stage 'walkforward'
OVERALL: FAIL
```

## Root cause — this is not a measured negative result

The baseline and component arms are **byte-identical**: same N (4258 =
4258), `dExpR` exactly `+0.0000R`, a zero-width confidence interval
(`[+0.0000,+0.0000]`), and `p=1.0000`. A real negative result (like
Hypothesis 1's Task 7 grid) shows non-trivial deltas that simply don't clear
the bar. A zero-width, byte-identical comparison means the mechanism under
test **never fired in either arm** — the flag toggle had no observable
effect on a single trade, in either direction. `OVERALL: FAIL` is therefore
misleading taken at face value: it reads as "measured, no lift" when the
correct reading is "not measured at all."

Investigating why:

- The stall-exit path resolves its trigger day via
  `_resolve_stall_exit_day` → `optimal_time_stop_days(_journal_entries(),
  strategy)` (`swingbot/core/edge/stops.py`). That function requires
  `MIN_SAMPLE=40` journal entries per strategy with a non-`None`
  `days_to_half_r` field, or it returns `None` for that strategy.
- Direct inspection of the production journal (`data/journal.json` in the
  main repo, 182 real entries, 107 wins): **`days_to_half_r` is absent from
  every single entry's schema** — it is not one of the fields ever recorded.
- A repo-wide grep for `days_to_half_r` (via the `.ignore`-respecting Grep
  tool) turns up exactly 3 files: `swingbot/core/edge/stops.py` (the
  consumer, `optimal_time_stop_days` itself), `tests/edge/test_edge_stops.py`
  (synthetic test fixtures only — not a real journal), and the old
  `v4-edge-engine` implemented plan doc. **Nothing in the journal-writing
  path** (`swingbot/core/analytics/journal.py`, `builders.py`, or anywhere
  else) **ever populates this field.**
- Conclusion: `optimal_time_stop_days()` returns `None` for every strategy,
  always — not just in this worktree's backtest replay, in the live
  production journal too. `plan.stall_exit_day` can therefore never be
  non-`None`, so the stall-exit mechanism cannot fire in TRAIN, VALIDATION,
  backtest, or live, **independent of `STALL_EXIT_ENABLED`'s value**. The
  flag toggling between the two arms above changed nothing because there was
  never a resolvable `stall_exit_day` for it to act on.

This was surfaced to the human partner as a premise-level problem (not a
ruling to make unilaterally), who decided on 2026-09-23 to close the
hypothesis here rather than fix journal-writing as part of this plan.

## Verdict

**Hypothesis 2 (MAE/time stall-exit) closes here as unmeasurable by
construction — Tasks 15 (Stage 2 walk-forward folds) and 16 (Stage 3
VALIDATION shot) are not run; VALIDATION's one-shot budget for this
hypothesis is preserved unspent.** `STALL_EXIT_ENABLED` stays default
`false` — ships inert. Decided by the human partner on 2026-09-23 after this
investigation was surfaced to them. Distinct from a genuine TRAIN failure
(contrast with Hypothesis 1's Task 7 result, which was a real measured
null) — reopening this hypothesis requires fixing journal-writing to
actually record `days_to_half_r`, which is new, separate scope, not part of
v92.
