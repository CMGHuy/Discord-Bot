# Short-side suppression: diagnosis and measurement plan

**Bump:** none (measurement and pre-registration only; any gate change ships under its own plan)
**Edge:** volume
**Status:** Spec. No gate changed, no pre-registration spent, no production change performed.
**Basis:** Session diagnosis 2026-09-21 against the live book, the cached universe and the
shipped gate tables. Feeds `2026-09-20-v97-directional-precision-improvement.md`; supersedes
nothing.

## Problem

The production book is not 90% long. It is **100% long**.

Re-derived from `data/journal.json` this session: 173 closed trades, **173 bullish, 0 bearish**.
Of those, 158 are decided (non-null `r_realized`): win rate 62.0%, mean R +1.537, median R
+1.000, range -1.00 to +5.50. The book spans **2026-08-06 .. 2026-09-21 — roughly six weeks.**

That window matters and is recorded here so no later reader over-reads the headline. Six weeks
of rising tape would produce few shorts under any honest gate, so "zero" is partly sample, not
purely defect. The structural finding below is what survives the caveat: a majority of the
engine cannot emit a short **in any regime**, so the suppression would persist through a
decline.

## Why it happens: four layers

Measured this session by calling `ENTRY_FUNCS` directly (pre-gate) over the 75 cached tickers
across horizons `{4w, 2m, 3m, 6m}`:

**The detectors find shorts.** 9,133 bullish entries vs **2,433 bearish — 21.0% of raw signal
is short.** Short setups are not absent. They are discarded, in four places:

| # | Layer | Site | Effect |
|---|---|---|---|
| 1 | Direction masks | `market/strategy_types.py:214` `STRATEGY_GATES` | 7 of 10 strategies carry `directions: ("bullish",)`. This alone discards **1,948 of 2,433 bearish entries (80.1%)** before any other gate runs. Only Break & Retest, EMA Crossover, RSI Divergence and Elliott Wave can fire short at all. |
| 2 | Shared regime gate | `market/entry_filters.py:49-51` | `bull_regime` = close > MA200 **rising over 20 bars**; `bear_regime` = MA200 **falling over 120 bars** AND close < MA200. A 6x lookback asymmetry. Measured over 106,716 bars / 74 tickers: bull passes **59.0%**, bear **18.4%** — 3.2x. Recomputing bear with the bull's 20-bar slope yields 24.5% (1.3x more bearish bars), so this layer is real but secondary to layer 1. |
| 3 | RS gate | `edge/rs_gate.py` | Its own docstring: `RS_LEADER_PERCENTILE=0` structurally disables the bullish arm, so "in production this gate only ever blocks bearish setups." In the v93 table it removed ~38-67% of every bearish sample. |
| 4 | Universe | `data/watchlist.json` | 76 symbols: US large-cap tech/growth plus `GC=F` and `SI=F`. No structurally weak names. |

Layers 1-3 are code. Layer 4 is configuration and is **out of scope here** (see Non-goals).

## What is already closed

`docs/claude/backtest-methodology.md:150` — **v93 re-derived the bearish arms for all seven
bullish-only masks on TRAIN plus folds. All seven failed the fixed rule.** No VALIDATION was
spent. That row is closed and **must not be re-run**. This spec does not reopen it, does not
re-read its table for a different verdict, and does not propose looser thresholds.

The per-strategy evidence is genuinely bad on its own terms and is recorded here so no future
session mistakes this spec for a rescue attempt: Fibonacci 21.3% WR, VWAP 12.5%, Volume
Profile 25.0%, Support/Resistance 36.2%, MA Ribbon 42.6%, MACD 52.6%, RSI 0.0% (N=10).

One methodological observation, recorded as an observation and **not** as grounds to re-run:
v93 judged each bearish arm through the **horizon mask selected for that strategy's bullish
arm**, which collapsed N before the `N >= 30` clause was applied (MACD 157 -> 19, Volume
Profile 362 -> 12, VWAP 66 -> 8). Whether that changes any verdict is unknown and is not
asked here.

## Relationship to v97

`2026-09-20-v97-directional-precision-improvement.md` is the live roadmap for this area. Two
interactions:

**1. This spec respects v97's boundaries.** v97 states: "Individual stocks in the production
watchlist only. Exclude ETFs, CFDs, and other instruments." and "LONG buys shares; SHORT
borrows shares." Everything proposed below is stocks-only. The inverse-ETF alternative
considered this session is recorded in Rejected alternatives and is **not** proposed.

**2. v97's per-direction contract is currently unsatisfiable for SHORT.** v97 requires:

> "Aim for at least 75% net-profitable positions separately for LONG and SHORT."
> "Retain at least 75% of baseline actionable-plan volume separately for LONG and SHORT."

Baseline SHORT volume is **zero** and baseline SHORT profitability is **undefined** (N=0).
"Retain 75% of zero" is satisfied trivially by changing nothing, and no profitability rate is
estimable. v97 tasks P1 and P2 should absorb this: the SHORT arm needs a *volume floor to
reach*, not a baseline share to retain. This spec's measurements are the input for setting it.

## Genuinely new questions

Two gates in the short path have **never been measured on their own axis**. Neither appears in
the closed-pre-registration table. Each is a new pre-registered hypothesis with its own shot.

**Q1 — Does the RS laggard arm improve bearish expectancy, or harm it?**
`rs_gate.py` records that the *bullish* arm was disabled because it measured negative at every
TRAIN threshold. The *bearish* arm was retained, but no record shows it was ever measured as
improving bearish outcomes. v93 **applied** it as a fixed filter and never tested it. Testing a
filter that has only ever been assumed is a new question, not a re-run.

**Q2 — Is `bear_regime`'s 120-bar MA200 lookback derived, or inherited?**
`bull_regime` uses a 20-bar slope; `bear_regime` uses 120. No result document derives the 120.
It gates every bearish arm in the engine, including the four strategies v93 never masked.
Asking what lookback the evidence supports is a new question about a constant that was never
tuned.

Both questions are **widenings**, not tightenings: each can only loosen or confirm a gate that
currently suppresses volume. Neither can restrict the long path (see Isolation).

## Scope

**In scope:** measuring Q1 and Q2 on TRAIN under current arithmetic (v2 exits, scale-out, TP2,
frictions on); recording results whatever they say; the long-book isolation proof below.

**Non-goals.** Explicitly excluded, each with its reason:

- **Reopening v93.** Closed. No re-derivation of the seven direction masks.
- **ETFs, inverse ETFs, CFDs.** Excluded by v97's agreed boundaries.
- **Watchlist changes.** Layer 4 is configuration; a universe change is a separate decision.
- **Shipping any gate change in this spec.** Measurement first. A change ships under its own
  plan, only if the pre-registered rule clears it.
- **Exit-model work.** v97 P7 owns exits.

## Evaluation contract

Pre-registered before any run, quoted verbatim into the results document, per
`docs/claude/backtest-methodology.md`:

- Window: TRAIN only. VALIDATION is not spent by this spec under any outcome.
- Arithmetic: v2 exits, scale-out, TP2 levels, frictions on. Frozen for the duration.
- A configuration clears only with WR >= 50%, ExpR > 0, decided N >= 30, scratch+timeout share
  <= 50%, and at least two anchored fold years with N >= 15 and positive ExpR.
- Q1 and Q2 are measured **independently**. Neither may borrow the other's evidence.
- A failure is recorded and the component closes. No threshold is loosened, no second grid is
  run on the same question, and the gate keeps its current default.
- If a question clears, the change ships **inert by default** behind a config flag, and
  enabling it is a separate decision with its own record.

## Isolation: the long book must not move

This is a hard requirement, not a preference. Both questions touch only bearish series
(`bear_regime`, and an RS branch that `rs_gate.py` documents as bearish-only in production),
so no long entry should change. That must be **proved, not asserted**.

Known coupling points found this session, each needing an explicit check:

1. **Cohort registry.** `backtesting/cohort_registry.py` keys cells on `direction|regime2_state`
   and `band()` classifies each cell against a pooled `pool_mean_r`. Adding bearish population
   shifts `pool_mean_r`, which can re-band existing **bullish** cells whose own performance is
   unchanged. The registry is frozen JSON, so the risk materialises only at regeneration — do
   not regenerate until this is resolved.
2. **Badge drift.** `analytics/calibration.py:83 badge_drift()` compares live closed trades per
   strategy against the registry. Bearish trades logged under a shared strategy name move that
   strategy's live WR and can raise spurious decay alerts.
3. **Shared-table mutation.** `entry_filters.gate_override()` mutates the global
   `STRATEGY_GATES` dict in place. It must not be used outside tests; in an async bot with
   concurrent scans it can leak into a live scan.

**Verification (the deliverable that discharges this section).** A differential test: run the
scan pipeline over the current watchlist with the bearish change present and absent, and assert
the emitted **long** alerts are identical — tickers, strategies, horizons, entries, stops,
targets, sizes. Plus re-derive the closed book and assert N=158 / WR 62.0% / ExpR +1.537 is
unchanged. Plus `python scripts/dev/testrun.py full` as the implementing plan's single final
verification task.

## Rejected alternatives

**Inverse-ETF basket.** Add PSQ/SH/RWM/DOG to the watchlist and let the already-validated
*bullish* arms trade them, giving downside coverage with no gate touched. Measured this
session and recorded because the evidence is reusable if the boundary is ever revisited:

- On a synthetic -1x SPY series, `bull_regime` passed 50.6% of 2022 bars and ~0% of bars in
  every bull year — the route self-gates to declines with no new flag.
- Hedge quality against an equal-weight series of the 73 cached watchlist names: PSQ corr
  **-0.936**, downside beta **-0.92**; SH -0.910 / -0.79; RWM -0.848; DOG -0.811.
- Liquidity (median daily dollar volume, 2018-06..2025-12): SH $225M, PSQ $136M, RWM $45M,
  DOG $30M. The unleveraged *sector* inverses are untradeable by comparison — MYY $0.2M,
  REK $0.2M, SEF $0.3M, EFZ $0.4M — and hedge this watchlist worse (REK corr -0.615). No
  unleveraged tech inverse exists; PSQ is the tech proxy.

**Rejected because v97 excludes ETFs as trade candidates**, not because the evidence is weak.
Reversing that boundary is the human partner's decision and is not taken here.

**Re-running the v93 grids.** Closed. See above.

## Open decisions for the human partner

1. **Does v97's ETF exclusion stand?** If it does, the inverse-ETF route stays rejected and
   short coverage depends entirely on Q1/Q2 clearing. If the partner wants it revisited, that
   is a revision to v97's boundaries and belongs in v97, not here.
2. **What SHORT volume floor should v97 adopt**, given "retain 75% of baseline" is vacuous at
   a zero baseline?
3. **Should Q1 and Q2 run before or after v97's P1/P2?** They measure the gates that decide
   whether a SHORT population exists to study at all, which argues for before.
