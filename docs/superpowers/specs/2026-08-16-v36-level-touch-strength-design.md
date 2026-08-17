# v36 — Level strength from touch count and recency

Version: ui 1.7.0 · bot 1.1.4
Bump: bot minor (1.4.x → 1.5.0) — which level becomes the target changes, so
trade plans change observably. `ui` none.

## The problem, stated once

This is the **one genuinely missing feature** of the four surveyed in the
TrendSpider brainstorm — the other three were already built.

`swingbot/core/market/levels.py:106`:

```python
class Level:
    price: float
    sources: list
```

A level knows its price and which methods produced it. It does **not** know
whether price has ever actually respected it, how many times, or how recently.

So confidence today answers "how many indicators agree this line exists" but
never "has this line ever held". A level that price sliced straight through
three times scores identically to one that has rejected price twice in the last
month, given the same method count. For a bot whose entire thesis is
support/resistance, that is the central missing piece of evidence.

## Goal

Grade each `Level` by how convincingly price has respected it historically, and
how recently, and feed that grade into level selection and confidence.

## Design

### Correction: the per-bar classifier already exists

Written before reading `edge/factors.py:193`. **`pattern_quality_at_level(df,
idx, level, direction) -> int`** already implements the wick-vs-body rule below,
including the exact rejection/break distinction (`:217-224`), with the comment
*"piercing and CLOSING through is a break, not a rejection, and must not score
like a bounce."*

It is the `candle_quality` input `engine.py::_build_quality_inputs` deliberately
declines to supply, because *"candle_quality needs a specific touch-bar+level
the scan loop doesn't track per plan"*.

So this spec's genuinely new work is narrower than described below: **touch
discovery** (which bars touched a level), **aggregation with recency decay**,
and **a field on `Level`**. The classification table below documents the rule
`pattern_quality_at_level` already implements; it is not a rewrite of it.

One consequence: that function scores 0–10 with **no negative band**, so a break
scores *low*, not negative. The negative signal is supplied at the aggregate
level rather than by editing a function other code already consumes.

### What counts as a touch — wick vs body

Three outcomes when price enters a level's tolerance band, distinguished by
where the bar **closed**:

| Outcome | Definition | Weight |
|---|---|---|
| **Rejection** | Wick penetrates the band, body closes back outside on the level's own side | **Positive** — the level held |
| **Break** | Body closes through the band to the other side | **Negative** — the level failed |
| **Consolidation** | Body closes inside the band | **Neutral** — no information |

This is the most faithful reading of how a level actually behaves, and it is the
reason a bare proximity count is not enough: a proximity count scores a level
that price destroyed as "well tested".

A **break followed by a re-established hold from the other side** is the
polarity-flip case (old resistance becoming support). v1 treats it as a break
for the level's original side and lets the new side accumulate its own
rejections independently. Explicit flip detection is out of scope.

### Recency

Touches decay with age — a rejection from three weeks ago is stronger evidence
than one from eight months ago. Decay is scaled per horizon, consistent with the
rest of `HORIZONS`: a `2w` level cares about recent weeks, a `9m` level about
recent quarters.

### Where the grade is used

Two places, and the distinction matters:

1. **Level selection** — a better-tested level is preferred when choosing the
   target, feeding `select_structural_target()`, introduced by v31 Task 2 and
   now live in `swingbot/core/planning/plan_engine.py`.
2. **Confidence** — touch strength becomes a factor inside v32's merged score.

### Interaction with v31 — the reason this spec is last

`docs/superpowers/plans/implemented/2026-08-16-v31-structural-targets.md`
merged to `main` on 2026-08-17 (`ef15927`), reworking
`select_structural_target()`, which is exactly the function consuming half of
this spec's output.

Task 1 still re-reads the selector as v31 actually left it and adjusts this
design to the real signature, rather than the one assumed here.

### Data cost

Touch history is computed from daily bars already fetched for the scan. The cost
is CPU over existing frames, not new fetches — but it is **per level per
scan**, and a clustered level map has many levels. The plan must measure scan
duration before and after; a scan that no longer completes inside
`SCAN_INTERVAL_MINUTES` is a failure regardless of win rate.

Caching the grade per (ticker, level price band, date) is the expected
mitigation, since it only changes when a new daily bar arrives.

### Config

- `LEVEL_TOUCH_STRENGTH` — checkbox, **default off**; flipped on by a
  VALIDATION pass.

## Validation

New pre-registration. Acceptance: win-rate improvement, alert volume down no
more than **~30%**, **and** scan duration within its existing budget.

The TRAIN sweep must separate the two uses — selection and confidence — because
they can disagree. Preferring better-tested levels may improve win rate while
the confidence factor adds nothing, or the reverse; shipping both on one
aggregate number would hide that.

## What this deliberately does NOT change

- **No new market data.** Daily bars already fetched.
- **No polarity-flip detection** in v1.
- **Clustering is untouched** — grading happens on `Level` objects after
  `_cluster_levels` produces them.
- **Method count is unaffected.** Touch strength grades a level's *quality*, not
  how many methods found it; it must not become a backdoor into the honesty
  gate.

## Risks

- **Overwriting v31.** Mitigated by strict sequencing — this spec does not begin
  until v31 lands, and Task 1 re-reads the selector.
- **Scan-duration regression.** Mitigated by measurement plus per-bar caching.
- **Overfitting the touch definition.** Wick/body/tolerance rules have many
  tunable edges, and a grid over all of them would find something that works on
  TRAIN and nothing else. Mitigation: fix the definition from reasoning, tune at
  most the tolerance band and the decay half-life.
- **Sparse evidence on new levels.** A freshly-formed level has no touch history
  and must score *neutral*, not *bad* — otherwise the system structurally
  prefers old levels, which is not the same as good ones.

## Parallelisation

- **Sequential: v31 lands, then Task 1 (re-read the selector) before
  everything.**
- **Group A (parallel, after Task 1):** the touch-classification function
  (new module or `levels.py` helper) and the per-horizon decay constants
  (`strategy_types.py`) — disjoint files, no contract dependency.
- **Sequential after Group A:** the `Level` grade field and caching, which
  consume both; then selection wiring and the confidence factor, which consume
  the grade.
- **Selection wiring and the confidence factor are themselves parallel** —
  different files (`levels.py` vs `confidence.py`), both consuming a grade
  contract fixed by the previous step.
- **Sequential at the end:** duration measurement, TRAIN, VALIDATION, docs.

## Depends on

**v32 and v31 have both landed** (2026-08-17). v31's
`select_structural_target()` is real, live code -- see this spec's own
"Interaction with v31" section. v32's registry is also real and live, but
`UNIFIED_CONFIDENCE` stays default-off after its TRAIN measurement found
no factor with real positive lift and its VALIDATION run FAILed -- the
confidence factor this spec's Task 5 would plug into has no live effect
today. See `docs/superpowers/plans/2026-08-16-v36-level-touch-strength.md`'s
(still a live plan) own "v32 has also landed, but not as this plan assumed"
section for the full detail.
