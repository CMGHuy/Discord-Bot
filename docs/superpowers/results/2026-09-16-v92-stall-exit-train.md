# v92 Hypothesis 2 — MAE/time stall-exit — TRAIN comparison

Plan v92 Task 14. Single TRAIN-window flag-off-vs-flag-on comparison for
Hypothesis 2 (`STALL_EXIT_ENABLED`) — no grid, since `stall_exit_day` is
journal-derived (`optimal_time_stop_days`), not a tuned constant
(`scripts/backtest/measure_stall_exit.py`). Raw per-ticker log was written
to `docs/superpowers/results/2026-09-23-measure_stall_exit.log` during this
run for cross-checking at the time; not committed -- `.gitignore` excludes
`docs/superpowers/results/*.log`, so it does not persist past this
worktree.

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

Investigating why, two independent gaps stack, in this order of primacy:

**Gap 1 (primary) — the backtest harness never resolves `stall_exit_day` at
all.** `measure_stall_exit.py` calls `run_backtest` → `_trade_plan_at`
(`swingbot/core/backtesting/backtest.py:160`), which constructs its
`TradePlanV2(...)` inline at `backtest.py:326-337`. That construction
**never sets `stall_exit_day`**, so it takes the dataclass default `None`
unconditionally (`plan_types.py:82`) — for both arms, regardless of the
journal. `plan.stall_exit_day` is only ever *populated* at
`builders.py:210` (`plan.stall_exit_day =
plan_params._resolve_stall_exit_day(strategy)`), inside
`build_strategy_plan` — the live scan/plan-building path that Task 11
wired. `backtest.py` never imports `builders.py` or calls
`build_strategy_plan`/`_resolve_stall_exit_day` anywhere (a repo-wide grep
of `swingbot/core/backtesting/` confirms zero hits for either name). **This
is the exact same architecture gap already recorded elsewhere in
`docs/claude/backtest-methodology.md`'s closed-pre-registrations table, for
`DATA_DRIVEN_STOPS_ENABLED`**:
*"it reached `build_strategy_plan` but the backtest sized through
`_trade_plan_at`, so it was unmeasurable by construction"* — same trap,
different flag. Because of this gap alone, `plan.stall_exit_day` is
`None` for every backtest-measured trade in this script's output, and the
journal question below never even gets reached.

**Gap 2 (secondary, and separately real) — even if Gap 1 were fixed, the
journal itself couldn't supply a value.** The stall-exit path resolves its
trigger day via `_resolve_stall_exit_day` → `optimal_time_stop_days(
_journal_entries(), strategy)` (`swingbot/core/edge/stops.py`). That
function requires `MIN_SAMPLE=40` journal entries per strategy with a
non-`None` `days_to_half_r` field, or it returns `None` for that strategy.
Direct inspection of the production journal (`data/journal.json` in the
main repo, 182 real entries, 107 wins): **`days_to_half_r` is absent from
every single entry's schema** — it is not one of the fields ever recorded.
A repo-wide grep for `days_to_half_r` (via the `.ignore`-respecting Grep
tool) turns up exactly 3 files: `swingbot/core/edge/stops.py` (the
consumer, `optimal_time_stop_days` itself), `tests/edge/test_edge_stops.py`
(synthetic test fixtures only — not a real journal), and the old
`v4-edge-engine` implemented plan doc. **Nothing in the journal-writing
path** (`swingbot/core/analytics/journal.py`, `builders.py`, or anywhere
else) **ever populates this field**, so `optimal_time_stop_days()` would
return `None` for every strategy even in the live scan/plan-building path
that does call `_resolve_stall_exit_day`.

**Net effect:** the journal's missing `days_to_half_r` field is a real,
separate problem, but it isn't even reached — `measure_stall_exit.py`'s two
arms are byte-identical primarily because the backtest harness never
resolves `stall_exit_day` at all (Gap 1), before the journal question (Gap
2) even comes up. Even a fully-populated journal would not change this
script's output by one trade. `plan.stall_exit_day` can therefore never be
non-`None` in a backtest-measured trade, so the stall-exit mechanism cannot
fire in TRAIN, VALIDATION, or backtest, **independent of
`STALL_EXIT_ENABLED`'s value and independent of the journal's content**. It
would still be reachable in *live* scanning (which does go through
`build_strategy_plan`) if Gap 2 alone were fixed — but that path is not
what this script, or any TRAIN/VALIDATION measurement, exercises.

This was surfaced to the human partner as a premise-level problem (not a
ruling to make unilaterally), who decided on 2026-09-23 to close the
hypothesis here rather than fix either gap as part of this plan.

**Win→non-win outcome-flip disclosure (spec §3):** not measured. The
baseline and component arms are byte-identical (Gap 1 above), so there are
no differing trades between them to compare for a win→non-win flip in
either direction.

## Caveats -- latent semantic gaps while the flag is off

Not gating (the hypothesis is already closed above as unmeasurable by
construction), but recorded honestly for whoever next reads this flag's
spec, since none of these are reachable while `STALL_EXIT_ENABLED` and the
harness gap both stay as they are today:

- **"Has not yet reached +0.5R" is implemented as a point-in-time check, not
  a high-water-mark check.** The spec's plainer reading ("has not yet
  reached +0.5R") would naturally mean "never reached +0.5R at any point
  since entry." The actual implementation (both `exit_sim.py`'s
  `_scale_out_exit_walk` and `plan_manager.py`'s live-poll block) checks
  `current_r < 0.5` at the moment the stall check fires -- a trade that
  touched +0.8R and slipped back to +0.3R by the check bar would still be
  exited by the current code. This is a real semantic gap from the spec's
  plainer reading, not an implementation bug per se, but worth knowing
  before this mechanism is ever reopened.
- **Live and backtest can disagree by up to one bar/one intraday move.**
  The live poll path (`plan_manager.py`) evaluates the stall condition
  against the current intraday price the instant `days_held >
  stall_exit_day` becomes true; the backtest walk (`exit_sim.py`) decides
  at each bar's CLOSE. A trade could stall-exit on different information
  in the two paths for the same calendar day.
- **Only strategy-source plans ever get `stall_exit_day` populated.**
  `builders.py:210`'s `build_strategy_plan` is the only writer of
  `plan.stall_exit_day` (via `_resolve_stall_exit_day`);
  `build_confluence_plan` never sets it, so it stays `None` for every
  confluence-sourced plan regardless of the flag. Per this repo's own live-
  book numbers (`prod-live-book-2026-09-10`), roughly 80% of the live book
  is confluence-sourced -- so even if both gaps above were fixed and this
  hypothesis reopened and passed, the mechanism would only ever apply to a
  minority of live plans as currently wired.

## Verdict

**Hypothesis 2 (MAE/time stall-exit) closes here as unmeasurable by
construction — Tasks 15 (Stage 2 walk-forward folds) and 16 (Stage 3
VALIDATION shot) are not run; VALIDATION's one-shot budget for this
hypothesis is preserved unspent.** `STALL_EXIT_ENABLED` stays default
`false` — ships inert. Decided by the human partner on 2026-09-23 after this
investigation was surfaced to them. Distinct from a genuine TRAIN failure
(contrast with Hypothesis 1's Task 7 result, which was a real measured
null) — reopening this hypothesis needs **both** gaps closed: (a) wiring
`backtest.py`'s `_trade_plan_at`/`TradePlanV2` construction to call
`_resolve_stall_exit_day` (or otherwise route backtest-constructed plans
through `builders.py`'s `build_strategy_plan`), **and** (b) journal-writing
fixed to actually record `days_to_half_r`. Both are new, separate scope, not
part of v92.
