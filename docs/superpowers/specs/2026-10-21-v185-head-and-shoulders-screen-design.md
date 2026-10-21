# v185 — Head-and-shoulders screen: four ideas, top and inverse, close and retest

**Version:** ui 1.34.0 · bot 2.14.3 (at writing)
**Bump:** none — four idea modules under `swingbot/core/backtesting/screen/ideas/` and four one-shot screen runs; nothing the bot or admin serves changes.
**Edge:** none (integrity) — four measurements. A `SCREEN-PASS` that also earns shape credit (below) is evidence for the *trigger* under the generic ATR race only; it would license a later `Edge: volume` strategy spec, where the pattern's own stop and measured-move target are still unmeasured. This spec claims no edge.
**Screen:** exempt (integrity)
**Panel:** technical-analyst, quant-researcher, veteran-trader
**Blocked on:** v182 Parts A and B merged (the short race and its calibration). Nothing in this spec is implemented, counted or run before then — partner decision 2026-10-21: all four ideas go together, after v182.
**Status:** spec written 2026-10-21 from a brainstorm with the partner (source: Daiken/BigWhale infographic "Đọc vị mô hình Vai Đầu Vai", partner-shared 2026-10-21 — the same series as `sweep_reclaim_bos`). Partner decisions: a standalone strategy (not a filter on Break & Retest, not an arm of v182); both directions; both entry triggers as separate ideas; wait for v182 entirely. Panel applied 2026-10-21 (see `## Panel review`).

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
| Break → retest → rejection entry | `Break & Retest` (`market/entry_filters.py:928`), bearish mirror included | v31 FAIL, v84 NO-LIFT, v104-a bullish OPEN (sealed-thin), v129 arm B NO-LIFT |
| Break of market structure | v127 MSB entries; `sweep_reclaim_bos` (same infographic series) | v127 closed; `screen-sweep_reclaim_bos` SCREEN-FAIL |
| Two-peak reversal shape | `Double Pattern` (v69) | NO-LIFT |
| Range breakdown short | v182 (spec 2026-10-21) | not yet run |
| **Five-pivot head-and-shoulders geometry, top and inverse** | nothing — `chart_patterns.py` holds only `dead_cat_bounce`; no H&S, triple-top or neckline code anywhere | never screened |

So the new claim is the shape: that a neckline break *inside a valid
head-and-shoulders* behaves differently from a plain swing-level break. The
screen tests that claim, and the frozen shape-credit rule (below) tests it
against the no-shape break directly — otherwise a pass would only relearn
Break & Retest or MSB.

### How this differs from closed work

The new mechanism is the five-pivot shape gate; every closed row below
traded a level or structure break without it. The closed rows stay closed.

- **Break & Retest (v31, v84, v104-a, v129):** a `sr_lookback`-bar
  high/low, no shape, v1 instrument. v104-a's unspent shot is untouched.
- **v127 MSB and `sweep_reclaim_bos`:** a break of the last swing level,
  no shape. Their events are printed as overlap (below).
- **Double Pattern (v69):** two peaks and a TRAIN grid; this is three
  peaks, frozen parameters, no grid.

## Design

### Parameter provenance

Every number below comes from textbook head-and-shoulders conventions and
the infographic, set on 2026-10-21 with no 2010–2019 chart, count or result
looked at. The panel's geometry changes were folded in the same day, before
any `--count-only`; this commit is the one frozen timestamp.

### The pattern (top; the inverse mirrors every price comparison)

All inputs are **confirmed** k = 3 fractal pivots from
`market/structure.pivot_confirmations` — a pivot at bar p is known only from
bar p + 3. `confirmed_pivots` keeps only the last two of each kind, so the
idea module builds its own ordered pivot list from `pivot_confirmations`,
appending each pivot at its confirmation bar. ATR is `indicators.atr`
(Wilder, 14), never a local variant. Every rule below reads bars ≤ t at
bar t (`no-lookahead` skill applies). A bar without full SMA50/ATR warm-up
before LS gives no pattern.

1. **Five alternating pivots** LS (high), T1 (low), H (high), T2 (low),
   RS (high): the last five of the alternating sequence. Consecutive pivots
   of one kind collapse to the more extreme one (higher high, lower low);
   on an exact tie the later pivot is kept.
2. **Ordering:** T1 < min(LS, H) and T2 < min(H, RS).
3. **Head dominance:** `H > max(LS, RS) + 0.5 × ATR`.
4. **Shoulder balance:** `|LS − RS| ≤ 1.0 × ATR`. RS below LS is not
   required.
5. **Neckline:** the line through (T1 position, T1 price) and (T2 position,
   T2 price), extrapolated to bar t. Slope cap: `|T2 − T1| ≤ 1.0 × ATR`.
6. **Depth:** H minus the neckline at H's position ≥ `2.0 × ATR`; LS and RS
   each ≥ `0.5 × ATR` above the neckline at their own positions — a flat
   triple top or chop with a bump does not pass.
7. **Prior trend:** at LS's bar, `Close > SMA50` and SMA50 above its value
   10 bars earlier (uptrend for a top; below and falling for the inverse).
8. **Width:** 15 to 80 bars from LS to RS.
9. **Arming:** at c = RS's confirmation bar (RS + 3). If any Close in
   (RS, c] is already beyond the neckline, the pattern is discarded — a
   stale break never fires.
10. **Expiry:** cancelled if no neckline break by c + 20, or if a High
    exceeds H first (a Low under H for the inverse). The neckline is thus
    extrapolated at most 23 bars past RS. A pivot set arms at most once.

ATR is read at c and frozen for the pattern.

### The two triggers

Both are **close-then-open signals**: the event is known at a daily close
and the race enters at the next open. Neither tests a resting order at the
neckline, and nothing here says how a retest limit order would fare.

- **Close (`hs_top_close`, `ihs_close`):** event at the close of the first
  bar b in (c, c + 20] whose Close is beyond the neckline at b.
- **Retest (`hs_top_retest`, `ihs_retest`):** after b, the first bar r in
  b + 1 .. b + 10 whose High reaches `neckline − 0.25 × ATR` or above (an
  overshoot counts). If `Close[r]` is still beyond the neckline on the break
  side, the event is at r's close. If `Close[r]` is back on the pattern side,
  the setup is cancelled. A High above H before r also cancels. No bar
  after r is examined.

Each pattern fires each trigger at most once.

### The four ideas

| Idea | Direction | Trigger | Race |
|---|---|---|---|
| `hs_top_close` | short | close | v182 short race, `ENTRY = "next_open"`, `RACE = "fixed"`, `CAP = 20` |
| `hs_top_retest` | short | retest | same |
| `ihs_close` | long | close | existing long race, unchanged |
| `ihs_retest` | long | retest | same |

**Fills (pinned, not inherited):** `next_open` entry at the open of t + 1,
with the race's existing gap rules (an open past the stop exits at the open)
and `frictions.py` base slippage once per fill. v182's 2× stop-market
multiplier is for level-mode resting orders and does **not** apply. Events
and matched-null bars get the identical fill rule. The short side also pays
v182's borrow fee, so the two directions carry different costs. Each results
doc prints mean friction in R for its direction. Each doc also says its
verdict rests on that direction's race calibration (v182's short A/A doc for
the tops, the existing long calibration for the inverses). Verdicts are never
pooled across directions.

`PARAMS` holds every number above (pivot k 3, head margin 0.5, shoulder
tolerance 1.0, slope cap 1.0, head depth 2.0, shoulder depth 0.5, trend
lookback 10, width 15–80, expiry 20, retest window 10, retest tolerance
0.25) and is frozen at this commit. `SOURCE` cites the infographic;
`SUMMARY` states each rule in one line.

### Shots, families and counts

Four ideas are four shots, each one-shot under the unchanged pass rule. They
form **two nested families of two**: every retest event follows a close
event of the same pattern. **All looks share one BH family:** the four ideas,
any renamed variant (below, at most four), and any later head-and-shoulders
idea under any name. That is at most eight looks from this spec. Every
results doc cites `ledger_qvalues` (`instrument/stats.py:226`) over the
family. The q values are reported, never gating.

- Both in a family pass: the follow-on spec picks one trigger, citing both.
- One passes: only that trigger may be used. "Weaker" has one operational
  meaning: the follow-on spec quotes the family q in its `## Why` and says
  the sibling failed.
- Neither: both closed.

Before any run, `screen_idea.py --count-only` over the full universe for all
four, recorded in `docs/superpowers/results/<date>-v185-counts.md` and
committed before the first run. For each idea the note prints the count,
expected events per year, and the paired minimum detectable ΔExpR at that N.
That way the partner sees the power before a shot is spent. The pass rule is
unchanged.

- Count ≥ 300: the one-shot run follows, by `backtest-runner`.
- Count < 300: no run, no ledger row, shot unspent; reported to the partner.
  At most one renamed, looser variant per idea, the partner's call, listed in
  the counts note and inside the one BH family.
- A run still under 300 after the race's exits: `SCREEN-UNDERPOWERED`,
  closed like a fail.

The retest ideas are the likeliest to fall under 300. That is accepted, not
designed around. A close-only pass says nothing about waiting for a retest
in live use.

### Shape credit (frozen; this gates what a pass buys)

Each idea has a **no-shape control** that matches its population except for
the geometry:

- **Level:** the last confirmed swing low L (swing high for the inverse),
  flat, at the bar it confirms; the anchor high is the last confirmed swing
  high before L.
- **Trend clause** read at that anchor high, exactly as clause 7 reads it
  at LS.
- **Arming/expiry:** arms at L's confirmation bar, expires 20 bars later or
  on a High above the anchor high, and is discarded on a stale close beyond L
  before arming.
- **Trigger:** the close control uses the close rule at L. The retest
  control uses the retest rule at L (a Break & Retest mechanism).
- **Exclusion:** bars where a valid five-pivot pattern is armed are
  excluded. Partial geometry (for example, balanced shoulders with too
  shallow a head) stays in the control, since it is "no shape" by
  definition.

The control runs through the same race and the same matched null.
**Shape credit** = the week-cluster bootstrap 95% lower bound
(`week_cluster_bootstrap`, `instrument/stats.py:57`) of
`ΔExpR_idea − ΔExpR_control` is above 0. **A `SCREEN-PASS` without shape
credit does not license the follow-on spec**: the idea is recorded as a pass
of the trigger with no shape credit, and that is a Break & Retest/MSB
question, which stays closed.

### Descriptive blocks in each results doc, never gating

- **Break extension:** entry open minus the neckline at b, in ATR,
  distribution. This shows whether a pass rides chase entries.
- **Next-open gap:** share of events whose next open gaps more than
  0.5 × ATR with and against the trade.
- **Overlap:** share of events within 5 bars of a v69 Double Pattern, v127
  MSB, `sweep_reclaim_bos` or Break & Retest event.
- **SPY regime:** ΔExpR by SPY above/below its 200-day average, and the
  regime mix of events against the null.
- **Earnings:** share of events with an earnings date inside b .. t + 20,
  where the earnings calendar covers the bar; uncovered events are counted
  separately.

### What a pass with shape credit buys (not this spec)

An `Edge: volume` strategy spec. **The screen's 1.5 ATR stop is not the
pattern's stop, so a pass does not transfer to it;** that spec measures its
own geometry. It would build the live plan from the pattern:
- **stop:** above the right shoulder (close trigger) or above the retest
  bar's high (retest trigger), the latter known at the event close;
- **target:** neckline minus the head-to-neckline height, or the nearest
  support, whichever is nearer;
- the unchanged acceptance funnel, and a chart drawing of LS/H/RS and the
  neckline.

It must also settle:
- **Alert timing:** the alert goes out after the close and the order rests
  overnight; how long that order stays valid.
- **Gaps at the open:** the maximum chase when the open gaps past the signal
  close (in ATR), and a skip when the open is past the target or the stop.
- **Regime:** whether a top is traded only when SPY is below or rolling over
  its 200-day, given the RS-gate bypass question.
- **Shorts:** what v182's follow-on settles — order form, RS-gate bypass,
  squeeze/earnings/borrow/uptick-rule risks, and a liquidity floor.

A fail closes exactly the frozen definition (these geometry numbers, that
trigger, the fixed 20-bar race), not "head and shoulders" in general. Any
later H&S idea joins this BH family.

## Testing

- Pivot sequence: hand-built frames for collapse of same-kind pivots
  (including the tie rule) and confirmation lag (a pivot is absent from the
  list before p + 3).
- Each geometry clause has a frame that fails only that clause (ordering,
  head margin, shoulder balance, slope cap, head depth, shoulder depth,
  trend, too narrow, too wide, stale break before arming, expiry, high above
  H). The event fires only on the frame satisfying all.
- Close trigger fires once per pattern. Retest trigger: touch with a close
  beyond fires at r; touch with a close back on the pattern side cancels; an
  overshooting High counts; an 11th-bar touch does not fire.
- Inverse ideas mirror the tops on **tie-free** frames: `ihs_*` on a frame
  equals `hs_top_*` on the price-negated frame (positions identical). The
  fractal rule's `>`/`>=` asymmetry (`structure.py:37-38`) is pinned by its
  own test, not by the mirror test.
- Truncation stability: `events(df.iloc[:t+1])[-1] == events(df)[t]` on
  random frames (no lookahead).
- Registry test pins direction, `ENTRY` and `RACE` for all four. A fill test
  pins base slippage (no 2× multiplier) on a `next_open` short event and its
  null bar.
- Control: a fixture frame with known control events (close and retest),
  the armed-pattern exclusion and the shape-credit bound computed on known
  numbers. Overlap and descriptive blocks: fixture frames with known counts.

## Out of scope

- Any live change: strategy registry, scan pipeline, RS gate, masks, charts.
- The pattern's stop, measured-move target and order form (follow-on spec).
- A filter on Break & Retest (option A, not chosen) or an arm on v182
  (option B, not chosen).
- Volume confirmation on the right shoulder or the break — the image does
  not ask for it; adding it would be a different idea with a new name.
- A trend-strength measure into LS beyond clause 7 (panel advisory,
  rejected: a further free number, and clause 7 plus the depth clause
  already require a reversal from an uptrend).

## Parallelisation

- **Gate:** v182 Parts A and B merged; the plan starts no earlier.
- **Detector first:** the shared pattern detector and pivot sequence. Both
  families and the control call it.
- **Then in parallel:** the four idea modules with their tests; the control
  and shape-credit computation; the descriptive blocks.
- **Counts → runs, sequential:** the counts note commits before any run;
  each run is one shot, by `backtest-runner`, one at a time.

## Panel review

2026-10-21, on 9eaec294. Roles: technical-analyst (sonnet), quant-researcher
(opus), veteran-trader (sonnet).

BLOCKING

- quant-researcher 1: no frozen rule for "clearly above the control", or for what a pass without it buys -- applied (shape credit = week-cluster bootstrap lower bound of ΔExpR_idea − ΔExpR_control > 0; a pass without it does not license the follow-on).
- veteran-trader 1: next-open fill and slippage rule for these ideas unstated -- applied (base slippage once per fill, no 2× level multiplier, identical for events and null, pinned by a test).
- veteran-trader 2: daily-bar retest is not a resting order -- applied (both triggers stated as close-then-open signals; retest bar's high known at the event close; follow-on settles overnight order validity).

ADVISORY

- technical-analyst 1: geometry admits a triple top -- applied (head depth ≥ 2 ATR, shoulders ≥ 0.5 ATR above the neckline).
- technical-analyst 2: arming vs confirmation lag ambiguous -- applied (arm at RS + 3; a stale close beyond the neckline discards; expiry from c).
- technical-analyst 3: retest wording contradictory -- applied (event only at the touch bar's close; close back cancels; overshoot counts; High above H cancels).
- technical-analyst 4: neckline extrapolation unbounded; trough ordering unstated -- applied (break by c + 20 bounds it; ordering clause 2).
- technical-analyst 5: prior trend tested only at LS -- partly applied (warm-up stated); trend-strength measure rejected: another free number, and the depth clause plus clause 7 already require a reversal.
- technical-analyst 6: chase entries -- applied (break-extension block).
- technical-analyst 7: retest control should be a break-retest -- applied.
- technical-analyst 8: ATR undefined -- applied (`indicators.atr`, Wilder).
- technical-analyst 9: mirror test vs fractal tie asymmetry -- applied (tie-free frames, tie rule, own asymmetry test).
- technical-analyst 10: verify no existing H&S/triple-top code -- applied (checked: `chart_patterns.py` holds only `dead_cat_bounce`).
- quant-researcher 2: control population mismatched -- applied (level, trend anchor, arming, expiry and exclusion matched).
- quant-researcher 3: look count and "weaker" undefined -- applied (one BH family, at most eight looks; "weaker" = quote family q and the failed sibling).
- quant-researcher 4: forking path of later H&S renames -- applied (later H&S ideas join the family).
- quant-researcher 5: 300 is a floor, not power -- applied (counts note prints events/year and paired MDE).
- quant-researcher 6: parameter provenance -- applied (provenance section; one frozen timestamp).
- quant-researcher 7: closed-work table incomplete -- applied (v104-a, v127, `sweep_reclaim_bos` added, with overlap).
- quant-researcher 8: directions race under different instruments -- applied (per-direction calibration cited; never pooled).
- veteran-trader 3: screen stop is not the pattern stop -- applied.
- veteran-trader 4: next-open gaps -- applied (gap block; race's gap rule stated).
- veteran-trader 5: earnings inside the hold -- applied (earnings block).
- veteran-trader 6: different cost structures by direction -- applied (per-direction friction printed).
- veteran-trader 7: regime-skewed by construction -- applied (regime mix vs null; follow-on settles the SPY rule).
- veteran-trader 8: follow-on alert timing and gap chase -- applied.
- veteran-trader 9: close-only pass says nothing about retest -- applied.
