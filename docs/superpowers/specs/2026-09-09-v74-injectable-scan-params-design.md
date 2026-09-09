# v74 — Injectable scan parameters: making the decision surface searchable

**Version:** ui 1.11.0 · bot 1.6.1
**Bump:** bot patch. v72 lands first and takes 1.6.1 → 1.6.2, so this takes
1.6.2 → 1.6.3. A pure refactor: `ScanParams.from_config()` reproduces today's
behaviour exactly, and no alert, chart or screen moves.
**Edge:** none (integrity) — and deliberately labelled that way. This spec buys
**no** edge by itself. It is the enabling half: it makes the trade-plan
decision surface addressable so v75 (search engine) and v76 (selection
statistics) can find edge in it. Calling it `expectancy` because expectancy
work depends on it would be the borrowed-language failure
`document-conventions.md` warns against.

## Goal

Make every knob that governs a trade-plan decision **settable per evaluation,
observable by the backtest harness, and safe to vary inside a process pool** —
so that a search over the decision surface is possible at all, and so that a
knob the harness cannot see fails a test instead of silently wasting a
pre-registered shot.

Today none of those three properties holds.

## Why — findings

All verified in-session against the working tree at `58deb633`. Each maps to a
component below.

### 1. TRAIN's acceptance gate has been dead code

`scripts/backtest/tune_strategy.py:155` filters candidate cells with
`(s["win_rate"] or 0) >= 80`. That floor was retired by plan v31 on
2026-08-17; `docs/claude/backtest-methodology.md` sets the live bar at
`win_rate >= 50` and says in bold **"do not restore 80% for any run against
the current engine"**, because v31 deleted the fixed per-strategy reward:risk
arithmetic 80 was calibrated to. The confluence population sits near 35%.

So `qualifying` is **always empty**, and line 157 —

```python
ranked = sorted(qualifying or rows, key=lambda r: (r[1]["expectancy_r"] or -9), reverse=True)
```

— falls through to ranking the **entire ungated grid**. Every recent TRAIN run
was pure argmax over an ungated grid, and nothing in the output said so. A
gate that silently disables itself is worse than no gate, because the results
doc still reads as though one applied.

The same retired floor sits in `tune_confluence_gates.py:91`,
`tune_exit_v2.py:86`, `run_confluence_validation.py:146`, and
`run_backtest_range.py:9` (docstring).

### 2. TRAIN selects on an objective VALIDATION does not grade

`tune_strategy.py:157` ranks by `expectancy_r` descending. v72's spec states:
*"Win rate becomes the objective; expectancy becomes a non-inferiority
constraint."* Post-v72 the repo selects the cell that maximises ExpR and then
grades it on ΔWR. v68 is that mismatch in the record: selected for "greatest
pooled ExpR improvement (+0.0104R)", died on the win-rate clause with ExpR
**−0.0097R, opposite sign**.

Resolving this is v76's work. It is recorded here because it is the reason
selection and acceptance must end up sharing one objective definition, which
constrains what `ScanParams` has to carry.

### 3. `plateau_report()` has never been called

`swingbot/core/backtesting/backtest_wf.py:31` defines `plateau_report()` with
a pre-registered `PLATEAU_TOLERANCE_R = 0.03`. v72's spec calls it "mandatory
and disqualifying" at Stage 1. No tuner calls it.

### 4. v72 leaves Stage 1 as prose with no mechanism

v72's Task C3 defines the funnel CLI's interface as `load_arms`, `stage_mde`,
`stage_walkforward`, `stage_validation`, `main`. **There is no
`stage_selection`.** The CLI reads arms "from a JSON file the component's own
measurement script wrote", so selection stays wherever it already was. Neither
the v72 spec nor any of its four plan parts mentions `tune_strategy.py`.

Even with v72 fully closed, Stage 1 is a documented claim that nothing
implements and nothing enforces.

### 5. Two harnesses, different blindness

- `bt.run_backtest` — used by `tune_strategy.py` and `run_backtest_range.py`.
  Per `backtest-methodology.md`'s v34 row, the replay harness **"never calls
  `scanning/engine.py` and cannot see this gate"**. Blind to confluence, RS,
  HTF and regime gating. v34 needed a purpose-built instrument
  (`measure_rs_gate_effect.py`) for exactly this reason.
- `replay_scenarios` (`swingbot/core/backtesting/backtest_scenarios.py:70`) —
  replays the confluence scan and takes gating as an explicit `gates` dict.

A search that grids a knob the chosen harness cannot observe produces cells
that differ only by noise, and an argmax over them is pure luck. This is the
same failure shape as v49's `EFFECTIVE_CONFLUENCE_ENABLED`, where the flag-on
arm rejected every scenario by construction and both TRAIN cells yielded zero
alerts.

### 6. The scan path is half-shared, half-duplicated

`backtest_scenarios.py`'s docstring: scenarios are fed "through the **SAME
plan constructor and exit simulator the live scan uses**" — it imports
`build_confluence_plan`, `primary_strategy_for` and `simulate_exit` from
`plan_engine`. But it reimplements the bar loop, the gating and the cooldown;
it never calls `scan_run._sync_run_scan`.

So a knob consumed inside `plan_engine` is searchable for free once threaded,
while a knob consumed in `scan_run` needs the backtest's parallel
implementation updated too — or the duplication removed.

### 7. Config is global mutable state, and the search already fights it

`swingbot/config.py` exposes values as module globals that `reload()` mutates
in place on SIGHUP. Consumers read `config.X` at call time.

`replay_scenarios`' docstring states the consequence precisely:

> *"Taken directly rather than read from config — the TRAIN grid runs twelve
> different parameter sets in one process, and a config read would make them a
> global the workers fight over."*

`tune_strategy.py` does the thing that docstring refused to do: it mutates
`ef.DEFAULT_PARAMS[strategy]` per cell and restores it in a `finally`. That is
correct only while the loop is serial — which is also why `tune_strategy.py`
has no worker pool while `measure_dcb_veto.py` does.

The seam this spec generalises **already exists** at
`swingbot/core/scanning/scan_run.py:150`:

```python
effective_min_confluence = config.MIN_TARGET_CONFLUENCE_COUNT if min_confluence is None else min_confluence
```

This is not a new idiom. It is the established one, applied past the point
where per-knob keyword arguments scale.

### 8. Three disagreeing sources of truth for the same gates

| Knob | `config` default | `CONFLUENCE_GATES` | `BASE_GATES` |
|---|---|---|---|
| `min_reward_pct` | 3.0 | 3.0 | 3.0 |
| `min_stop_distance_pct` | 2.0 | 2.0 | 2.0 |
| `max_stop_distance_pct` | 7.0 | 7.0 | 7.0 |
| `min_risk_reward` | **1.5** | 1.5 | **0.0** |
| `min_confluence` | **2** | 2 | **1** |

`CONFLUENCE_GATES` (`backtest_scenarios.py:44`) matches what ships.
`BASE_GATES` (`measure_dcb_veto.py:65`) does not: v68's dead-cat-bounce
measurement ran on a population including single-confluence, sub-1.5-RR setups
**the live bot would never alert on**.

This may well have been deliberate — a more permissive population buys N for a
veto test. Nothing at the definition site says so, and nothing tests it.
v72's Task B1 regenerates that population as a committed regression fixture,
so the divergence would be inherited into the fixture the new gate is
calibrated against. **Recorded, not resolved:** whether v68's population was
intentionally permissive is a question for the human partner and for v72's B1,
not something this spec decides.

### 9. The confluence gates are unvalidated defaults, rejected by a retired bar

`backtest_scenarios.py:26` documents `CONFLUENCE_GATES` verbatim:

> *"TRAIN grid found no qualifying config (Task 39); these are unvalidated
> defaults, not a tuned winner. The pre-registered selection rule (per horizon:
> win_rate>=80, expectancy_r>0, N>=30, excl<=50%) failed at every one of the 6
> (min_confluence, min_risk_reward) grid points tested — best observed
> win_rate was 66.4% (need >=80%)."*

That grid ran in July 2026. v31 retired the 80% floor in August 2026 and set
the live bar at 50, precisely because it deleted the arithmetic 80 was
calibrated to. A 66.4% cell clears 50 comfortably.

The bot's confluence gating — the highest-leverage surface on both alert
volume and win rate — therefore runs on values the repo itself labels "NOT the
grid winner", rejected by a threshold that no longer exists, scored against
arithmetic that no longer exists.

**This is flagged, not acted on.** Re-running that grid is *not* obviously
re-running a closed pre-registration, because the engine underneath it was
replaced rather than the answer being unwelcome — but that judgment belongs to
the human partner, and to a new pre-registration written when v75 exists to
run it properly. This spec neither re-runs it nor changes those defaults.

### 10. The cost asymmetry that makes rigour unaffordable

`tune_strategy.py:141-152` calls `run_config` once per grid cell, and
`run_config` loops every ticker × every horizon calling `bt.run_backtest`.
Cost is `cells × tickers × horizons` full backtests, serial, single-process. A
12-cell grid over 89 cached tickers × 10 horizons is ~10,680 full passes.

`measure_dcb_veto.py` replays **once** per ticker/horizon and scores all 12
cells against the same collected rows as a post-filter, with a process pool
(`_ticker_worker`, `collect(..., workers=...)`). Its docstring: "12 cells
scored in ONE replay pass."

The chosen selection policy — broad search with multiplicity priced by a
permutation null over the max statistic — requires re-scoring every cell under
each of ~200 permutations. That is affordable only when scoring a cell is
near-free, and only when cells can be evaluated in parallel. Both properties
depend on parameters being passed rather than read from a mutated global.

## Design

### `swingbot/params.py`

A frozen dataclass `ScanParams` holding the decision surface, sited top-level
beside `config.py` so layering stays acyclic:

```
config  →  params  →  { core.scanning, core.planning, core.backtesting }
```

Both `core.scanning` and `core.planning` consume it, so it cannot live in
either without creating an import cycle or an inverted dependency.

- `ScanParams.from_config()` — the live default, reading current config globals
  once, at the boundary.
- `dataclasses.replace(params, min_confluence=1)` — how a search cell, or a
  measurement script wanting a non-shipped population, states its deviation
  **visibly**.
- Frozen, so no worker can mutate it; picklable, so it crosses a process pool.

`CONFLUENCE_GATES` and `BASE_GATES` collapse into it. A script that wants v68's
permissive population writes an explicit `replace(...)` a reviewer can see,
instead of a hand-typed dict that drifts (finding 8).

### The seam, in two layers

**Shared layer.** `plan_engine.build_confluence_plan` and `simulate_exit` take
`params: ScanParams`. One change; both the live scan and `replay_scenarios`
benefit, because they already share these functions (finding 6).

**Duplicated layer.** Rather than threading `params` into two parallel bar
loops and testing that they agree, **extract the gate evaluation into one pure
function** — `passes_gates(plan, params) -> bool` — that both
`scan_run._sync_run_scan` and `replay_scenarios` call. Parity then holds
structurally. A test that asserts two implementations agree can rot; a single
implementation cannot disagree with itself.

This is the component that makes finding 8 impossible to recur, rather than
merely detectable.

### The searchable surface: a five-way classification

Of 121 `config.FIELDS`, each field is assigned exactly one class. **The
classification is a deliverable, declared in code** — not inferred by a reader,
and not left implicit.

**Class 1 — searchable** (35, enumerated exactly in the plan's Task A2).
Decision knobs a daily-bar replay can observe:
`MIN_TARGET_CONFLUENCE_COUNT`, `CONFLUENCE_DEVIATION_PCT`, `MIN_REWARD_PCT`,
`MIN_STOP_DISTANCE_PCT`, `MAX_STOP_LOSS_PCT`, `MIN_ALERT_CONFIDENCE_LEVEL`,
`DEDUP_TOLERANCE_PCT`, `HTF_CONFLUENCE_ENABLED`, `MTF_ADJACENT_GATE`,
`RS_GATE` and its percentiles, the seven `OPEX_*` fields,
`DATA_DRIVEN_STOPS_ENABLED`, `LEVEL_LIFECYCLE_STOPS_ENABLED`,
`AVWAP_LEVELS_ENABLED`, `PYRAMIDING_ENABLED`, `VOLUME_PROFILE_NODES_ENABLED`,
`REGIME_GATES_ENABLED`, `EARNINGS_BLACKOUT_DAYS`, `MAX_ALERTS_PER_SCAN`,
`SCALE_OUT_ENABLED`, `PLAN_ENGINE_V2`, the four `DCB_*` fields.

**Class-1 membership is provisional until verification item 1 confirms it.**
A knob asserted searchable that fails its observability test is not a bug in
the test — it is the discovery that this harness cannot see that knob, and it
moves to class 3 with the reason recorded. `MIN_ALERT_CONFIDENCE_LEVEL` is the
known open case: confidence scoring lives in `core/scanning/confidence.py` and
it is not yet established that `replay_scenarios` computes it. The test
decides, not this document.

**Class 2 — frozen but injectable.** `MIN_RISK_REWARD_RATIO`,
`MAX_RISK_REWARD_RATIO`, `BREAKEVEN_TRIGGER_FRACTION`, `tp1_fraction`. The
harness must see them; changing them needs its own pre-registration. Carried in
`ScanParams` and flagged frozen, so v75's search engine can refuse to grid them
without an explicit human override. v72's geometry-lock clause exists to catch
exactly this axis being used to manufacture win rate.

**Class 3 — live-only, structurally unmeasurable by a daily-bar replay.**
`NEAR_TP_TIMEOUT_MINUTES`, `NEAR_TP_STALL_CHECK_MINUTES`,
`NEAR_TP_STALL_MAX_FLUCTUATION_PCT`, `QUIET_HOURS_*`, `EXTENDED_HOURS_*`,
`INTRADAY_*`, `SIGNAL_CONFIRMATION_SCANS`, `SESSION_*`, the `NEAR_CLOSE_*`
pair, and the whole `REVERSAL_*` family.

`NEAR_CLOSE_*` and `REVERSAL_*` sit here rather than in class 1 because both
are governed by wall-clock parameters a daily-bar replay cannot represent: in
a daily-bar replay every bar *is* a close, so "near close" has no meaning, and
`REVERSAL_MIN_HOLD_HOURS` / `REVERSAL_COOLDOWN_HOURS` have no sub-daily
resolution to act on. Measuring them needs an intraday instrument, which is
not this one.

This class is the honest
generalisation of finding 5: some knobs cannot be measured by this instrument
at all. Declaring that up front costs one line; discovering it after a
pre-registered shot costs the shot.

**Class 4 — measurement fidelity, never searchable on principle.**
`SLIPPAGE_BPS`, `COMMISSION_PER_TRADE`, `COMMISSION_RISK_BASIS`. They must be
in `ScanParams` because the harness needs them, but tuning them is
self-deception: lowering modelled slippage improves every number and buys zero
real edge. Marked never-searchable and enforced by test, so no future grid can
include them by accident.

**Class 5 — out of scope.** Credentials, Discord/admin plumbing, display,
worker counts, timeouts, `MARKET_DATA_*`. Plus the 15 Account Defaults
(position sizing, heat caps, `DD_THROTTLE_ENABLED`): these are portfolio-level
and belong to `backtest_wf.portfolio_replay`'s unit of analysis, not per-trade
selection. Flagged for a later spec rather than silently dropped.

### The dead-gate fix

The defect at `tune_strategy.py:157` is not the number `80` — it is
`qualifying or rows`, a gate that disables itself in silence. This spec makes
that fallback **loud**: when zero cells qualify, the tuner says so in its
output and in any JSON it writes, and does not present an ungated argmax as a
gated selection.

What the threshold should *become* is v76's decision, because post-v72 "a
feature is judged against the baseline it replaces, never against zero" and the
absolute floor leaves the feature-acceptance path entirely. v74 stops the
silent degradation; v76 replaces the rule.

## Verification

1. **Observability, per knob.** Baseline replay once on a small committed
   fixture; then once per class-1 knob with that knob perturbed. Assert the
   output differs. A knob that can be set but changes nothing **fails**. Knobs
   the fixture cannot exercise (`EARNINGS_BLACKOUT_DAYS` needs an earnings date
   in-window) go on an explicit exempt list **with a stated reason**, so
   "unmeasurable by this instrument" is a maintained, reviewable list rather
   than a silent gap. ~46 replays — slow tier, not the ~27s fast tier.
2. **Classification coverage.** Every one of the 121 fields carries exactly one
   class; every class-1/2/4 field has a `ScanParams` attribute and vice versa.
   Drift fails the suite. Fast tier.
3. **Process-pool safety.** `ScanParams` is frozen; `pickle.loads(pickle.dumps(p)) == p`.
   This is the property the design exists for — v75's max-statistic permutation
   needs a worker pool (finding 10).
4. **Zero observable difference.** `ScanParams.from_config()` reproduces
   today's trade set byte-for-byte on the fixture. This is the release gate:
   per `working-conventions.md` the test is observable difference, not diff
   size, so the bot line takes a patch bump and no live behaviour moves.
5. **Dead-gate loudness.** With zero qualifying cells, the tuner reports the
   condition explicitly and does not rank the ungated grid as though gated.
6. **Full suite once**, as the plan's own final verification task.

Error handling stays thin deliberately: `config._cast` already validates and
casts, an unknown knob in `replace()` raises `TypeError` from the dataclass
itself, and no validation is added for states that cannot occur.

## What this spec deliberately does not do

- **No search engine.** Grid construction, one-pass cell scoring, worker pools
  and fold-train windows are v75.
- **No selection statistics.** Plateau enforcement, the ΔWR objective,
  max-statistic permutation and the `DEAD` verdict are v76.
- **No tuning of anything.** No knob's default changes. No grid is run.
- **No re-run of the July 2026 confluence grid** (finding 9), and no change to
  `CONFLUENCE_GATES`.
- **No change to bot behaviour.** Verification item 4 is the gate on that.
- **No resolution of the `BASE_GATES` divergence** (finding 8) — recorded for
  the human partner and for v72's Task B1.

## Sequencing

v72 closes first (its Tasks B1–B2, C1–C3, D1–D3 remain), because v76 reuses
`acceptance.py`'s `ArmTrade`, `standardised_win_rate`, `bootstrap_delta`,
`mde_win_rate` and `evaluate` rather than reinventing them — which is what
makes selection and acceptance share one objective definition (finding 2).

Then: **v74** (this spec, the seam) → **v75** (search engine) → **v76**
(selection statistics). v74 has standalone value even if v75 and v76 slip: it
collapses three disagreeing gate definitions into one, converts harness
blindness from a post-hoc discovery into a red test, and stops TRAIN
presenting an ungated argmax as a gated selection.
