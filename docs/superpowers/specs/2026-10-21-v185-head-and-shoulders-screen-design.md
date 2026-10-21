# v185 — Head-and-shoulders screen: four ideas, top and inverse, close and retest

**Version:** ui 1.34.0 · bot 2.14.3 (at writing)
**Bump:** none — four idea modules under `swingbot/core/backtesting/screen/ideas/` and four one-shot screen runs; nothing the bot or admin serves changes.
**Edge:** none (integrity) — four measurements. A `SCREEN-PASS` is evidence for the *trigger* under the generic ATR race only; it would license a later `Edge: volume` strategy spec, where the pattern's own stop and measured-move target are still unmeasured. This spec claims no edge.
**Screen:** exempt (integrity)
**Panel:** technical-analyst, quant-researcher, veteran-trader
**Blocked on:** v182 Parts A and B merged (the short race and its calibration). Nothing in this spec is implemented, counted or run before then — partner decision 2026-10-21: all four ideas go together, after v182.
**Status:** spec written 2026-10-21 from a brainstorm with the partner (source: Daiken/BigWhale infographic "Đọc vị mô hình Vai Đầu Vai", partner-shared 2026-10-21 — the same series as `sweep_reclaim_bos`). Partner decisions: a standalone strategy (not a filter on Break & Retest, not an arm of v182); both directions; both entry triggers as separate ideas; wait for v182 entirely.

## Why

The infographic's thesis, in its own words: *"Ba đỉnh chỉ là hình dạng —
neckline mới là mốc xác nhận quan trọng"* — three peaks are only a shape;
the neckline break is the confirmation. Its trade sequence: neckline break →
retest that fails to reclaim the neckline → short; stop above the retest
high, target the next support; the setup is void once price closes back
above the neckline.

What the repo already measured, and what it never has:

| Piece of the image | In the repo | Record |
|---|---|---|
| Break → retest → rejection entry | `Break & Retest` (`market/entry_filters.py:928`), bearish mirror included | v31 FAIL, v84 NO-LIFT, v129 arm B NO-LIFT |
| Two-peak reversal shape | `Double Pattern` (v69) | NO-LIFT |
| Range breakdown short | v182 (spec 2026-10-21) | not yet run |
| **Five-pivot head-and-shoulders geometry, top and inverse** | nothing (`git grep` finds no H&S or neckline code) | never screened |

So the new claim is the shape: that a neckline break *inside a valid
head-and-shoulders* behaves differently from a plain swing-level break. The
screen tests that claim, and its control (below) tests it against the
no-shape break directly — otherwise a pass would only relearn Break &
Retest.

### How this differs from closed work

- **Not a Break & Retest re-run.** The closed B&R pre-registrations traded
  a `sr_lookback`-bar high/low with no shape condition, under the v1
  instrument. These are new Stage −2 ideas with a five-pivot shape gate,
  raced against the screen's matched null. The closed B&R rows stay closed.
- **Not a Double Pattern re-run.** v69 used two peaks and a TRAIN grid; this
  is three peaks, frozen parameters, no grid. The results doc prints event
  overlap with v69's detector so a pass cannot be a renamed double top.

## Design

### The pattern (top; the inverse mirrors every price comparison)

All inputs are **confirmed** k = 3 fractal pivots from
`market/structure.pivot_confirmations` — a pivot at bar p is known only from
bar p + 3. `confirmed_pivots` keeps only the last two of each kind, so the
idea module builds its own ordered pivot list from `pivot_confirmations`,
appending each pivot at its confirmation bar. Every rule below reads bars
≤ t at bar t (`no-lookahead` skill applies).

1. **Five alternating pivots** LS (high), T1 (low), H (high), T2 (low),
   RS (high): the last five of the alternating sequence. Consecutive pivots
   of one kind collapse to the more extreme one (the higher high, the lower
   low), as a zigzag does.
2. **Head dominance:** `H > max(LS, RS) + 0.5 × ATR14`.
3. **Shoulder balance:** `|LS − RS| ≤ 1.0 × ATR14`. RS below LS is not
   required.
4. **Neckline:** the line through (T1 position, T1 price) and (T2 position,
   T2 price), extrapolated to bar t. Slope cap: `|T2 − T1| ≤ 1.0 × ATR14`,
   so a steep trend leg cannot pose as a neckline.
5. **Prior trend:** at LS's bar, `Close > SMA50` and SMA50 above its value
   10 bars earlier (uptrend for a top; below and falling for the inverse).
6. **Width:** 15 to 80 bars from LS to RS.
7. **Arming and expiry:** the pattern arms on RS's confirmation bar. It is
   cancelled if no neckline break comes within 20 bars of RS, or if a High
   exceeds H first (a Low under H for the inverse). A pivot set arms at most
   once.

ATR14 is read at RS's confirmation bar and frozen for the pattern.

### The two triggers

- **Close (`hs_top_close`, `ihs_close`):** event at the close of the first
  bar after arming whose Close is beyond the neckline at that bar.
- **Retest (`hs_top_retest`, `ihs_retest`):** after the close trigger's
  break bar b, within 10 bars: a bar whose High reaches within
  `0.25 × ATR14` of the neckline (from the broken side), then that bar or the
  next closes back beyond the neckline on the break side — event at that
  close. A Close back on the pattern side of the neckline cancels the setup.

Each pattern fires each trigger at most once.

### The four ideas

| Idea | Direction | Trigger | Race |
|---|---|---|---|
| `hs_top_close` | short | close | v182 short race, `ENTRY = "next_open"`, `RACE = "fixed"`, `CAP = 20` |
| `hs_top_retest` | short | retest | same |
| `ihs_close` | long | close | existing long race, unchanged |
| `ihs_retest` | long | retest | same |

`PARAMS` holds every number above (pivot k 3, head margin 0.5, shoulder
tolerance 1.0, slope cap 1.0, trend lookback 10, width 15–80, expiry 20,
retest window 10, retest tolerance 0.25) and is frozen at commit, before any
count. `SOURCE` cites the infographic; `SUMMARY` states each rule in one
line.

### Shots, nesting and counts — v182's rules, unchanged

Four ideas are four shots, each one-shot under the unchanged pass rule. They
form **two nested families of two**: every retest event follows a close
event of the same pattern. Each results doc prints the family's event
overlap and BH q across the ledger (reported, never gating).

- Both in a family pass: the follow-on spec picks one trigger, citing both.
- One passes: only that trigger may be used, treated as weaker than a lone
  pass, and the spec says the other failed.
- Neither: both closed.

Before any run, `screen_idea.py --count-only` over the full universe for all
four, recorded in `docs/superpowers/results/<date>-v185-counts.md` and
committed before the first run.

- Count ≥ 300: the one-shot run follows, by `backtest-runner`.
- Count < 300: no run, no ledger row, shot unspent; reported to the partner.
  At most one renamed, looser variant per idea, the partner's call, listed in
  the counts note and counted as one family with its parent.
- A run still under 300 after the race's exits: `SCREEN-UNDERPOWERED`,
  closed like a fail.

The retest ideas are the likeliest to fall under 300; that is accepted, not
designed around.

### Descriptive blocks in each results doc, never gating

- **Shape-vs-no-shape control** (the image's own claim): bars with the same
  prior-trend clause whose Close first breaks the last confirmed swing low
  (swing high for the inverse) but which do **not** satisfy the five-pivot
  geometry, through the same race against the same null, as ΔExpR. A pass
  whose ΔExpR is not clearly above this control cannot be credited to the
  shape.
- **SPY regime split:** ΔExpR by SPY above/below its 200-day average.
- **Overlap with v69 Double Pattern events** (share of events within 5 bars
  of a double-pattern event).

### What a pass buys, and what comes after (not this spec)

A `SCREEN-PASS` buys an `Edge: volume` strategy spec that would build the
live plan from the pattern: stop above the retest high (retest trigger) or
the right shoulder (close trigger), target at the neckline minus the
head-to-neckline height (measured move) or the nearest support, whichever
is nearer; the unchanged acceptance funnel; the chart drawing of LS/H/RS
and the neckline. For the short side it must also settle what v182's
follow-on settles: order form, RS-gate bypass, squeeze/earnings/borrow/
uptick-rule risks, a liquidity floor.

A fail closes exactly the frozen definition (these geometry numbers, that
trigger, the fixed 20-bar race), not "head and shoulders" in general.

## Testing

- Pivot sequence: hand-built frames for collapse of same-kind pivots and
  for confirmation lag (a pivot is absent from the list before p + 3).
- Each geometry clause has a frame that fails only that clause (head too
  low, shoulders unbalanced, neckline too steep, no prior uptrend, too
  narrow, too wide, expiry, high above H) — the event fires only on the
  frame satisfying all.
- Close trigger fires once per pattern; retest trigger: touch-and-reject
  fires, close back across cancels, an 11th-bar retest does not fire.
- Inverse ideas are the exact mirror: `ihs_*` on a frame equals `hs_top_*`
  on the price-negated frame (positions identical).
- Truncation stability: `events(df.iloc[:t+1])[-1] == events(df)[t]` on
  random frames (no lookahead).
- Registry test pins direction, `ENTRY` and `RACE` for all four.
- The control and overlap blocks: a fixture frame with known counts.

## Out of scope

- Any live change: strategy registry, scan pipeline, RS gate, masks, charts.
- The pattern's stop, measured-move target and order form (follow-on spec).
- A filter on Break & Retest (option A, not chosen) or an arm on v182
  (option B, not chosen).
- Volume confirmation on the right shoulder or the break — the image does
  not ask for it; adding it would be a different idea with a new name.

## Parallelisation

- **Gate:** v182 Parts A and B merged; the plan starts no earlier.
- **Idea modules:** one shared pattern detector, then the four idea modules
  and their tests — the two families can be written in parallel once the
  detector lands (both call it).
- **Control/overlap blocks** after the detector, in parallel with the ideas.
- **Counts → runs, sequential:** the counts note commits before any run;
  each run is one shot, by `backtest-runner`, one at a time.
