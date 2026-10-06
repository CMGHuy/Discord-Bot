# v134 — Fair value gap context diagnostic: structure, confluence, approach

**Version:** ui 1.21.1 · bot 2.0.1 (at writing)
**Bump:** none (a pure module no live path imports, plus a read-only measurement script)
**Edge:** none (integrity) — measurement only; it is the admission test for follow-on `expectancy` arms on how an FVG is weighted or entered

## Why

The partner shared six more "Daiken/BigWhale" pages on 2026-10-06, the Fair
Value Gap chapter. They make one argument: a gap is a place to watch, never a
signal, and four things decide whether it deserves attention.

1. **Displacement.** A gap left by a decisive push matters more than one left
   between small, overlapping candles.
2. **Structure.** A gap matters more inside the sequence trend → break of
   structure → displacement → gap than in the middle of a range.
3. **Location.** A small gap where several other factors meet beats a wide
   gap in noise. Size does not decide quality.
4. **Reaction.** How price comes back decides the read. A fast drive that
   closes through the zone is no reaction; a slowing return is worth more.

Claim 1 is v128's `displacement` arm. Claims 2–4 are measured nowhere:

- `fvg.py` gives every unfilled gap the same vote, whatever made it and
  wherever it sits.
- v121 stores impulse speed, impulse range decay, pullback depth and pullback
  duration in the entry snapshot (`structure.leg_shape_features`), but none of
  them is tied to a gap, and none measures the *return* leg's contraction.
- v130 will label major swings and BOS/CHoCH events, but not which gaps they
  produced.

One more slice comes from the data, not the pages. The handbook's charts are
intraday gold, which trades around the clock. On daily stock bars a 3-candle
gap often contains an overnight or earnings gap, a zone price never traded in
at all. Whether that behaves like an in-session imbalance is unknown.

This spec builds the tags as a causal instrument and measures, on TRAIN only,
whether each claim separates gap outcomes. It gates nothing.

## Not a re-run of a closed or open row

| Row | Why this is different |
|---|---|
| v128 FVG lift audit (`all` / `off` / `displacement`) | v128 tests the FVG *vote* on plan outcomes through the full funnel. v134 scores every gap at first touch and changes no vote. Its displacement row is a gap-level cross-check and cannot reopen v128 (see "What follows") |
| v122 pullback volume dry-up (NO-LIFT at Stage 0) | A volume ratio on pullback strategies and confluence entries. The approach tag here is a true-range ratio on the return leg to a gap, and it gates nothing |
| v121 leg-shape keys | Impulse-leg shape at the entry bar of a trade. v134's approach tag is the return leg to a specific gap, at first touch |
| v130 structure tiers and events | v130 asks whether major structure separates trade outcomes. v134 consumes v130's events to tag gaps; it defines no tier or event |
| v133 liquidity pools and role coverage | Liquidity is v133's subject and is out of scope here |

## Scope

In: a new `swingbot/core/market/fvg_context.py`; a read-only script
`scripts/backtest/measure_fvg_context_diagnostic.py`; one results document.

Out: any change to `fvg.py`, `levels.py`, the confluence vote, plans, alerts,
charts, config flags or stored records; liquidity sweeps and order blocks;
premium/discount position in an impulse leg (v124's leg owns that).

## Dependencies and ordering

- **v128 closed.** v134 uses `fvg.is_displacement_gap` (V128-1) and
  `fvg_attribution.record_ticker` (V128-5). v128 merges its code inert on any
  outcome, so both exist once it closes. v134 runs only after v128's
  closed-table row is written, so nothing here can be read before v128's grid
  and selection are final.
- **v130 implemented.** The structure tag reads v130's snapshot keys.

## Window

- Daily bars, the standard backtest cache, every cached ticker.
- A gap is in the population only if its formation bar is on or after
  2020-01-01 **and** its whole event (formation, first touch, outcome) ends on
  or before 2023-12-31. A gap that would need a later bar to resolve is
  dropped and counted as `censored`.
- The script never loads a bar dated after 2023-12-31 and refuses any window
  argument that touches 2024-01-01 or later. 2024–25 is v128's unspent
  VALIDATION window. Bars before 2020 serve only as lookback history.

## Definitions (bullish shown; bearish mirrors every comparison)

`ATR14` is `indicators.atr(df, 14)`. `i` is the third candle of the pattern,
`m = i − 1` the middle candle.

### Gap

A bullish gap forms at bar `i` when `Low[i] > High[i − 2]`. Its zone is
`bottom = High[i − 2]`, `top = Low[i]`, `mid` their mean. Every such gap is
enumerated at formation. This differs from `find_fair_value_gaps_detailed`,
which returns only the last three untouched gaps per side as of the frame's
last bar.

### First touch

The first bar `τ > i` with `Low[τ] ≤ top`.

- `High[τ] ≥ bottom`: a **touch**. This is the same overlap test `fvg.py` uses
  to drop a gap, so first touch is exactly the last moment the live bot treats
  the gap as a level.
- `High[τ] < bottom`: price jumped the whole zone. Counted as
  `gapped_through`, not scored.
- No such bar within 60 bars: counted as `untouched`, not scored.

### Tags

| Tag | Known at close of | Definition | Buckets |
|---|---|---|---|
| `displacement` | `i` | `fvg.is_displacement_gap(df, gap, k=1.5)` | `yes`, `no` |
| `structure` | `i` | v130's `struct_event_last` for the gap's direction is `bos_with` or `choch_with`, and `struct_event_bars_ago ≤ 1` (the event fired on `m` or `i`) | `bos`, `choch`, `none` |
| `confluence` | `τ` | distinct non-FVG families with a candidate within `levels.CLUSTER_TOLERANCE_PCT` of `mid`, from `collect_candidate_levels(df.iloc[:τ+1], HORIZONS["4w"], Close[τ])` | `0`, `1–2`, `3+` |
| `approach` | `τ` | mean true range of the last third of bars `i+1 … τ` ÷ the first third; undefined below 6 bars (`structure.MIN_LEG_THIRD` per third) | `slowing` (< 1), `not_slowing` (≥ 1), `short` (undefined) |
| `origin` | `i` | `untraded = 1 − overlap([Low[m], High[m]], [bottom, top]) / (top − bottom)` | `intrabar` (0), `partial`, `true_gap` (1) |
| `size` | `i` | `(top − bottom) / ATR14[i]` | quintiles of the window population, per direction |
| `touch_close` | `τ` | where `Close[τ]` sits | `above`, `inside`, `below` |

Families are named by the same mapping `count_confirming_strategies` uses. The
`4w` horizon is frozen because its swing length matches the 20-bar outcome
horizon below; it is a descriptive default, not a searched value.

### Outcome (frozen)

For a touched gap, with `a = ATR14[τ]`:

- `stop = bottom − 0.25 × a`
- `Close[τ] ≤ stop`: **failed on touch**. No entry; counted separately.
- Otherwise `entry = Close[τ]`, `risk = entry − stop`,
  `target = entry + 1.5 × risk`. 1.5 is the floor of the live risk-reward
  band, so break-even hold rate is 40%.
- Bars `τ+1 … τ+20`: **loss** at the first `Low ≤ stop`, **win** at the first
  `High ≥ target`, stop first when one bar does both. Neither within 20 bars
  is a **timeout**, marked at `Close[τ+20]`.

Per bucket the report prints `N`, hold rate (`wins / (wins + losses)`), mean
R over all scored gaps (win `+1.5`, loss `−1`, timeout at its mark), and the
failed-on-touch share. These are gap statistics. They are not the bot's ExpR
and are never quoted as it.

The constants `0.25`, `1.5`, `20` and `60` are frozen module constants
(partner-approved 2026-10-06). A follow-on that wants to search one
pre-registers its own grid.

## Report

### Table A — gap level (primary)

One block per tag: buckets × direction, with the columns above. A census
block before it gives formed, touched, gapped-through, untouched and censored
counts, and the number of distinct ticker-months, since gaps cluster in time
on one ticker.

### Table B — trade level (secondary, confounded)

Baseline `all`-arm plans from `fvg_attribution.record_ticker` whose
`fvg_family` is true, on replay window 2020-01-01..2023-12-31. Each is tagged
by the most recently formed FVG candidate in its level cluster. A live FVG
vote is cast by an untouched gap, so `confluence`, `approach` and
`touch_close` are evaluated at the signal bar instead of at first touch.

Per bucket: N, win rate, ExpR, split by confluence-sourced and
strategy-sourced. Buckets with `N < 30` print `thin` with no ExpR. The header
says the slice is confounded: FVG-tagged plans carry more families by
construction, and every one passed every other gate. Table B carries no
verdict.

### Pre-registered verdict (descriptive, fixed before any run)

Four independent claims, each with the handbook's favourable bucket fixed
here:

| Claim | Favourable | Against |
|---|---|---|
| displacement | `yes` | `no` |
| structure | `bos` or `choch` | `none` |
| confluence | `3+` | `0` and `1–2` |
| approach | `slowing` | `not_slowing` (`short` excluded) |

A claim **earns a follow-on spec** only if, on bullish gaps in Table A, all
hold:

1. Hold rate is higher in the favourable bucket.
2. Mean R is no lower in the favourable bucket.
3. Failed-on-touch share is no higher in the favourable bucket.
4. Both sides have `N ≥ 100` scored gaps.
5. Clauses 1 and 2 hold separately in 2020–21 and in 2022–23, with `N ≥ 50`
   per side in each half.
6. On bearish gaps, clause 1 has the same sign, or a side is under `N = 100`.

Otherwise the claim closes as a no-lift row in
`docs/claude/backtest-methodology.md`, with no budget spent. `origin`, `size`
and `touch_close` are descriptive and carry no verdict: the handbook predicts
no direction for the first, and predicts *no effect* for the second.

No statistic here is inferential. Four one-directional claims are declared in
advance; nothing else in the tables may be promoted to a claim afterwards.

Output: `docs/superpowers/results/YYYY-MM-DD-v134-fvg-context-diagnostic.md`.

## What follows (only for a claim that earns it)

A separate `expectancy` spec per claim, for example an FVG vote conditional on
a structure event, or a slowing-approach condition on a gap entry. Each must:

- freeze its grid without reading this report's buckets
- clear the v72 and v92 gates from Stage −1 to Stage 3 under its own
  pre-registration
- state why it is not a re-run of a closed row

Two claims carry an extra condition:

- **displacement.** v128 owns the displacement vote. If v128 closed that
  mechanism, a pass here does not reopen it; a follow-on must name a mechanism
  outside v128's row (a zone entry, not the vote).
- **approach.** A follow-on must state its difference from v122 and from
  v121's leg-shape keys.

## Code

- `swingbot/core/market/fvg_context.py`, pure and imported by no live path:
  `all_gaps(df)`, `first_touch(df, gap)`, `formation_tags(df, gap)`,
  `touch_tags(df, gap, touch)`, `gap_outcome(df, gap, touch)`, plus the frozen
  constants.
- `scripts/backtest/measure_fvg_context_diagnostic.py`: loads the cache,
  truncates at 2023-12-31, runs both tables, writes the results document.
  It prints flushed progress per ticker, and a percent figure to a log deleted
  on completion if the run passes 15 minutes.

Every function stays below cyclomatic complexity 15. The `no-lookahead` skill
applies to every tag.

## Testing

- `all_gaps` on hand-built frames: a bullish and a bearish gap, no gap when
  the candles overlap, and a count that exceeds
  `find_fair_value_gaps_detailed` on a frame with more than three gaps a side.
- `first_touch`: touch, `gapped_through`, `untouched` at 61 bars.
- Each tag on a hand-built frame per bucket, bearish mirror included;
  `approach` is `short` below 6 bars; `origin` is `intrabar` when the middle
  candle spans the zone and `true_gap` when it does not overlap it.
- `gap_outcome`: win, loss, stop-first on a shared bar, timeout mark,
  failed on touch.
- **Causality:** appending future bars changes no formation tag of an
  already-formed gap and no touch tag or entry of an already-touched one.
- Script: refuses a window touching 2024-01-01; a gap whose outcome would
  need a 2024 bar is `censored`.
- One full-suite run, as the plan's final task.

## Parallelisation

Sequential throughout: instrument → script → run → close-out.

- `fvg_context.py` comes before the script, which consumes every function in
  it. The tags and the outcome function share no symbol but share that one
  file, so they are one task chain, not two agents.
- Tables A and B live in the script's single file, so they are also one chain.
- The run waits on v128's closed row and on v130's snapshot keys. The
  instrument and its tests do not, except the `structure` tag (v130) and the
  `displacement` tag (V128-1).
