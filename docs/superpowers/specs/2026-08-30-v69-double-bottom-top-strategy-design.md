# v69 — Double bottom / double top as a standalone strategy

**Version:** ui 1.10.0 · bot 1.5.0
**Bump:** bot minor (1.5.0 → 1.6.0)
**Edge:** volume

Add a twelfth entry to `STRATEGY_FUNCS`: a two-pivot reversal pattern that
enters on the **neckline break**, not on the second touch. It generates its own
trades, earns its own `STRATEGY_GATES` scope and its own VALIDATED/WEAK badge,
and never touches the confluence path.

This is shot #2 of the two-shot sequence begun in v68. v68 puts chart-pattern
geometry to work as a *veto* on an existing negative population; this puts it to
work as a *source* of trades.

## Why this is not v36 wearing a new name

The nearest closed pre-registration is **v36 level touch strength**, and the
resemblance is close enough that the burden of proof sits here rather than with
a reviewer. v36 measured win rate 37.09% → 36.32% and expectancy 0.0670R →
0.0057R, and was filed under `no-lift/`.

The mechanisms are genuinely different in three ways, and all three matter:

| | v36 (closed) | v69 (this spec) |
|---|---|---|
| What it produces | A **grade** on a level that already existed | An **entry trigger** where there was none |
| Where it acts | Confluence target selection + a confidence factor | `entry_filters.entries_for` — the strategy path |
| What confirms it | Nothing; the grade applied on sight | A **neckline break**, a later event the pattern must survive |

The third is the substantive one. v36 asked *"has this level been touched
often?"* — a question answerable the moment you see the level. v69 asks *"did
price form two equal lows, then break the peak between them?"* — a question
that cannot be answered until the break happens, which is precisely what makes
it an entry rather than a grade.

A twelfth **confluence voter** would still be a dead branch (v49: mean
off-diagonal redundancy 0.628, `N_eff` capped at 1.746). This spec does not
propose one. Nothing here appends to `collect_candidate_levels` or
participates in `count_confirming_strategies`.

## The budget gate

v68 and v69 are two pre-registered shots on the same underlying question:
*does multi-pivot chart geometry carry information this bot does not already
have?*

**Read v68's TRAIN result before spending v69's shot.** Specifically:

- If v68's veto showed **no cell clearing its rule at any decline threshold**,
  that is evidence the geometry carries nothing on this universe, and v69's
  VALIDATION should not be spent on a hunch. Its TRAIN grid may still run — a
  TRAIN grid is not a budgeted resource — but a weak TRAIN plus a dead v68 is a
  `no-lift/` close, not a VALIDATION shot.
- If v68 measured a real improvement, the geometry hypothesis survives and v69
  proceeds normally.

This is a judgement the plan records rather than automates, because "the
geometry carries nothing" is an inference across two different mechanisms and
should be made by a person looking at both tables.

## Decisions taken

| Question | Decision |
|---|---|
| Pivot source | Reuse `indicators.zigzag_pivots` — do not write a second pivot detector |
| Confirmation | **Neckline break**, never the second touch |
| Direction | Both — double bottom (bullish) and double top (bearish) |
| Registration | A full twelfth strategy: `STRATEGY_FUNCS`, `ENTRY_FUNCS`, slash command, backtest CLI |
| Initial scope | **No `STRATEGY_GATES` entry** — unrestricted until TRAIN earns a scope |
| Measurement | `tune_strategy.py` (TRAIN grid) then `run_backtest_range.py` (VALIDATION) |
| Chart overlay | **Out of scope** — see below |

**Reusing `zigzag_pivots`** matters beyond saving code. It already backs the
Elliott Wave strategy, so its pivot semantics are exercised by an existing
VALIDATED-or-WEAK badge; a second detector with slightly different reversal
semantics would mean two definitions of "swing low" in one codebase, and the
divergence would surface as an unreproducible backtest rather than an error.

**No `STRATEGY_GATES` entry at launch.** A missing key means both directions
and all horizons, and `STRATEGY_GATES`' own comment block records that its
entries are *earned* from a TRAIN grid with the numbers written inline. Adding
a guessed scope would fabricate evidence in the exact place this repo keeps its
real evidence.

**The chart overlay is out of scope.** Drawing the two lows and the neckline on
the trade chart is genuinely useful and genuinely separable: it changes no
trade, affects no measurement, and touches `chart_strategy_overlay.py`, which
is a file this plan otherwise never opens. It gets its own small plan if the
strategy validates. Shipping a pattern nobody can see on the chart is an
acceptable interim state; delaying a measurement to draw it is not.

## Detection rule

For a **double bottom**, over `zigzag_pivots(df, threshold_pct)`:

1. Find the last three pivots in the order `low → high → low`.
2. **Equality** — the two lows are within `equality_tol_pct` of each other,
   measured against the lower of the two.
3. **Separation** — the intervening high sits at least `separation_pct` above
   the higher of the two lows. Without this, two lows a rounding error apart
   with no real peak between them is a flat line, not a pattern.
4. **Recency** — the second low is within `max_age_bars` of the current bar, so
   a shape from six months ago does not trigger today.
5. **The neckline break is the entry** — `close > high_pivot_price`, on the
   current bar, having been at or below it on the previous bar. That last
   clause makes it a *fresh* break rather than a state that stays true for
   weeks.
6. **Volume arm** (when enabled) — the breaking bar's volume exceeds its
   trailing 20-bar mean by `volume_mult`.

Double top is the exact mirror: `high → low → high`, break *below* the
intervening low.

### Why confirmation-on-break is what makes this causal

The second low is only recognisable as "the second low of a double bottom"
after price turns back up — which is information from the future at the moment
the low prints. A detector that fired on the second touch would be reading
tomorrow's data and would produce an excellent backtest and a worthless live
signal.

Entering on the neckline break removes that entirely: every clause is
evaluable from bars at or before the current one. `zigzag_pivots` itself only
confirms a pivot after a `threshold_pct` reversal, so a pivot it reports at
bar *i* was already confirmed by bar *i*. This is the same discipline
`entry_filters.py` states at the top of the file, and v69 gets the same
truncation test v68's D2 introduced.

### Parameters

| Parameter | Value | Fixed or gridded |
|---|---|---|
| `zigzag_threshold` | the horizon's `max_risk_pct` | **Fixed** — the same scaling `elliott_wave_signal` already uses |
| `max_age_bars` | 10 | **Fixed** — a fresh break, not an old one |
| `equality_tol_pct` | 2 / 3 / 5 | Gridded |
| `separation_pct` | 5 / 10 | Gridded |
| `volume_mult` | off / 1.5 | Gridded |

**12 TRAIN cells** (3 × 2 × 2), the same grid width as v68 and the same
reasoning: most parameters fixed from the shape of the problem, only the ones
whose right value is genuinely unknown left to the grid.

## Measurement

`Edge: volume` — this adds qualifying setups rather than sharpening existing
ones. If it also raises pooled expectancy that is a bonus, not the claim.

**TRAIN 2020-2023** via the existing grid tool:

```bash
python scripts/backtest/tune_strategy.py --strategy "Double Pattern" \
    --grid equality_tol_pct=2,3,5 separation_pct=5,10 volume_mult=0,1.5
```

No new instrument. `tune_strategy.py` already grids `DEFAULT_PARAMS` keys, and
`entries_for` is the single source both the backtest and the live scanner read —
so unlike v68's confluence veto, this is visible to `run_backtest_range.py` by
construction.

Pre-registered selection, matching the shape `STRATEGY_GATES`' existing entries
were earned with: **per (direction, horizon) cell include iff
`win_rate >= 50` and `expectancy_r > 0` and `N >= 30` and
`excluded <= 50%`; adopt the parameter set with the best pooled ExpR among sets
having at least two qualifying cells.** The qualifying (direction, horizon)
cells become the strategy's `STRATEGY_GATES` scope, with the numbers written
inline as a comment exactly as every existing entry carries them.

**VALIDATION 2024-25** is one shot on the adopted parameter set and scope, via
`run_backtest_range.py --validation --strategy "Double Pattern"`. Gates:
`win_rate >= 50`, `expectancy_r > 0`, `N >= 15`, scratches+timeouts ≤ 50%. A
pass earns a `VALIDATED` registry badge; a fail earns `WEAK` and the strategy
stays shipped but unpromoted — the same disposition v31 gave Break & Retest
and VWAP.

**If TRAIN produces no qualifying parameter set**, the strategy is not shipped,
VALIDATION is not spent, and the documents close under `no-lift/`.

## Risks and limitations

- **N is the main threat, again.** Requiring two near-equal pivots plus a real
  intervening peak plus a fresh break is a narrow filter, and the `N >= 30` per
  cell gate is not lenient. The `off` arm on `volume_mult` and the widest
  `equality_tol_pct` exist to keep some cells populated; cells that come back
  under 30 are recorded as such rather than dropped.
- **`zigzag_threshold` scales with the horizon**, so the same ticker produces
  different pivots at `2w` and `9m`. That is intentional — a "swing low" means
  something different over two weeks than over nine months — but it means the
  pattern is not one shape measured ten times, and the per-horizon cells are
  genuinely independent.
- **Elliott Wave is the cautionary neighbour.** It is the only existing
  strategy built on `zigzag_pivots`, and `STRATEGY_GATES`' comment records that
  it *"could not be gated to a passing train config … only fires on 4w and
  bullish-only there is WR=74.1 ExpR=-0.001"*. A pivot-based strategy has
  already failed to earn a scope in this codebase once.
- **This buys no edge if v68 measured none.** See the budget gate above.

## Parallelisation

- **Sequential: the detector before everything.** The entries function, the
  signal function and every test consume its signature.
- **Group A (parallel):** the causality test and the registration sweep test —
  different files, no shared symbol.
- **Sequential: registration after the entries and signal functions exist**, or
  the sweep test asserts against half-wired registries and fails for the right
  reason at the wrong time.
- **Sequential and absolute: TRAIN before scope, scope before VALIDATION,
  VALIDATION once.**

## Success criteria

1. `double_bottom` / `double_top` detect the textbook shapes and reject flat
   lines, single bottoms, and stale patterns whose break already happened.
2. The verdict is provably causal — truncating the frame at bar *i* does not
   change bar *i*'s answer.
3. The strategy is registered at **every** point an existing strategy appears,
   proven by a test that enumerates them rather than by a checklist.
4. A twelve-cell TRAIN grid is recorded with the selection rule quoted and
   every under-populated cell named.
5. Either a parameter set and scope are adopted and VALIDATION is spent once,
   **or** none qualifies and the component closes without spending it.
6. `python scripts/dev/testrun.py full` is green.
