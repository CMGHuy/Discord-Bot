# v102 — Fibonacci x Rolling S/R confluence: pre-registration

**Plan:** `docs/superpowers/plans/2026-09-24-v102-fib-sr-confluence-extended-history.md`
**Spec:** `docs/superpowers/specs/2026-09-24-v102-fib-sr-confluence-extended-history-design.md`
**Committed:** 2026-09-24, before any backtest of a tolerance (Stage 0's counts-only run, `docs/superpowers/results/2026-09-24-v102-stage0.md`, does not count as scoring data).

## Direction entering Stage 1

**Bullish only.** Per `docs/superpowers/results/2026-09-24-v102-stage0.md` (Task V102-5): at the loosest grid tolerance (1.0), bullish TRAIN_EXT signal count is 89 (>= MIN_N_TRAIN=30) and proceeds. Bearish is 29 (< 30) and **closes NO-LIFT at Stage 0** — a free-stage closure, no backtest run, no VALIDATION budget spent. Bearish will not appear in Stages 1-3 of this pre-registration.

## Constants (from `scripts/backtest/measure_fib_confluence.py`, verbatim)

- `TRAIN_EXT = ("2010-01-01", "2023-12-31")`
- `VALIDATION = ("2024-01-01", "2025-12-31")`
- `TRAIN_START_YEAR = 2010`
- `FOLD_YEARS = range(2013, 2024)` — 11 anchored folds (2013 through 2023), each trained from 2010-01-01 through the fold year minus one
- `GRID = (0.25, 0.5, 0.75, 1.0)` — the candidate tolerances
- `BASELINE_TOL = 0.0` — reference only, never a candidate; shows what the population looks like with the confluence filter off
- Badge/volume constants: `WR_FLOOR = 50.0`, `MIN_N_TRAIN = 30`, `MIN_N_VALIDATION = 15`, `MAX_SCRATCH_SHARE = 0.5`
- Fold constants: `FOLD_MIN_N = 15`, `FOLD_POSITIVE_SHARE = 2/3`, `MIN_QUALIFYING_FOLDS = 3`

## Stage 1 — selection rule (TRAIN_EXT, free)

For each grid tolerance, pool trades and score the badge clauses (`win_rate >= 50`, `expectancy_r > 0`, `n >= 30`, `scratch_timeout_share <= 0.5`). A cell **passes** only if it clears every clause. **Plateau requirement:** a passing cell's immediate grid neighbours (one step down and up in `GRID`, where they exist) must also pass — an isolated spike does not qualify even if it individually clears every clause. **Winner:** the highest-`expectancy_r` cell among the plateau-passing cells. No plateau-passing cell -> no winner -> the direction does not proceed to VALIDATION.

## Stage 2 — walk-forward rule (fold-test, free, repeatable)

For each of the 11 `FOLD_YEARS`, the tolerance is **re-selected independently** on that fold's own train span (2010-01-01 through fold-year-minus-1): the highest-`expectancy_r` grid cell with decided `n >= MIN_N_TRAIN` on that span. A fold where no grid cell reaches `n >= 30` on its train span is **unselected** and does not qualify (it is not scored as a failure, it simply does not count toward either qualifying total). The fold's test-year performance is then measured only with its own re-selected tolerance, never the Stage 1 overall winner.

**Fold verdict:** among the folds that qualify (re-selected tolerance found, and that fold's test-year `n >= FOLD_MIN_N = 15`), at least 3 folds must qualify at all, and at least 2/3 of qualifying folds must have `expectancy_r > 0`. Both conditions must hold for Stage 2 to clear.

**Proceeds to VALIDATION only if both Stage 1 (a winner exists) and Stage 2 (the fold verdict clears) pass.**

## Stage 3 — VALIDATION (one shot, ever)

Window: 2024-01-01..2025-12-31, read from the same extended cache as TRAIN_EXT (`data/backtest_cache_ext/`). **At most one `validation` run for bullish**, at the tolerance Stage 1/2's evaluation names as `validation_tol` (the Stage 1 winner) — never at any other tolerance, and never re-run regardless of outcome. Badge clauses apply with `MIN_N_VALIDATION = 15` in place of `MIN_N_TRAIN`.

## Populations and arithmetic

- **Bullish** (the only direction reaching Stage 1+): entries from the **live gate** (no `gate_override`), i.e. exactly the population the live scanner would alert on.
- Bearish, had it proceeded, would have used the unmasked gate (`entry_filters.gate_override`) plus the v93 laggard rule (`measure_bearish_arms.apply_laggard_rule`) — stated here for completeness per the funnel's general design, but moot: bearish is closed at Stage 0 and this run will not measure it.
- **Exit arithmetic:** v2 exit model, scale-out enabled, TP2 mode `levels`, frictions on — the same settings used throughout v101/v93/v84 measurement, current live arithmetic (post-`a3a903d6` 2% stop cap).

## Extended cache and equivalence

`data/backtest_cache_ext/` (2010-01-01..2025-12-31, 73 tickers after the universe filter; CRWV/SNDK/SPCX absent, consistent with the shared cache) is the sole data source for every stage of this pre-registration, including VALIDATION — TRAIN and VALIDATION share one data source, per the spec. The shared `data/backtest_cache/` is never read or written by this funnel.

Equivalence check against v101's closed diagnostic (`docs/superpowers/results/2026-09-24-v102-ext-cache-check.md`, Task V102-4): **PASS both directions.** Bearish passed comfortably; bullish `ExpR` landed exactly at the ±0.03 tolerance boundary (+0.039 -> +0.009). Recorded honestly as a borderline pass, not a comfortable one — nothing found points to a data defect, but this is the number to revisit first if a later stage looks inconsistent with the diagnostic.

## Survivorship bias — declared, not corrected

The universe is today's watchlist. Tickers that later failed, delisted, or were removed from the watchlist before 2026-09-24 are absent from every year of TRAIN_EXT, including 2010-2015 where the distance from "today" is greatest. This biases the measured population **toward higher win rate and expectancy in the earlier years**, since only names that survived to be on today's watchlist are measured at all — a name that would have generated losing Fibonacci signals in 2011 and was delisted by 2015 never appears in this sample. This bias is not correctable within this measurement's scope and is not being corrected; it is disclosed so that an early-years result is read with it in mind, not as an unqualified historical average.

## The horizon population this measurement actually describes

Task V102-5's per-horizon breakdown (`docs/superpowers/results/2026-09-24-v102-stage0.md`) found that at every non-zero grid tolerance, **100% of surviving bullish signals fall in the 2w or 4w horizon** — all 8 longer horizons (2m through 9m) have zero survivors at every tested tolerance. **Any PASS this pre-registration produces describes a 2w/4w population, not a cross-horizon Fibonacci result**, even though the grid and the filter definition make no horizon distinction by design. This is disclosure per the Phase A code review's Important #2 finding (ledgered as a Ruling in this plan's SDD workspace) — it is not a reason to change the grid, the tolerance definition, or exclude other horizons before scoring; the filter is applied identically across all 10 horizons, and the concentration is an empirical fact about where confluence with Rolling S/R happens to occur at these tolerances, not a horizon mask added to the code.

## One-shot rule (binding)

At most **one** `python scripts/backtest/measure_fib_confluence.py validation` invocation for the bullish direction, at the tolerance `evaluate`'s output names as `validation_tol`, over the entire life of this pre-registration. If Stage 1/2 do not both clear, no VALIDATION run happens at all and this component closes NO-LIFT at Stage 2 without spending the shot.

## Cross-plan note

As of this pre-registration's commit, v100 (the standard arm producer, `docs/superpowers/plans/implemented/2026-09-23-v100-arm-producer_2-producer-funnel.md`) had **not** merged to `main` — only its spec and plan were committed. v102's funnel is self-contained regardless (its own Stage 1/2 rules, defined above) and does not go through `scripts/backtest/validate_component.py`.
