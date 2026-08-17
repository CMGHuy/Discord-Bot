# v33 — Multi-timeframe trend alignment

Version: ui 1.7.0 · bot 1.1.4
Bump: bot minor (1.2.x → 1.3.0) — a new hard gate removes alerts that fire
today; the feed changes observably. `ui` none.

## The problem, stated once

Every ticker is scanned across all 10 horizons, and each horizon is scored
independently. Nothing stops a `2w` bullish scenario firing on a ticker whose
`4w` and `3m` structure is clearly rolling over. Countertrend swings are among
the most reliable ways to depress win rate, and this bot currently has no
horizon-to-horizon check at all.

It has *two other* trend signals, which is the complication:

- `swingbot/core/edge/factors.py::mtf_alignment(daily_df, direction) -> int` —
  a **weekly-frame** alignment score (0–3), fed into quality scoring at
  `scanning/engine.py:511`.
- `get_htf_bias(df, horizon_key)` — a higher-timeframe bias, fed in as the
  `htf` component.

Neither is a comparison between *this bot's own horizons*. Adding a third trend
signal without subsuming at least one of the existing two would triple-count
trend context.

## Goal

Two horizon-to-horizon checks, with different strictness:

1. **Adjacent-horizon check — hard gate.** The next horizon up must agree with
   the scenario's direction, or the scenario is not built.
2. **Macro-anchor check (6m) — confidence penalty.** Disagreement with the `6m`
   horizon costs points but never blocks. A 2-week swing against the 6-month
   trend is normal and tradeable.

## Design

### Trend definition

A horizon is bullish when its own `ema_fast > ema_slow`, bearish otherwise —
using that horizon's existing `ema_fast`/`ema_slow` from `HORIZONS`
(`swingbot/core/market/strategy_types.py`). No new constants, and consistent
with how the bot already thinks per horizon.

### Adjacent pairing

Chained across the 10 horizons in `HORIZONS` order: `2w`→`4w`, `4w`→`2m`,
`2m`→`3m`, `3m`→`4m`, … `8m`→`9m`.

**`9m` has no horizon above it** and is exempt from the adjacent gate. This is
an exemption, not a silent pass — it is logged and surfaced as "no higher
horizon" rather than as an alignment that succeeded.

### Macro anchor

Fixed at **`6m`**, for every horizon `2w`–`5m`. Horizons `6m`–`9m` have no macro
check (a horizon cannot anchor to itself or to something shorter) and fall back
to the adjacent gate alone. Same rule: exemption is logged distinctly from
agreement.

The anchor is a **constant in this spec, not a config field.** If the TRAIN
sweep shows the choice matters, promoting it to `.env` is a follow-up, not
speculative surface area now.

### Reconciliation with existing signals — do this first

Task 1 of the plan decides, from measurement rather than taste, which of
`factors.mtf_alignment` (weekly-frame) and `get_htf_bias` the new adjacent check
**subsumes**, and removes it. Acceptable outcomes:

- Adjacent-horizon check replaces `mtf_alignment`; `htf_bias` stays.
- Adjacent-horizon check replaces `htf_bias`; `mtf_alignment` stays.
- Both are genuinely independent of the new check and all three stay — allowed
  only with measured evidence of low correlation, recorded in the spec.

Shipping all three on unexamined assumption is not an acceptable outcome.

### Where it plugs in

The adjacent gate is a **pre-scenario gate**, in the same class as the
volatility floor and `MIN_STOP_DISTANCE_PCT` — the scenario is not built, rather
than built and scored low. The macro penalty is a factor inside the v32 merged
score.

### Config

- `MTF_ADJACENT_GATE` — checkbox, **default off**, flipped on only by a
  VALIDATION pass (per v32's rollout rule).

The macro-anchor penalty needs no flag; it is a weight inside the merged score.

## Validation

New pre-registration. Acceptance: win-rate improvement with alert volume down no
more than **~30%**. This is the gate most likely to breach that ceiling — an
adjacent-horizon agreement requirement is strict — so the TRAIN sweep must
report volume loss per horizon, not just in aggregate. If `2w` alone loses 60%
while the rest lose 10%, the honest answer may be a horizon-scoped gate.

## What this deliberately does NOT change

- **No new market data.** All 10 horizons' EMAs are already computed per scan.
- **The macro anchor never blocks.** Only the adjacent check gates.
- **`9m` and `6m`–`9m` exemptions are not treated as passes** in logging or
  scoring.

## Risks

- **Triple-counted trend context** if reconciliation is skipped — the single
  biggest risk here, hence Task 1.
- **Volume collapse on short horizons.** Mitigation: per-horizon volume
  reporting in the TRAIN sweep, horizon-scoped gate as the fallback design.
- **Whipsaw at EMA crossovers.** A horizon whose EMAs are nearly equal flips
  direction on noise. Mitigation: measure whether a neutral band around the
  crossover is needed; add one only if the data asks for it.

## Parallelisation

- **Sequential: Task 1 (reconciliation) before everything** — later tasks either
  add to or replace a signal Task 1 removes.
- **Group A (parallel, after Task 1):** the adjacent-gate implementation
  (`scanning/engine.py` pre-scenario path) and the macro-penalty factor
  (`scanning/confidence.py` merged score) — disjoint files, no shared symbol.
- **Sequential after Group A:** TRAIN sweep, then the single VALIDATION run.
- **Sequential at the end:** docs + embed/explain surfacing, which consume the
  finished behavior.

## Depends on

**v32 landed** (2026-08-17) but not as this line assumed: the merged-score
registry is real, live code, but `UNIFIED_CONFIDENCE` stays default-off --
v32's TRAIN measurement found no factor with real positive win-rate lift,
its own `FACTORS` list ships with only one inert factor, and its one-shot
VALIDATION run FAILed. **There is no point budget v32 established** for
this factor to draw from. See `docs/superpowers/plans/
2026-08-16-v33-mtf-trend-alignment.md`'s (still a live plan, not moved to
`implemented/`) own "v32 landed, but not as this plan assumed" section for
the full detail; not re-derived here.
