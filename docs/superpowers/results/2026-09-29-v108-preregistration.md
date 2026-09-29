# v108 pre-registration -- EMA Crossover re-arm (mechanism E)

Registered 2026-09-29, before any count or backtest. Committed on `main` on top of `53fc7c09`
(the merge of Phase A: V108-1 `fdae5368`, V108-2 `1eaf3893`, plus the unrelated `test_jobs` flake fix).
Scripts under test: `scripts/backtest/measure_fib_v103.py`, `scripts/backtest/funnel.py` (the plan
calls it `fib_funnel.py`; the harness imports it as `fib_funnel`), and
`swingbot/core/market/entry_filters.py::_touch_events_after`.
Spec: `docs/superpowers/specs/2026-09-27-v108-ema-crossover-rearm-rescue-design.md`.
Every constant below was read from those files, not from memory.

## Mechanism

- K = the first K touch **events** inside `pullback_max_bars = 15` bars after each held cross. A run of
  consecutive touching bars is one event, and the first in-window touching bar always opens one.
- Per-direction knobs `max_touches_bull` / `max_touches_bear` in `DEFAULT_PARAMS["EMA Crossover"]`, both
  default `1`. The harness sets only the scored direction's knob (`E_PARAMS`).
- Unchanged: the ten ANDed filters, the stop/target arithmetic, and no `STRATEGY_GATES["EMA Crossover"]` entry.
- V108-3 real-data K=1 parity (TRAIN only, frames truncated at 2023-12-31, masks only, nothing scored):
  `frames 72`, `k1_entries 196`, mismatches `[]`.

## Grid

`K in {2, 3}`, loosest `K=3`, reference `K=1`. The reference is reported and **never eligible to win**; if
`K=1` would clear and no `K>1` cell does, the verdict is NO-LIFT.

## Windows

- `TRAIN_EXT = 2010-01-01..2023-12-31`.
- `FOLD_YEARS = 2013..2023` (11 folds), anchored at 2010-01-01 (`TRAIN_START_YEAR = 2010`): fold Y trains on 2010-01-01..Y-1, tests on year Y.
- `VALIDATION = 2024-01-01..2025-12-31`, read only by the `validation` command.

## Stage 0

Per direction, closed if the `K=3` TRAIN_EXT signal count is `< 30` (`MIN_N_TRAIN`), or if the `K=3` count is
`< 1.15 x` the `K=1` count (`inert_ratio = Fraction(115, 100)`, compared exactly). A closed direction keeps its budget.

## Clauses and constants

From `funnel.py`: `WR_FLOOR = 50.0`, `MIN_N_TRAIN = 30`, `MIN_N_VALIDATION = 15`, `MAX_SCRATCH_SHARE = 0.5`,
`FOLD_MIN_N = 15`, `FOLD_POSITIVE_SHARE = 2/3`, `MIN_QUALIFYING_FOLDS = 3`, `TRAIN_START_YEAR = 2010`,
`FOLD_YEARS = 2013..2023`, `BOOTSTRAP_SEED = 42`. From `acceptance.py`: `BOOTSTRAP_RESAMPLES = 10_000`.
Lower bound = 2.5th percentile over ticker clusters with an empty baseline arm.

- **Tier 1** = WR >= 50, ExpR > 0, N >= 30 (>= 15 on VALIDATION), scratch+timeout share <= 0.5.
- **Tier 2** = ExpR > 0 and ticker-cluster bootstrap lower bound > 0, with the same floors.
- **Only a Tier 1 winner can earn `VALIDATED`.**

## Stage 1

Plateau rule over the grid `(2, 3)`. Each cell's only neighbour is the other cell, so a winner needs **both**
cells to pass the same tier. Winner order: Tier 1 plateau, then Tier 2 plateau, then none. A Tier 2-only
winner still runs Stages 2-3; if it passes, its K ships but the badge stays `WEAK`.

## Stage 2

Per fold Y, re-select from `{2, 3}` the highest-ExpR cell on 2010..Y-1 with N >= 30 (none qualifies =
unselected, counted in the report). The fold clears when >= 3 folds have test N >= 15 and >= 2/3 of those
have ExpR > 0. A direction proceeds only with a Stage 1 winner **and** a Stage 2 clear.

## Populations and arithmetic

Both directions unmasked, as live today (EMA Crossover has no `STRATEGY_GATES` entry). Bearish rows pass
through the v93 laggard rule (`apply_laggard_rule`), as live does. `exit_model="v2"`, `scale_out=True`,
`tp2_mode="levels"`, `frictions=True`, `one_at_a_time=True`, level lifecycle as today, all ten horizons pooled.

## Data

The extended cache at `E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext`, and the universe
file `2026-09-29-v108-universe.txt`, sha256 `4452b50f6391e7b3f14a224874b7a0dcc8f4245f7f5cca006c0f0ed7c2dca4de`
(77 names; equals the v103 universe and, on 2026-09-29, the main-tree watchlist). 73 of 77 survive the
liquidity/data-quality filter, and **any run whose `universe_n` != 73 is discarded**. Survivorship bias is
stated, not corrected: it biases WR and ExpR upward in the early years.

## The one-shot rule

At most one `validation` run per direction (two in all), only at the committed evaluate output's
`validation_cell`, never at another cell, and never again after a FAIL.

## Outcomes (decided now)

- **Tier 1 PASS in a direction:** that direction's knob is set to its winning K.
- **Tier 2 PASS:** the knob is set as above, the badge stays `WEAK`, and no registry row is emitted.
- **Anything else:** both knobs stay `1`.

## Registry-row rule (decided now, before any score)

The `EMA Crossover` registry row is strategy-level and must describe the population live lets through, which
is both directions. `emit-registry` therefore runs **only when both directions pass VALIDATION at Tier 1**. It
pools their rows (`registry_status` -> `VALIDATED` only if the pooled badge also clears). In any other case no
row is emitted and the existing row (`WEAK`, N=36, 2024-01-01..2025-12-31, run 2026-07-18) stays untouched. A
one-direction Tier 1 PASS ships that direction's K and records in `docs/claude/backtest-methodology.md` why the
badge did not change. This is v103's population-equality rule applied to a strategy with no direction mask.

## Not consulted / not re-run

Not consulted: the 2026-07 VALIDATION read (N=36, WR 75.0%, fixed R:R table). Not re-run: v84's
`pullback_max_bars` axis (closed, round 2) and the v84 EMA fold-stability row.
