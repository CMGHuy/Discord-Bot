# v32 — Unified confidence score

Version: ui 1.7.0 · bot 1.1.4
Bump: bot minor (1.1.4 → 1.2.0) — the gate that decides which alerts fire
changes population and gains a sixth level; every user sees a different feed.
`ui` patch, for the Settings field range and the retirement of tier labels.

## The problem, stated once

This repo has **two scoring systems**, and the smarter one is advisory.

`swingbot/core/scanning/confidence.py::score_confidence()` produces a 1–5 level
from a method-count base level, a 100-point quality base, and an honesty cap. It
is the **only** thing that gates whether an alert fires
(`MIN_ALERT_CONFIDENCE_LEVEL`, default 3).

`swingbot/core/planning/quality.py::score_plan()` produces a 0–100 score with
frozen E37 weights over `regime`, `htf`, `confluence`, `volume`,
`atr_percentile`, `trigger_distance`, `badge`, plus the edge components `rs`,
`mtf`, `breadth`, `candle` and a `gap` penalty. `PLAN_ENGINE_V2` defaults to
`"on"`, the RS cache is refreshed every scan
(`scanning/engine.py:1101`), breadth is computed (`engine.py:1068`), and real
per-item values reach it (`engine.py:1251`). It runs. It gates **nothing**.

The codebase says so itself, at `swingbot/commands/scanning.py:1163`:

> **HONEST GAP** … this codebase has no 0-100 quality_score gate on whether an
> item becomes an alert -- quality_score is purely informational/ranking. The
> only real gate that controls "does this item qualify at all" is
> MIN_ALERT_CONFIDENCE_LEVEL (a 1-5 tier).

So relative strength, multi-timeframe alignment, market breadth and
anchored-VWAP-derived levels are all computed, all scored, and then **not
permitted to stop a single bad alert**. The gate that fires alerts knows nothing
about any of them.

This spec merges the two into one score that both grades *and* gates.

## Goal

One 0–100 score, derived from both scorers' inputs, mapping to a **1–6**
confidence level, gating alerts through the existing
`MIN_ALERT_CONFIDENCE_LEVEL` setting.

## Design

### The merged score

Two kinds of evidence stay structurally separate, because collapsing them is the
failure mode the current honesty gate exists to prevent:

- **Base level from method count** (unchanged in principle). How many
  independent methods agree on the target is evidence of a different kind from
  how favorable the context is. It remains the base, and the honesty cap remains
  on top of it.
- **Quality points (0–100)** from a single merged factor set, drawn from both
  scorers.

Candidate merged factor set (final weights are an output of this spec, not an
input — see Validation):

| Factor | Source today |
|---|---|
| Target distance quality | `confidence.py` |
| Stop level confluence | `confidence.py` |
| Market regime alignment | both (`confidence.py` + `quality.component_regime`) |
| ADX trend strength | `confidence.py` |
| MACD momentum alignment | `confidence.py` |
| RSI trend alignment | `confidence.py` |
| Squeeze / volume breakout | `confidence.py` |
| Candlestick pattern | both |
| **Relative strength** | `quality.rs_points` — **newly gating** |
| **MTF alignment** | `quality.mtf_points` — **newly gating** |
| **Market breadth** | `quality.breadth_points` — **newly gating** |
| HTF bias | `quality.component_htf` |
| Volume ratio | `quality.component_volume` |
| ATR percentile | `quality.component_atr_percentile` |
| Trigger distance | `quality.component_distance` |
| Badge status | `quality.component_badge` |
| Gap penalty | `quality.gap_penalty` |

Overlaps are deliberate in this table and must be **resolved to one factor
each** during implementation — `regime` and `candle` are computed by both
scorers today, and trend/momentum is triple-counted across ADX, MACD and
HTF/MTF. Task 1 of the plan is the reconciliation, and it is the most important
task in this spec: shipping the union of both factor sets without deduplication
would weight trend context roughly three times.

### Levels 1–6

`LEVELS` in `confidence.py` becomes six bands. **Level 6 is conditional**: it
ships only if the TRAIN measurement finds a population that clears **both**

1. **≥100 TRAIN samples**, and
2. a **Wilson score interval** whose lower bound still supports the elite claim
   — the point estimate alone is not sufficient.

If no population clears both, this spec ships **1–5** and records the negative
result. A 100%-win-rate tier on six trades is not a tier.

Level 6 carries its own method-count floor in the honesty gate, at least as
strict as Level 5's current 3+.

### What is retired

**A/B/C `tier` is removed.** Confidence levels become the single vocabulary
across embeds, admin UI and code. `QualityResult.tier` and `_tier()` go away.

This invalidates the offline **decile audit** table that is the stated evidence
behind the current A/B/C thresholds, and the **E43 ablation harness** judges
components individually against that structure. Both must be re-pointed at the
merged score **within this spec** — not deferred. Losing the audit without
replacing it would leave the surviving thresholds unjustified, which is worse
than the duplication being removed.

### Config

`MIN_ALERT_CONFIDENCE_LEVEL` **keeps its name and its default of 3**, and gains
`6` as a legal value. No live `.env` needs to change at deploy. The
`config.Field` entry's `max` moves 5 → 6, which propagates to the admin UI
Settings page automatically.

Level thresholds are recalibrated so that a default of 3 admits an alert
population near today's — the level numbers keep roughly their current meaning
rather than silently becoming stricter or looser.

### Rollout

**No shadow period.** The TRAIN/VALIDATION gate is the safety net. This is a
deliberate departure from how `PLAN_ENGINE_V2` shipped, and it places the whole
burden of proof on the pre-registration being genuine: **the VALIDATION gate is
written down before the VALIDATION run, and is not revised after seeing the
result.** A failed VALIDATION means the merged score does not flip on — it does
not mean re-tuning until it passes.

Ships **default-OFF** behind a flag; flips ON only on a VALIDATION pass.

## Validation

Follows `docs/claude/backtest-methodology.md`. New pre-registration required.

- **Weights derived from TRAIN outcomes**: each factor's measured win-rate lift
  across the TRAIN window, weighted by predictive power. Not a fitted
  regression — weights stay legible integers, because the breakdown renders
  verbatim in embeds and a row must mean something a human can read.
- **One VALIDATION shot** against the pre-registered gate.
- **Acceptance**: win rate improves versus the current gate, with alert volume
  down no more than **~30%**. A configuration that filters harder must justify
  it with a proportionally larger win-rate gain, stated in the
  pre-registration.
- Sweeps chunked per-factor and dispatched via the `backtest-runner` subagent;
  no casual full grids.

## What this deliberately does NOT change

- **The honesty gate stays.** Method count still caps the level. Restructuring
  the points beneath it does not license reaching Level 5 or 6 on context
  alone.
- **The method-count base level stays.** It is not folded into the additive
  pool.
- **No new market data.** Everything in the merged factor set is already
  computed during a scan. This spec adds no fetches and no dependencies.
- **`MIN_ALERT_CONFIDENCE_LEVEL`'s default stays 3.** Level 6, if it ships, is
  opt-in.
- **Plan Engine v2 is not removed.** Only its scoring role is unified;
  `build_confluence_plan` and the rest are untouched.

## Risks

- **Tier retirement removes the decile audit's structure.** Mitigation: re-point
  the audit and the E43 ablation harness in the same spec. If that proves larger
  than expected, it is a signal to split, not to defer.
- **No shadow period** means the flip is the first live exposure. Mitigation:
  genuine pre-registration, default-OFF ship, and an easy revert (single flag).
- **Factor double-counting** across the merged set is the single most likely way
  this spec makes win rate *worse*. Mitigation: reconciliation is Task 1 and
  gates all later work.
- **Docs lag badly.** `docs/strategy.md` still describes 5 horizons and 8 level
  methods; reality is 10 horizons plus AVWAP, RS, breadth and badges. This spec
  fixes the scoring sections it touches.

## Parallelisation

- **Sequential: Task 1 (factor reconciliation) before everything.** Every later
  task consumes the reconciled factor set; starting weight derivation or the
  level-band work before the set is fixed means redoing both.
- **Group A (parallel, after Task 1):** the TRAIN measurement harness and the
  `LEVELS` / config-range changes — disjoint files
  (`scripts/`… vs `confidence.py` + `config.py`), no contract dependency.
- **Sequential after Group A:** weight derivation (consumes the harness),
  then level-threshold recalibration (consumes the weights), then the single
  VALIDATION run (consumes both).
- **Sequential: tier retirement before the audit/ablation re-point** — the
  harnesses assert against the structure being removed.
- **Group B (parallel, at the end):** docs updates and embed/admin-UI label
  changes — disjoint files, both consume the finished score.

## Downstream

v33 (MTF), v34 (RS), v35 (AVWAP) and v36 (level touch-count) all depend on this
spec landing: each either promotes a factor this spec unifies, or adds a new one
into the budget this spec establishes.
