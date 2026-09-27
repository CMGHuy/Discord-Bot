# v100 — Standard arm producer: measurability and power guards for the acceptance funnel

**Version:** ui 1.21.0 · bot 1.10.2
**Bump:** none
**Edge:** none (integrity) — buys no edge itself; protects every future `expectancy`/`harvest` shot from being spent on an instrument that cannot see the component or a sample too small to answer.

Sub-project **A** of the TRAINING/VALIDATION improvement programme
(brainstorm 2026-09-23). Siblings, each its own spec → plan cycle, in this order:
**C** cached baseline artifacts (throughput) → **B** fresh holdout window + live
forward-test scoring → **D** historical scan-replay engine. None is in scope here.

## 1. Problem

Three recurring failure modes in the closed-pre-registrations table
(`docs/claude/backtest-methodology.md`) share one root cause: **every plan
hand-builds its own instrument.** `scripts/backtest/` holds ~16 bespoke
`measure_*.py` scripts; `validate_component.py` only scores whatever arms JSON
they hand it.

1. **Unmeasurable by construction.** `DATA_DRIVEN_STOPS_ENABLED` burned its
   VALIDATION shot scoring 0.0000; `STALL_EXIT_ENABLED` (v92 H2) closed on TRAIN
   the same way. Both because `backtest.py:run_backtest` builds plans through
   `_trade_plan_at` plus an inline `TradePlanV2(...)`, never through
   `planning/builders.py:build_strategy_plan`. Nothing checks that a component
   reached the trades before compute — or a shot — is spent.
2. **Underpowered samples.** Each script picks its own universe: v69 ran 3
   tickers, v36 15 tickers × 5 horizons, v68 25 tickers. Fold `N >= 30` /
   `N >= 15` misses recur (v84 EMA, VWAP; v69). Many "no lift" rows are
   really "could not tell".
3. **Overstated Stage 0 MDE.** Both `acceptance.mde_win_rate` and
   `acceptance_harvest.mde_expectancy_r` use an unpaired formula
   (`sqrt(2·var/n_eff)`). Nearly every design here is paired — veto/filter arms
   are subsets of the same baseline, exit arms replay the same entries — so the
   relevant variance is that of the per-trade *change*, typically far smaller.
   The harvest docstring flags this; the win-rate side has the same defect,
   unflagged.

`tests/backtesting/test_knob_observability.py` already maps the blind spots:
~40 searchable knobs are `EXEMPT` from the replay, falling into three groups —
**plumbing gaps** (4: `RSI_DIV_MIN_CONSECUTIVE_TURN`, `MA_RIBBON_CONFIRM_BARS`,
`SR_MIN_LEVEL_TOUCHES`, `FIB_TARGET_1_0_EXTENSION` — read from the config
global, not threaded through `ScanParams`), **exit-only** (4: the v92 trail and
stall knobs — invisible because the test compares selection-time plan fields,
not outcomes), and **live-scan-only** (the rest — confidence, dedup, MTF/HTF,
OPEX, RS, regime, alert caps, which live in `scanning/engine.py` and no replay
runs).

## 2. Decisions (partner-approved 2026-09-23)

| Question | Decision |
|---|---|
| Approach | One standard arm producer, not thin funnel guards or a process-only rule |
| Engine | Replay engines behind a pluggable `ArmEngine` interface now; historical scan replay is sub-project D and registers later without funnel changes |
| Sample width | Stages 1–3 must run the full cached universe × all 10 horizons; only the Stage −1 pilot may be narrow |
| Stage 0 MDE | Paired MDE is the default on **both** gates; unpaired kept only for arms with no pairing overlap |
| Enforcement | `validate_component.py` refuses unstamped arms unless `--bespoke-instrument "<reason>"`, which the results doc prints |

## 3. Architecture

New package `swingbot/core/backtesting/arms/`:

| Unit | Does | Depends on |
|---|---|---|
| `engine.py` | `ArmEngine` protocol: `engine_id`, `code_hash()`, `run(frames, window, horizons, params) -> list[KeyedTrade]` | nothing |
| `confluence_engine.py` | Confluence population: wraps `backtest_scenarios.replay_scenarios` + `planning/exit_sim.simulate_exit` | existing replay |
| `strategy_engine.py` | Strategy-source population, plans built **through `build_strategy_plan`** | `planning/builders.py` |
| `reachability.py` | Registry: every searchable knob → `reachable` / `exit_only` / `live_scan_only` / `plumbing_gap`, plus reason. Replaces the observability test's local `EXEMPT` dict — one source of truth | `config` |
| `keys.py` | `KeyedTrade`; pairing key `(ticker, horizon, source, strategy, signal_date, direction)` | — |
| `windows.py` | The single stage → window/universe table (§4) | — |
| `provenance.py` | Stamp: engine ids + code hashes, stage, window, universe list + count, horizons, knob delta, git HEAD | — |
| `scripts/backtest/measure_arms.py` | CLI: `--knob FLAG=value [--knob …] --stage {pilot,selection,walkforward,validation}` → stamped, keyed arms JSON in the shape `validate_component.py` already reads | all above |

`run_backtest` itself is **not** changed: badges and `--emit-registry` keep
their current path. `strategy_engine` is a new measurement path beside it.
Existing `measure_*.py` scripts and their closed records are untouched; only new
pre-registrations must use the producer.

Funnel changes:

- **Stage −1 `reachability`** (new, free) in `validate_component.py`: static
  check first — `live_scan_only` / `plumbing_gap` refused before any compute;
  then the pilot's changed-outcome count — zero ⇒ refused. The comparison is on
  **simulated outcomes**, not plan fields, so `exit_only` knobs are measurable.
- **Width check** at Stages 1–3 against the stamp.
- **Paired MDE:** `mde_win_rate_paired` (discordant-pair / McNemar-style) and
  `mde_expectancy_r_paired` (variance of per-key ΔR), both ticker-cluster
  design-effect adjusted. Stage 0 uses them whenever the arms carry keys with
  overlap; the unpaired functions remain for zero-overlap arms.
- **Stamp check:** unstamped arms refused unless `--bespoke-instrument`.

First implementation step: thread the four `plumbing_gap` knobs through
`ScanParams`, reclassifying them `reachable`.

## 4. Data flow

```
measure_arms.py --knob X=v --stage S
  → reachability.classify(X)            static refusal before compute
  → windows.resolve(S)                  window + universe from ONE table
  → engines.run(baseline params)        ┐ same frames, same process pool,
  → engines.run(component params)       ┘ same engine code hash
  → pair by key → changed-outcome count
  → write arms JSON + provenance stamp
validate_component.py --stage S --arms <json>
  → verify stamp → Stage −1 / 0 paired MDE / 2 folds / 3 clauses
```

`windows.py` table (consolidates windows currently scattered across docs and
scripts; values are today's documented ones, not new choices):

| Stage | Window | Universe × horizons |
|---|---|---|
| `pilot` | 2018-06-01..2020-12-31 | first 10 tickers of the sorted cached universe × all 10 |
| `selection` | fold-train windows (2018-06..2020 / ..2021 / ..2022) | full × all 10 |
| `walkforward` | fold-test 2021 / 2022 / 2023 | full × all 10 |
| `validation` | 2024-01-01..2025-12-31 | full × all 10 |

The producer loads frames only for the stage window plus indicator warm-up and
**never opens 2024+ data unless `--stage validation`.**

## 5. Error handling

Stable refusal tokens on stderr (same convention as the registry hard gates).
Every refusal leaves the one-shot budget intact.

| Token | When |
|---|---|
| `refused:unreachable:<class>` | knob classified `live_scan_only` or `plumbing_gap`; reason printed from the registry |
| `refused:zero-diff` | pilot changed zero keyed outcomes |
| `refused:narrow-universe` | Stages 1–3 stamp below full universe × 10 horizons |
| `refused:unstamped` | arms JSON with no stamp and no `--bespoke-instrument` |
| `refused:engine-mismatch` | baseline and component stamps carry different engine code hashes |
| `refused:window-contact` | a non-validation stage's stamp touches 2024+ |

- **Closed pre-registrations:** already denied by
  `.claude/hooks/guardrails.py:CLOSED_PREREGISTRATION_KNOBS`; the producer does
  not duplicate that list.
- **Partial failure:** one ticker failing to replay fails the whole run, naming
  it. Silently dropping a ticker would make the stamped universe a lie.
- **Progress:** flushed per-ticker lines; a percent figure written to
  `logs/measure_arms.<run-id>.progress`, deleted on success. Full-width runs
  dispatch to `backtest-runner`.

## 6. Testing and verification

Unit (fast tier, committed v74 two-ticker fixture, no network):

- `keys.py`: pairing stable across runs; duplicate keys raise.
- `reachability.py`: every `config.searchable_attrs()` knob has exactly one
  class — a new unclassified searchable knob fails the suite.
- `test_knob_observability.py` rewritten to read the registry: a `reachable`
  knob must change fixture **outcomes**; a `plumbing_gap` knob that starts
  changing them fails with "reclassify me".
- Paired MDE: zero-overlap input reduces to the unpaired formula; a synthetic
  paired population with known ΔR variance matches the closed form; MDE is
  monotone non-decreasing in ICC.
- One test per refusal token.

Parity (the one real behaviour change): `strategy_engine` vs `run_backtest` on
the fixture, all flags default. Stops must be identical. Targets are expected
identical; any difference is **recorded in the plan's results as a finding**,
not forced equal (v31 documents deliberate target divergence in
`_trade_plan_at`).

Acceptance proof (slow tier, one run each, `backtest-runner`, pilot and Stage 0
only — nothing spent, no closed knob taken past Stage −1):

1. `--knob STALL_EXIT_ENABLED=true --stage pilot` ⇒ `refused:zero-diff` or
   `refused:unreachable:*` — mechanically reproduces the v92 H2 closure.
2. `--knob DATA_DRIVEN_STOPS_ENABLED=true --stage pilot` ⇒ refused — the shot
   it burned would now be refused for free.
3. One `reachable` knob **not** in the closed-pre-registrations table (chosen
   at plan time, justified there) ⇒ non-zero diff, stamped arms, and
   `validate_component --stage mde` printing paired and unpaired MDE side by
   side.

Full suite once, as the plan's final task.

## 7. What this does not do

- **Reopens nothing.** A better instrument is not a new hypothesis
  (`backtest-methodology.md`). Every closed row stays closed, including v92
  H1's +0.2409R Stage 0 MDE — a smaller paired MDE is not grounds to re-run it.
- **Changes no gate threshold.** Clause constants, `ALPHA`, `MDE_POWER`,
  `WIN_RATE_FLOOR_PP`, `VOLUME_MAX_CUT_PCT` are untouched; only the variance
  estimator Stage 0 feeds them changes.
- **Does not make live-scan-only knobs measurable.** They are refused honestly
  until sub-project D, or measured through a logged `--bespoke-instrument`.
- No caching (C), no new window (B), no live-path or alert change.

## Parallelisation

- **Group 1 (parallel):** `keys.py`, `windows.py`, `provenance.py`, paired MDE
  functions (`acceptance.py` / `acceptance_harvest.py`) — disjoint files, no
  shared symbols.
- **Sequential:** `ScanParams` threading of the four plumbing-gap knobs before
  `reachability.py` (the registry classifies them `reachable` only once threaded)
  and before the observability-test rewrite. `engine.py` before both engines;
  both engines before `measure_arms.py`; `measure_arms.py` before the
  `validate_component.py` stamp/Stage −1/width checks (they validate its
  output). Acceptance proof after everything; full suite last.
