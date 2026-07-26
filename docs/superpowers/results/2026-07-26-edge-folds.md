# Edge Engine v4 — Task E33: Phase-E2 component fold decisions

Generated 2026-07-26T13:56:50+00:00 in 253.4 min.

## Pre-registered selection rule (quoted verbatim, fixed before data contact)

> anchored expanding folds — train 2018→fold-start, test years 2021 / 2022 / 2023. A component passes if pooled test `expectancy_r` improves vs baseline in **≥ 2 of 3 folds**, no fold degrades baseline expectancy by more than 0.05R, and N ≥ 30 per fold. Components that fail are documented and dropped — no second grid on the same hypothesis.

Constants as run: improving folds ≥ 2, max degradation 0.05R, min N 30.

## Setup

- Universe: `watchlist` — 78 symbols, 11 strategies × 10 horizons
- Exit model: v2 + scale-out, `tp2_mode=levels`, frictions ON (matches the E22 friction-adjusted baseline tooling's own defaults)
- OHLCV: `data/backtest_cache/` (same cache the E22 baseline was measured on)
- Each (symbol, strategy, horizon) backtested once per leg; folds sliced by entry_date

## Results

### AVWAP_LEVELS_ENABLED — **FAIL**

| fold | N | baseline expR | component expR | delta |
|---|---:|---:|---:|---:|
| 2021 | 1617 |   0.2125 |   0.2124 |  -0.0001 |
| 2022 | 838 |   0.0346 |   0.0345 |  -0.0001 |
| 2023 | 1076 |   0.1893 |   0.1893 |  -0.0001 |

Pooled delta expectancy_r: -0.0001

### VOLUME_PROFILE_NODES_ENABLED — **FAIL**

| fold | N | baseline expR | component expR | delta |
|---|---:|---:|---:|---:|
| 2021 | 1617 |   0.2125 |   0.2125 |  -0.0000 |
| 2022 | 838 |   0.0346 |   0.0338 |  -0.0008 |
| 2023 | 1076 |   0.1893 |   0.1896 |  +0.0003 |

Pooled delta expectancy_r: -0.0002

## Not run — the harness cannot observe these

Registering these would score a meaningless 0.0000 delta and burn their one-shot pre-registration, so they are deliberately NOT run.

- **DATA_DRIVEN_STOPS_ENABLED** — E31/E32 reach plan_engine.build_strategy_plan only; the backtest sizes through backtest._trade_plan_at, which takes no stop_mult/tp2_r. Needs those threaded through run_backtest first.
- **REGIME_GATES_ENABLED** — entry_filters.apply_regime_gate needs a `regimes` series that run_backtest -> _vectorized_entries -> entries_for never supplies, and strategy_types.REGIME_ALLOW is empty, so there is nothing to gate even if it did.
- **PYRAMIDING_ENABLED** — E38 lives in the live plan manager; plan_engine.simulate_exit has no pyramiding concept, so the backtest cannot observe it.
- **EARNINGS_BLACKOUT_DAYS** — E18's gate was never wired into the scan or backtest path.

## Observations

_Written after reading the numbers above; failures are recorded, not fixed._

**Both tested components fail decisively, not marginally.** Pooled deltas
(-0.0001R for AVWAP, -0.0002R for Volume Profile) are noise-level against
the 0.05R degradation threshold — these aren't components that almost
passed. AVWAP improves 0/3 folds; Volume Profile improves only 1/3 (2022
degrades -0.0008R, 2023 improves +0.0003R), short of the required ≥2. Per
the pre-registered rule, **both are dropped.** No config default changes,
no `REGIME_ALLOW` changes — `docs/superpowers/results/adopted_components.json`
is written empty (`{}`).

**Adopted count for Phase E2: zero.** This is the real headline, not a
detail. The plan's own Task E33 text specifies a 16-variant grid —
`regime_gates`, `rs_min` at 3 thresholds, `sector_rs`, `mtf_min` at 2
thresholds, `breadth_floor` at 3 thresholds, `gap_fragile_filter`,
`earnings_blackout` at 2 windows, `mae_stops`, `mfe_tp2`, `time_stops` —
none of which were ever run. The config flags that grid assumes
(`RS_MIN_ENABLED`, `MTF_MIN_ENABLED`, `BREADTH_FLOOR_ENABLED`,
`GAP_FRAGILE_FILTER_ENABLED`) do not exist anywhere in this codebase
(verified by grep — zero hits). Every factor task that would feed them
(E24 regime gates, E25/E26 RS/sector-RS, E27 MTF alignment, E28 breadth,
E34 candle quality, E36 divergence, E37 composite quality score) shipped
its math as a tested pure function with backtest-observable wiring
explicitly and deliberately deferred, each documented at the time as a
separate, later task. The 2 components actually tested here
(AVWAP/Volume Profile) are the only ones with real wiring into the
backtest today, via `levels.collect_candidate_levels` under
`tp2_mode="levels"` — everything else is a pure function the walk-forward
harness structurally cannot see, same reasoning as the 4 `INERT_COMPONENTS`
listed above, just a larger set of them than this doc's "Not run" section
enumerates (that section only covers 4 of the ~10+ actually-dormant
components; the rest were never wired well enough to even be considered
inert candidates for this specific script's `REGISTERED_COMPONENTS` dict).

**This is not a burned pre-registration.** The rule says "no second grid on
the same hypothesis" — none of the untested components were ever actually
run against real data, so testing them later (once wired) is a first
attempt, not a retry. The prerequisite work is exactly the plan's own
"deferred fix list" from Task E39/E40 (thread `stop_mult`/`tp2_r` through
`run_backtest → _trade_plan_at` for E31/E32; thread a `regimes` series
through `_vectorized_entries → entries_for` for E24; wire pyramiding into
`simulate_exit` for E38; wire E18's earnings blackout into the scan/backtest
path) — closing that list is what would let a *real* 16-component grid run,
not a repeat of this one.

**Net effect on downstream tasks:** E40's blocked shadow-evaluation
sub-step needed a fold-passing component list — that list is empty, so
there is nothing left to build there. E41 (permutation test) and E42
(plateau report) exist as tested, working tools but have nothing to run
against — both only apply to *adopted* components. E43's ablation harness
reads an empty `adopted_components.json` and correctly produces no rows.
E44's evidence pack closes honestly at "0 components adopted this phase,"
not because the phase's underlying research (E23-E37's factor math) was
wrong, but because most of it was never connected to anything measurable.

