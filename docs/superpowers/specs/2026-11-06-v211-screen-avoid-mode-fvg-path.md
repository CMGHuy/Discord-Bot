# v211 — Avoid mode for the idea check, and the overhead bearish-gap idea

**Version:** ui 1.39.1 · bot 2.16.5
**Bump:** none (a measurement instrument and one screen run; nothing live changes)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, technical-analyst

## Why

On 2026-11-06 the partner asked what the live book's losses since September
teach. The numbers are in
`docs/superpowers/results/2026-11-06-loss-review-sep-nov.md`. They are
live-book, in-sample and exploratory. One population stood out:

| Population (live book) | N | ExpR | WR |
|---|---|---|---|
| Longs whose plan attribution is `FVG (bearish)`, opened Sep 1 onward | 68 | −0.199 | 19% |
| Same, opened before Sep 1 | 61 | −0.060 | — |
| Longs attributed `FVG (bullish)`, opened Sep 1 onward | 33 | +0.298 | 36% |

**What the live shape is.** `primary_strategy_for`
(`swingbot/core/planning/builders.py:547`) names the source behind the
plan's **target**, and `levels.py:349` feeds the gap's midpoint in as a
level candidate. So these are longs bought at an ordinary support whose
**TP1 sits at an older unfilled bearish gap overhead**. They bet on a gap
fill, and the trade does not get there.

**What this spec tests, and what it does not.** The Stage −2 screen races
generic events on any bar, with no bot plan beneath them and a fixed race
target of 3 × ATR14. It therefore cannot reproduce the live plans. It tests
the **generic mechanism behind them**:

> A long taken while an older unfilled bearish gap sits within the race's
> reach overhead does worse than both of these:
> - matched random bars;
> - matched bars where an older unfilled bearish gap exists but sits beyond
>   reach.

On 2026-11-06 the partner chose this route over a read-only replay
diagnostic of the bot's own plans (the v143 style). The live population is
motivation only. A verdict here is a statement about the mechanism, and any
later veto spec must say so.

**Two obstacles, and how this spec removes them.**

1. **The screen cannot test an avoid idea.** Stage −2
   (`backtest-methodology.md` § Funnel stages) passes only ideas that beat
   a matched random baseline by ≥ +0.10R. A veto in keep form selects most
   bars and is diluted towards zero by construction. A plain sign flip is
   not enough either: the panel showed it is **easier** to clear than the
   edge bar. Four closed long screens already sit at ΔExpR ≤ −0.10 with p
   near 1:
   - `screen-high52w` −0.366;
   - `screen-gap_volume` −0.464;
   - `screen-sweep_reclaim_bos` −0.162;
   - `screen-range_breakdown_close` −0.321.

   Partly, the 2010–2019 bull window flatters the long null
   (`backtest-methodology.md`, the range_breakdown_close row). So the avoid
   mode must beat a **control arm** as well as the null (G1).
2. **v68 `DEAD_CAT_BOUNCE_VETO` is closed** (validation failed, budget
   spent). It keyed on decline size and a fresh gap. Here the event fires
   only on gaps **at least 5 bars old**, never on the bar a gap forms. The
   control arm holds "a bearish gap exists" constant and varies only
   whether it is within reach. The v143 closed row (FVG bullish signal-bar
   features) never tested a bearish gap's position relative to price, so
   this idea is not a renamed v143 feature.

## Goals

### G1. Avoid mode for the Stage −2 screen

An idea module may export `MODE = "avoid"` (default `"edge"`). The mode is
part of the frozen definition, like `RACE` / `DIRECTION` / `ENTRY`. A changed
mode is a new idea with a new name, and one mode is declared before the run.

An avoid idea is `SCREEN-AVOID-PASS` only if **all six clauses** hold.

**Against the matched random null** (today's null, K = 20, same ticker,
month and trend state), with d = R_event − mean(R_null):

1. mean d ≤ −(0.10 − tolerance). The existing `_TOLERANCE` is mirrored, so
   exactly −0.10 passes.
2. The upper 95% week-clustered bootstrap bound is < 0 (strict on
   `ci_high`; 10,000 resamples, seed 42).
3. mean d < 0 (strict) in ≥ 7 of the 9 years 2011–2019. An empty year
   counts against.
4. N ≥ 300, or else `SCREEN-UNDERPOWERED`, closed.

**Against the control arm.** Up to K = 20 bars are drawn per event from the
same ticker, month and trend state, among bars where the idea's
`control_condition` holds (G3). With d_c = R_event − mean(R_control), over
events that have at least one control bar:

5. mean d_c ≤ −(0.10 − tolerance).
6. The upper 95% week-clustered bound of d_c is < 0, and N_c ≥ 300. Below
   300, the result is `SCREEN-UNDERPOWERED`, closed.

Any clause failing gives `SCREEN-FAIL`.

The report also prints, without gating:
- per-year d_c;
- the share of events with no control bar;
- the closed long screens' recorded exp_r, showing which would have cleared
  clauses 1–2 alone (calibration context, never re-run).

### G2. One shot, one family

`screen_idea.py` refuses an id already in the ledger. The avoid p is the
share of null-pairing resamples ≥ 0. It enters the same
`ledger_qvalues` BH family as every other row.

### G3. The idea `fvg_overhead_aged`

Daily bars and daily ATR14, the screen's own timeframe. The live cluster
spans horizons; the screen measures the daily mechanism.

**Gap source.** The live detector, called **once per bar t on
`df.iloc[:t+1]`**. Its output depends on where the frame ends:
- the 100-bar `LOOKBACK_BARS` window;
- the top-3 `MAX_GAPS_PER_SIDE` eviction;
- "unfilled" judged against bars up to t.

This means the unfiltered output of `find_fair_value_gaps_detailed` with
its live defaults. A gap counts as filled on any wick touch, as live does.
So the screen speaks about never-touched gaps only. Gap size is
unconstrained, as live; the displacement mode is not used, and using it
would make a new idea.

**Condition.** For a gap g at bar t:
- **age:** `t − g.bar_index ≥ 5`;
- **within reach:** `Close[t] < g.bottom ≤ Close[t] + 3 × ATR14[t]`.

For an unfilled bearish gap, `g.bottom > Close[t]` always holds, so the
binding parts are the age and the upper bound. Bottom is chosen because it
is a long's first contact with the supply zone. The mid (the live TP1
anchor) and the top are deliberately not tried. Each would be a new idea,
never a retry.

**Event.** At most one per gap identity (`bar_index`): the first bar t at
which g satisfies the condition. Several gaps qualifying on the same bar
make one event. A gap that leaves the window or is evicted never re-fires.

**Control condition.** No gap satisfies the condition at t, and at least
one gap with age ≥ 5 has `g.bottom > Close[t] + 3 × ATR14[t]` (it exists
but is out of reach).

**Null and control eligibility.** Every bar where **any** gap satisfies the
condition, not only event bars, is excluded from both the null and the
control pools. Contaminating the baseline with the state itself would pull
d towards 0. The report prints the excluded share.

**Entry proxy.** The race enters at `Open[t+1]` with target
`Open[t+1] + 3 × ATR14[t]`. The condition uses `Close[t]` as a frozen proxy,
because the open is unknown at the close. The report prints the share of
events where `Open[t+1] ≥ g.bottom`, meaning the gap was reached
overnight.

**Race.** `RACE = "fixed"`, `DIRECTION = "long"`, `ENTRY = "next_open"`,
`MODE = "avoid"`.

**CAP.** 20. That is the cap of the fixed-race ideas with the same 3 ATR
target (`gap_volume`, `range_breakdown_close`, `range_breakdown_stop`,
`sweep_reclaim_bos`). It is frozen here, before any count is seen.

**Lookahead.** A gap is knowable at the close of its third candle
(`bar_index`). The age rule puts every event at least 5 bars later.

**`SOURCE`:** the loss review results doc above.

### G4. The detector does not swallow errors in the screen

Today `find_fair_value_gaps_detailed` wraps its body in
`except Exception: return []` (`fvg.py`). Inside the screen that would turn
a failure into "no event" and shrink N silently. Change it as follows:
- split the body into a named helper that raises;
- the live function keeps its swallow by calling that helper, so it stays
  byte-identical, pinned by a test;
- the screen calls the helper and aborts the ticker with a counted error.

The results doc prints events per year and errors per ticker.

### G5. Verdict plumbing carries the mode everywhere

- **`verdict.py`.** Avoid clauses sit table-driven beside the edge clauses:
  - the mirrored tolerance;
  - `ci_high < 0`;
  - a `years_negative` that keeps the empty-year rule;
  - the control-arm clauses.
- **Every `decide` call site takes the idea's `MODE`.** That covers
  `screen_idea.py`, `screen/diagnostics.py` (the sub-population summaries)
  and the trail 2 × slippage verdict. A test proves an avoid idea never
  prints an edge label anywhere.
- **`screen_trail_calibration.py`** counts only edge passes as false passes.
- **`stats.VERDICTS`** gains `SCREEN-AVOID-PASS`, along with its pinned
  ledger tests.

### G6. Spec gate accepts an avoid pass for a veto only

`tests/hooks/test_spec_screen_header.py` accepts
`<ledger-id> SCREEN-AVOID-PASS` only for an `Edge: expectancy` spec adding a
**veto** filter. Every other case still requires `SCREEN-PASS`.

### G7. Docs, and their mirrors in the same commit

- `backtest-methodology.md` § Funnel stages: the avoid mode, its six
  clauses, why a control arm is required, the one-shot rule.
- `document-conventions.md` `Screen:` table: the avoid row.
- `AGENTS.md`: the mirror of both.

### G8. Run the one shot through `backtest-runner`

- Per-ticker checkpointing and a flushed percent print
  (`working-conventions.md` § Long runs must checkpoint).
- The results doc records the window, the universe and the seed derivation
  (`null_seed(idea, ticker)`).
- Output: `docs/superpowers/results/<date>-screen-fvg_overhead_aged.md`
  plus one ledger row. The verdict is recorded in this spec's closing
  commit.

## Non-goals

- **No veto ships here.** An avoid pass buys a spec for a confluence-plan
  veto. That spec then runs the unchanged funnel (Stage −1..3) on the
  bot's own replay, where the live shape (gap = TP1) is measured directly.
- **Edge-mode ideas are unaffected.** No existing idea's verdict or output
  changes; all read `MODE = "edge"` byte-identically, pinned by a witness
  test.
- **No short-side mirror,** and no re-run of any closed idea under the
  avoid mode.

## Anti-goals

- **Threshold shopping.** If this run fails, the idea is closed. None of
  these is a retry: a different age, the gap mid or top, a k × ATR reach,
  the displacement mode, or dropping the control clauses.
- **Re-opening v68 by the back door.** The event never keys on decline
  size, drawdown depth, distance from a high, or a gap on its formation
  bar.

## Constraints

- **Detector parity.** The live detector is reused through the G4 helper,
  never reimplemented. A vectorised form is allowed only if a parity test
  proves it matches the per-bar call at every t on frames that include all
  of these:
  - more than 3 bearish gaps (eviction);
  - a gap leaving the 100-bar window;
  - a later wick fill.
- **Truncation test.** Appending bars after t never changes the event or
  the condition at t.
- **Complexity.** Every function stays under complexity 15.
- **Tests ship with the work:**
  - the verdict clauses in both modes and their edges: exactly −0.10, an
    empty year, N = 299/300, N_c = 299/300, `ci_high` exactly 0;
  - the registry pin for `MODE`;
  - the per-gap onset and the eviction case;
  - null and control eligibility;
  - the detector helper's byte-identity;
  - the hook's accept and reject cases;
  - the ledger vocabulary.

## Left to the builder

- Where `MODE` and `control_condition` are read in the runner.
- The results-doc wording.
- Whether the control-arm draw reuses `null.candidates` with a different
  mask (preferred) or needs one small helper.

## What follows

- **`SCREEN-AVOID-PASS`:** brainstorm the confluence veto spec ("no long
  whose TP1 is an unfilled bearish gap"), citing this ledger id.
- **`SCREEN-FAIL` / `SCREEN-UNDERPOWERED`:** closed. The row goes into
  `backtest-methodology.md`'s closed table. The live population stays
  visible in the autopsy only. A read-only replay diagnostic of the bot's
  own gap-target longs (the v143 style) remains a separate, budget-free
  question.

## Panel review

Panel 2026-11-06 on c764f279 (quant-researcher, quant-engineer,
technical-analyst). The partner chose to fix the avoid mode rather than
switch to a replay diagnostic.

**BLOCKING**
- quant-researcher: a sign-flipped bar is easier than the edge bar; four
  closed long screens would clear it, and G4 would unlock a filter spec on
  it -- applied: control arm, clauses 5–6, calibration printout.
- quant-engineer: the event target `Close[t] + 3 ATR` differs from the race
  target `Open[t+1] + 3 ATR` -- applied: frozen proxy, overnight-reach share
  printed.
- quant-engineer: the detector must run per bar on a truncated frame
  (window, top-3, fill) -- applied: G3 gap source, parity constraint.
- quant-engineer: the detector's blanket `except` shrinks N silently --
  applied: G4.
- quant-engineer: the sign-flipped mean clause must mirror the tolerance;
  `ci_high < 0`; `years_negative` -- applied: G1, G5.
- quant-engineer: `decide` call sites (runner, diagnostics, trail
  calibration) lack the mode -- applied: G5.
- quant-engineer: `stats.VERDICTS` lacks the avoid label -- applied: G5.
- technical-analyst: the event does not capture the live population (gap =
  TP1) -- applied as a restatement: the spec now says it tests the generic
  mechanism, with the live shape as motivation only. The partner chose this
  over a v143-style replay diagnostic, which is kept as a separate open
  question.
- technical-analyst: onset-only fires on formation and excludes older gaps
  -- applied: age ≥ 5, per-gap onset.

**ADVISORY**
- quant-researcher: onset fires at formation, which is v68's gap arm --
  applied (age ≥ 5).
- quant-researcher: no control arm -- applied (now gating).
- quant-researcher: null contaminated by condition-true bars -- applied:
  excluded, share printed.
- quant-researcher: onset ambiguous -- applied: per gap identity, once.
- quant-researcher: `CAP` unfrozen -- applied: 20, with reason.
- quant-researcher: live numbers not reproducible -- applied: results doc
  committed.
- quant-researcher: q-value family not stated -- applied: G2.
- quant-researcher / quant-engineer / technical-analyst: the "i+1"
  confirmation was wrong -- applied: confirmed at `bar_index`, and the
  truncation test is restated.
- quant-engineer: eviction and window exit cause re-fires -- applied:
  per-gap once.
- quant-engineer: `mode all` is not a parameter of the detailed function --
  applied: the unfiltered output is named.
- quant-engineer: long run -- applied: checkpointing, G8.
- technical-analyst: bottom chosen without a reason -- applied: reason
  given; mid and top are new ideas.
- technical-analyst: a wick touch counts as filled -- applied: stated as
  scope.
- technical-analyst: top-3 by recency, size unconstrained -- applied:
  stated, and covered by the parity frames.
- technical-analyst: check the v143 tested features -- applied: checked,
  not among them.
- technical-analyst: no timeframe named -- applied: daily bars, daily
  ATR14.
