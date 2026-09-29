# v108 — EMA Crossover re-arm: more pullback entries per cross

**Version:** ui 1.21.0 · bot 1.10.3 (at writing)
**Bump:** none until wiring; bot minor if a K > 1 ships (alert stream gains entries, badge flips)
**Edge:** volume
**Status:** Closed no-lift at Stage 1 (both directions) 2026-09-29; VALIDATION spent: none. Phase A code (inert, K=1 default) merged to `main` at `53fc7c09`.

## Why this, and the honest prior

**Goal (the partner's words, 2026-09-27):** save the `WEAK` strategy easiest
to bring back to `VALIDATED`. EMA Crossover was chosen because its only
failure is sample size, not direction.

**Diagnosis.** v84 re-measured the unchanged pullback mechanism under current
arithmetic (`results/2026-09-10-v84-ema-crossover-preregistration.md`, TRAIN
2020–2023, 77-name universe, `--exit-model v2 --scale-out`): pooled N=55,
WR 61.8%, ExpR +0.494 — every badge clause clears. Fold stability failed on
the N floor alone:

| Fold year | N | WR | ExpR |
|---|---|---|---|
| 2021 | 13 | 53.8% | +0.346 |
| 2022 | 16 | 75.0% | +0.747 |
| 2023 | 13 | 53.8% | +0.513 |

No year is negative. The strategy is starved, not broken.

**Where the starvation comes from.** `ema_cross_entries`
(`swingbot/core/market/entry_filters.py`) in `entry_mode="pullback"` keeps
only the **first** fast-EMA touch inside the 15-bar window after a held
cross (`_first_touch_after`, `break` after the first hit). Later touches in
the same trend leg are discarded before the ten ANDed filters even see them.

**Why this is a new mechanism, not a re-run.** v84 closed the row with
"reopening needs a genuinely new mechanism", and
`docs/claude/backtest-methodology.md` states a better instrument "does not
reopen any closed row". Changing *which bars can be entries* is a change to
the signal, not to the instrument. The extended 2010–2023 history is the
instrument only; see the honesty clause.

**Prior.** Moderate. `one_at_a_time=True` suppresses any touch that lands
while the first trade is still open, so the lift is bounded by how often a
trade closes inside the 15-bar window. Stage 0 measures this for free before
any badge clause is scored. Second touches may also be lower quality — the
Stage 1 plateau is what catches that.

## Mechanism

- Two new params in `DEFAULT_PARAMS["EMA Crossover"]`, `max_touches_bull`
  and `max_touches_bear`, both default **`1`**, which must reproduce today's
  entries bit-for-bit (ships inert). Per-direction so each direction's
  verdict maps straight onto its own knob; the harness sets only the
  scored direction's param.
- `_first_touch_after` generalises to "the first K **touch
  events** inside the `pullback_max_bars` window after each held cross". A
  touch event is a bar satisfying the existing touch mask whose previous bar
  did not — a run of consecutive touching bars is one event, so a three-bar
  dip is one entry, not three.
- Unchanged: `pullback_max_bars=15` (that axis was tuned in round 2 and is
  closed), all ten ANDed filters, the stop/target arithmetic, the absence of a
  `STRATEGY_GATES` entry.
- No cooldown knob: `one_at_a_time` already forbids overlapping trades.
- No-lookahead: a touch event at bar `j` reads bars `<= j` only (the cross at
  `ci < j`, the touch mask at `j` and `j-1`).

## Instrument (reuse v103's harness)

Added as mechanism `E` in `scripts/backtest/measure_fib_v103.py`'s
`MECHANISMS` table through `_param_value("EMA Crossover",
"max_touches_<dir>", K)` for the direction being scored;
`scripts/backtest/fib_funnel.py`'s stage logic is reused unchanged. Every
constant below is v103's (`results/2026-09-25-v103-preregistration.md`).

- `TRAIN_EXT = 2010-01-01..2023-12-31`, extended cache
  `data/backtest_cache_ext`, `BACKTEST_CACHE_DIR` set on every run.
- Universe: the 77-name production watchlist passed via `--tickers` (a
  worktree's own watchlist is a 3-ticker fixture), 73 after the liquidity
  filter; the run reports `universe_n` and a run with any other count is
  discarded.
- Arithmetic: `exit_model="v2"`, `scale_out=True`, `tp2_mode="levels"`,
  `frictions=True`, `one_at_a_time=True`, level lifecycle as today. All ten
  horizons pooled. Directions scored separately, each as live today (EMA
  Crossover has no direction mask).
- **Grid:** `K ∈ {2, 3}`; **reference** `K = 1`, reported but never
  eligible to win.

### Stage 0 (free)

Per direction, a direction closes with budget intact if either:

1. the loosest cell (`K=3`) has TRAIN_EXT N < 30 (`MIN_N_TRAIN`); or
2. **mechanism inert:** `K=3` produces fewer than **1.15×** the `K=1`
   signal count (`count_signals`) — re-arm adds too little to change the
   fold picture.

### Stage 1 (TRAIN_EXT, plateau)

Tier 1 (badge tier: WR ≥ 50, ExpR > 0, N ≥ 30, scratch+timeout share ≤ 0.5)
and Tier 2 (ExpR > 0 and ticker-cluster bootstrap lower bound > 0, same
floors) exactly as v103. A cell counts only if it and every grid neighbour
pass the same tier. Winner: highest-ExpR Tier 1 plateau cell, else highest
Tier 2, else none.

**Only a Tier 1 winner can earn `VALIDATED`.** A Tier 2-only winner still
runs Stages 2–3; if it passes, its K ships live (a positive-expectancy
volume gain) but the badge stays `WEAK`.

### Stage 2 (11 anchored folds, 2013–2023)

Per fold Y, re-select the highest-ExpR grid cell (K ∈ {2,3}) on 2010..Y-1
among cells with N ≥ 30; score it on year Y. Clears when ≥ 3 folds have test
N ≥ 15 and ≥ 2/3 of those have ExpR > 0. Unselected folds are counted in the
report.

### Stage 3 (one VALIDATION shot)

Only for a direction with a Stage 1 winner **and** a Stage 2 clear.
`VALIDATION = 2024-01-01..2025-12-31`, scored on the tier Stage 1 assigned,
N ≥ 15. One shot per direction; the result is recorded as-is.

## Honesty clause

- **`K=1` cannot win.** `K=1` on TRAIN_EXT is the unchanged v84 mechanism on
  a longer window. It is the reference arm only. If `K=1` would clear and no
  `K>1` cell does, the verdict is NO-LIFT.
- The 2026-07 VALIDATION read of the pullback entry (N=36, WR 75.0%, scored
  under the deleted fixed reward:risk table) is not consulted for any choice.
- No threshold, grid value or window changes after the pre-registration
  commit. The pre-registration is written and committed **before** the
  first `collect` run.

## Outcomes

- **Tier 1 PASS (Stage 2 clears, VALIDATION passes) in a direction:** set
  that direction's `max_touches_<dir>` to its winning K, re-emit the
  registry row as `VALIDATED` with its `run_date`, release as `bot minor`.
  The other direction keeps whatever its own verdict earned.
- **Tier 2 PASS in a direction:** set that direction's K as above; badge
  stays `WEAK`; `bot minor`.
- **Any other outcome:** both params stay `1` (inert code on `main`),
  EMA Crossover stays `WEAK`, a closed-pre-registration row is added to
  `docs/claude/backtest-methodology.md`, and the spec/plan move to
  `implemented/` (inert code landed) per `document-lifecycle.md`.

## Live-path risk (wiring task only)

With K > 1 live, a second pullback in the same leg posts a second alert. The
partner places real resting orders off alerts
(`docs/claude/edge-priorities.md`), so the wiring task must confirm the live
scan's duplicate/open-position suppression for the same ticker and strategy
behaves as `one_at_a_time` did in the backtest — otherwise the live
population differs from the measured one.

## Testing

- `max_touches_bull = max_touches_bear = 1` parity: entries identical to today's on a fixture frame
  covering several crosses.
- Touch-event counting: consecutive touching bars count once; K caps the
  count; touches past `pullback_max_bars` are ignored; a new cross resets.
- No-lookahead: truncating the frame at any bar leaves every earlier entry
  unchanged.
- Harness: mechanism `E` wiring (cell context restores the param; `K=1`
  excluded from winner selection).

## Parallelisation

- **Group 1 (parallel):** the entry-filter change + its tests
  (`entry_filters.py`, `tests/…entry…`) and the harness wiring + its tests
  (`measure_fib_v103.py`, `tests/scripts/…`) — disjoint files; the harness
  only needs the param *names* `max_touches_bull`/`max_touches_bear`, fixed
  by this spec.
- **Sequential:** pre-registration commit after Group 1 and before any
  measurement; Stage 0 → Stage 1/2 → Stage 3 strictly in order (each gates
  the next); wiring/close-out after the verdict; full suite once, last.
