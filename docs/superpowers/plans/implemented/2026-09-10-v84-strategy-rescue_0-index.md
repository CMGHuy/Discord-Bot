# Strategy Rescue v2 — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each of the eight rescuable WEAK strategies exactly one
pre-registered shot at a `VALIDATED` badge, spending no VALIDATION budget on
any strategy that fails a free stage first.

**Architecture:** Each strategy gets an isolated, independently-testable change
— a `STRATEGY_GATES` entry, a new entry-filter parameter, or a target-candidate
addition — followed by a free TRAIN measurement, the free fold stages, and (only
on success) its single VALIDATION shot with `--emit-registry`. No strategy's
change touches another's code path. Failures are recorded and closed, not
retried.

**Tech Stack:** Python 3.11, pandas/numpy, pytest. No new dependencies. **No ML
in the live path.**

**Spec:** `docs/superpowers/specs/2026-09-10-v84-strategy-rescue-v2-design.md`
— read it before starting any task; the pre-registered rules live there and
this plan argues from them.

**Bump:** bot minor
**Edge:** expectancy (Tier 1 tasks are `none (integrity)` — re-measurement only)

## Parts

| Part | Tasks | Contents |
|---|---|---|
| `_1-tier1.md` | R1–R14 | EMA Crossover (no code change), Break & Retest (new gate entry), VWAP (gate re-derivation) |
| `_2-tier2.md` | R15–R30 | R15 shared arms harness, then RSI Divergence (R16–R19), MA Ribbon (R20–R23), Support/Resistance (R24–R27), wrap (R28–R30) |
| `_3-tier3.md` | R31–R36 | Fibonacci (1.0 extension candidate behind a config Field); R36 records the withdrawn Elliott Wave hypothesis |
| `_4-closeout.md` | R41–R45 | Full suite once, results docs, methodology rows, registry reconciliation, VERSION bump |

**Seven strategies, not eight.** Elliott Wave was withdrawn during planning —
its proposed mechanism already ships, at a *tighter* band than the spec
proposed (see R36 and spec §4.8). RSI was never in scope (spec §4.9).
**Maximum VALIDATION budget spend: 7 shots.**

## Global Constraints

Every task's requirements implicitly include this section.

- **Badge threshold, frozen:** `win_rate >= 50`, `expectancy_r > 0`,
  `N >= 30` (train) / `N >= 15` (validation), scratches+timeouts ≤ 50% of
  closed trades. **Never restore the pre-v31 80% floor.** Every
  `run_backtest_range.py` invocation MUST pass `--pass-wr 50` explicitly —
  the script's own default is still `80.0`.
- **Live arithmetic flags on every measurement:** `--exit-model v2 --scale-out`.
  A run without both is measuring something production does not do.
- **VALIDATION is ONE shot per strategy, ever.** It is spent only after that
  strategy's TRAIN rule and fold stages pass. A strategy that fails a free
  stage is recorded as closed in `results/` and gets no VALIDATION run.
  Never re-run a failed grid at a looser threshold.
- **Registry writes are machine-generated only:**
  `run_backtest_range.py ... --emit-registry swingbot/core/backtesting/validation_registry.json --run-date <YYYY-MM-DD>`.
  Hand-editing `validation_registry.json` is forbidden.
- **A plateau, not a spike.** Any task whose rule involves a grid must show the
  qualifying config sits in a plateau across adjacent parameter values. A lone
  passing cell surrounded by failures does not proceed to VALIDATION.
- **`tp2_mode` mismatch — campaign-wide trap.** `run_backtest_daterange`
  defaults `tp2_mode="none"` while `run_backtest_range.py --tp2` defaults to
  `"levels"`. **Any instrument that calls the backtest directly MUST pass
  `tp2_mode="levels"`**, or its folds measure different economics than the
  TRAIN grid they are compared against. This is the exact silent mismatch that
  corrupted round 2's Elliott Wave grid, and it is unrecoverable once a
  VALIDATION look is spent.

## The fold-stage instrument (pre-registered, hybrid by design)

Verified during planning, by three independent passes over the tooling:
`validate_component.py --stage walkforward` **runs no backtest** — it scores a
pre-written arms JSON of per-trade rows. `wf_run.py` **cannot produce that
input** (it emits pooled `delta_expectancy_r` only, no per-trade rows and no
`delta_win_rate_pp`), so **a `wf_run.py` PASS is not a Stage 2 pass** — never
treat it as one. The component arm is expressible **only through
`swingbot.config` attributes**; `DEFAULT_PARAMS` tunables are invisible to it.

That splits the campaign in two, and the split is deliberate:

| Strategies | Mechanism shape | Instrument |
|---|---|---|
| EMA Crossover, Break & Retest, VWAP (Tier 1) | no new knob — either nothing changes, or a `STRATEGY_GATES` constant | **FOLD-STABILITY RULE** (defined in part 1) |
| RSI Divergence, MA Ribbon, Support/Resistance, Fibonacci (Tiers 2–3) | a new `config.Field` + lazy `getattr` seam | **Arms harness + `gate_win_rate` delta gate** (R15) |

**Why not one instrument for all seven.** `gate_win_rate` scores a *delta
between two arms*. EMA Crossover has no second arm by design — spec §4.1's
entire point is that the mechanism is unchanged — so every fold delta would be
exactly `0.0` and the gate would return **FAIL by construction for a strategy
scoring 61.8% WR**. A badge is an absolute threshold on a strategy's own
population; scoring it with a delta gate is a category error. Break & Retest and
VWAP change a gate constant, not a config Field, so they take the same absolute
rule.

**Why not the absolute rule for all seven.** Fold-stability never asks whether
the *change* helped — a new filter could hold the badge clauses across folds
while actively making the strategy worse. Where a genuine second arm exists, the
delta gate is the stronger question and is therefore mandatory. Using the
absolute rule there would be a loosening dressed as a simplification.
- **Record failures as-is.** An empty results table is a finished measurement,
  not a stub. Do not "fix" a negative result.
- **Long runs go to the `backtest-runner` subagent**, never inline — any
  measurement here sweeps 77 tickers × 10 horizons and takes minutes.
- **Do not run the full pytest suite per task.** Use
  `python scripts/dev/testrun.py file tests/market/test_entry_filters.py`
  (~7s) while iterating. The full suite runs exactly once, in Task R41.
- **Closed mechanisms no task may re-implement:** `REGIME_ALLOW`,
  v32/v33 blended-confidence, `EFFECTIVE_CONFLUENCE`, `LEVEL_TOUCH_STRENGTH`
  (post-selection tiebreak — the S/R task uses touch-count at a *different*
  pipeline point and must say so in its results doc), `DEAD_CAT_BOUNCE_VETO`,
  EMA Crossover's pullback-entry redesign, MA Ribbon's
  `min_width_pctile`/`require_expanding` grid, RSI Divergence's
  `min_volume_ratio`/`min_reclaim_strength` grid, RSI's ADX+Bollinger gate.
- **RSI is out of scope.** It is deliberately not rescued (spec §4.9). No task
  in this plan touches `rsi_entries` or `DEFAULT_PARAMS["RSI"]`.

## Shared conventions

**TRAIN measurement for one strategy** (free, repeatable, no budget):

```bash
python scripts/backtest/run_backtest_range.py --train --strategy "<Name>" \
  --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratchpad>/<slug>_train.json
```

**VALIDATION shot** (ONE per strategy, only after every free stage passes):

```bash
python scripts/backtest/run_backtest_range.py --validation --strategy "<Name>" \
  --exit-model v2 --scale-out --pass-wr 50 \
  --emit-registry swingbot/core/backtesting/validation_registry.json \
  --run-date <YYYY-MM-DD> \
  --json <scratchpad>/<slug>_validation.json
```

**Baseline numbers to beat** (fresh TRAIN, current arithmetic, 2026-09-10 —
these are the pre-registered starting points; a rescue must improve on its own
row, and every task records its delta against it):

| Strategy | N | Win rate | ExpR |
|---|---|---|---|
| EMA Crossover | 55 | 61.8% | +0.494 |
| Break & Retest | 298 | 48.0% | (pooled) |
| VWAP | — | 44.5% pooled / 52.9% at 4w | +0.335 at 4w |
| RSI Divergence | 1534 | 48.0% | +0.257 |
| MA Ribbon | 233 | 48.1% | +0.270 |
| Support/Resistance | 247 | 45.7% | +0.316 |
| Fibonacci | 246 | 35.4% | +0.232 |
| Elliott Wave | 104 | 32.7% | +0.184 |

## Parallelisation

Tier 1, Tier 2 and Tier 3 parts touch disjoint code and may run in separate
worktrees concurrently. **Within a part, tasks are sequential** — each
strategy's measurement depends on its own code change landing first.

Two hard serialisation points:

1. **`swingbot/core/market/strategy_types.py` is touched by both R-Break &
   Retest (adds a key) and R-VWAP (edits the `"VWAP"` key).** These two tasks
   must not run concurrently in different worktrees — land one, rebase, then the
   other. Everything else in Tier 1 is independent.
2. **`validation_registry.json` is written by every VALIDATION task.** Emits are
   same-key merges, so concurrent emits from different worktrees can lose rows.
   Run all `--emit-registry` steps from a single branch, serially. Task R44
   reconciles the final file.

## Task map

Grep `^### Task R` in any part file to list its tasks; `/task-brief R<N>`
extracts one.

- **R1–R4** EMA Crossover — fold stages, then VALIDATION (no code change)
- **R5–R9** Break & Retest — add `STRATEGY_GATES` entry, TRAIN, folds, VALIDATION
- **R10–R14** VWAP — re-derive gate to 4w, TRAIN, folds, VALIDATION (slope-gate
  fallback only on failure)
- **R15** Shared arms harness (`measure_strategy_arm.py`) — **blocks every
  Tier 2/3 fold stage**; build it first
- **R16–R19** RSI Divergence — `min_consecutive_rsi_turn`, grid, folds, VALIDATION.
  **Real allocation:** R16/R17 ran; R17 REJECTED-ON-TRAIN (0/3 qualify) so
  R18/R19 did not run (gated). Closed WEAK, VALIDATION unspent.
- **R20–R23** MA Ribbon — `confirm_bars`, grid, folds, VALIDATION.
  **Real allocation:** R20/R21 ran; R21 0/2 qualify so R22/R23 did not run
  (gated). Closed WEAK, VALIDATION unspent.
- **R24–R27** Support/Resistance — level-touch significance filter, grid, folds,
  VALIDATION. **Real allocation:** R24/R25 ran; R25 0/3 qualify so R26/R27
  did not run (gated). Closed WEAK, VALIDATION unspent.
- **R28–R30** Tier 2 wrap — 0/3 rescued, 0/7 VALIDATION shots spent so far
  (combined with Tier 1's 0/3). **Handoff for R42/R43:** RSI Divergence, MA
  Ribbon and Support/Resistance all remain `WEAK` — each closed at its free
  TRAIN grid stage, never reached Stage 2 or VALIDATION; per-strategy
  failure stage and metric are in
  `docs/superpowers/results/2026-09-10-v84-tier2-summary.md`, sourced from
  each strategy's own `*-train.md` doc.
- **R31–R35** Fibonacci — 1.0 extension behind `FIB_TARGET_1_0_EXTENSION`,
  measurement script, TRAIN, folds, VALIDATION
- **R36** Elliott Wave — records the withdrawn hypothesis; **no tasks, no shot**

**R37–R40 do not exist.** They were reserved for Elliott Wave before it was
withdrawn. The gap is deliberate — nothing is missing, and the numbers were left
unreused so the withdrawal stays visible in the task map rather than being
papered over by renumbering.

**Known reconciliation item for the executor (parts 2 and 3 were written in
parallel):** R15 builds a shared arms harness (`measure_strategy_arm.py`), and
R32 independently specifies a Fibonacci-specific one (`measure_fib_extension.py`,
modelled on `measure_rs_gate_effect.py`). **Before building R32's script, check
whether R15's harness already covers the Fibonacci arm** — a config-Field arm is
exactly what R15 emits. Build a second script only if R15's interface genuinely
does not fit, and say why in the commit message. Two harnesses that do the same
thing is how measurement instruments drift apart.
- **R41** Full pytest suite, once
- **R42–R43** Results docs for every strategy, rescued or closed
- **R44** Registry reconciliation + final badge count
- **R45** `backtest-methodology.md` closed-pre-registration rows, `VERSION.json`
  bump, plan close-out

## Definition of done

1. Every one of the eight strategies has a recorded verdict — rescued with a
   fresh registry row, or closed with its negative result written to
   `docs/superpowers/results/` and a row in the closed-pre-registrations table.
2. No VALIDATION run exists for any strategy that failed a free stage.
3. The full suite passes once (Task R41): `0 failed`, `0 xfailed`.
4. **Rescuing only Tier 1 is a success.** The plan is complete when every
   strategy has a verdict, not when some number of them pass.
