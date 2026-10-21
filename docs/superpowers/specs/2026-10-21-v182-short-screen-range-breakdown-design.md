# v182 — Idea screen for shorts, and two Schwab range-breakdown short screens

**Version:** ui 1.33.1 · bot 2.14.2 (at writing)
**Bump:** none — backtesting instrument (`swingbot/core/backtesting/screen/`, `scripts/backtest/screen_idea.py`) and two one-shot screen runs; nothing the bot or admin serves changes.
**Edge:** none (integrity) — the short race is instrument plumbing and the two screens are measurements. A `SCREEN-PASS` is evidence for the *trigger* under the generic ATR race only; it would license a later `Edge: volume` short-entry spec, where Schwab's stop and targets are still unmeasured. This spec claims no edge.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, veteran-trader
**Status:** spec written 2026-10-21 from a brainstorm with the partner (sources: Schwab "The Ins and Outs of a Swing Trade", "Short Selling: The Risks and Rewards", TradingView short-idea format). Partner decisions: more shorts *and* a higher short win rate is the goal; breakdowns only in the stock's own downtrend, no SPY gate; screen both entry triggers; later spec targets TP1 at half the projected move, TP2 at the full projection. Panel applied 2026-10-21; partner approved the spec the same day and ruled it distinct from the closed v105 (not a re-run).

## Why

The live book issues few shorts and its recent shorts lose. Production,
trades opened 2026-07-06..2026-10-21, read 2026-10-21 (read-only):

- 333 of 983 closed trades are shorts; their share fell from 45% of July
  closes to 11% of October's; none open now.
- Shorts: WR 51.3% and ExpR −0.124R over the 267 closed shorts that carry
  a journal R (of 333). Longs: WR 50.1%, ExpR +0.003R over 509 of 650.
  About 20% of closed trades have no journal R, so these are a selected
  subset. Recent months (shorts by entry month, closed): September WR 25%
  (N 16), October 36% (N 14) — thin. Motivation only; nothing gates on
  these.
- Stop-outs average −1.13R for shorts and −1.15R for longs, so stop fill is
  **not** a short-specific problem (cause: 60-second polling including
  extended hours fills at the observed print; the partner's broker also
  closes in extended hours, so the fill model stays). Not this spec.

Why shorts are rare (code survey): live shorts come only from confluence
scenarios; the RS gate blocks every short above the 25th RS percentile
(`scanning/scan_run.py:769-781`, `edge/rs_gate.py:28-50`); confidence docks
15 points counter to SPY's 200 EMA (`scanning/confidence.py:430-440`); every
dedicated short mechanism is masked after a closed negative pre-registration
(v93, v101–v104, v108, v113, Q-INV) or an unmeasurable one (v118, v119).

What the sources add that the bot has never tested: **a breakdown below a
defined sideways range in a downtrend**, with the stop just above the broken
support and the target projected down by the range height (Schwab, "Ins and
Outs": "measuring the previous distance between the support and resistance
lines, and then ... subtract it from support for a downswing trade"). The
confluence path never projects a measured move (`planning/targets.py`
selects only real supports).

The repo rule is that a new entry needs a `SCREEN-PASS` before its spec. The
screen refuses any non-long idea today
(`screen/ideas/__init__.py:51`, "v140 screens long ideas only"). So this spec
does three things: teach the screen to race shorts (Part A), add a
level-entry race mode a resting sell-stop needs (Part B), and run the two
breakdown screens (Part C).

### How this differs from closed short work

Closed results stay closed (`backtest-methodology.md` § Closed
pre-registrations). Neither idea reopens them:

- **Vol Expansion Breakdown (v104 Part B):** required ATR expansion on the
  breakdown bar; no range, no touches, no downtrend. Here: a range with two
  touches of each side, a falling SMA50, no volatility condition.
- **Break & Retest bearish (v84, v104 Part A):** enters on the retest of a
  broken level. Here: enters on the break itself.
- **Compression short (v119, unmeasurable, not closed):** a volatility
  squeeze state and its first release. Here: a price range defined by
  touches; volatility is not read.
- **Downtrend Overbought Fade / Bull Trap:** fade a rally. Here: no rally
  condition.
- **Pending range continuation (v105, NO-LIFT, closest relative):** a
  horizontal 10/15/20-bar range, two visits to the trigger side, a 30-SMA
  trend before the range, a resting stop-market order beyond the boundary,
  long and short (`specs/no-lift/2026-09-25-v105-pending-range-continuation-design.md`).
  What v105 measured and closed was the **directional-pressure predicate**
  `d` as a component over that range baseline, on 75 tickers, 2020–2023;
  the short side had component N 10–16 and never reached a test. The bare
  breakdown was never raced against a null. Its reopening rule bars "a
  range-pressure PENDING entry at these `(N, d)` values"; v182 has no
  pressure predicate, a 30-bar window, touches on *both* sides and a
  falling SMA50, so it is not that mechanism. It is close enough that the
  partner was told before approving (see `## Panel review`).

## Design

### Part A — the short race

`Idea.direction` accepts `"short"` (still default `"long"`); the direction is
part of the frozen idea, pinned in
`tests/backtesting/screen/test_ideas_registry.py` like `RACE`. A changed
direction is a new idea with a new name.

A short race is the exact mirror of the long race, for both shapes:

| | long (unchanged) | short |
|---|---|---|
| entry | open t+1 | open t+1 |
| risk | 1.5 × ATR14[t] | 1.5 × ATR14[t] |
| stop | entry − risk | entry + risk |
| target (fixed) | entry + 2 × risk | entry − 2 × risk |
| gap stop | open ≤ stop → exit at open | open ≥ stop → exit at open |
| gap target | open ≥ target → exit at open | open ≤ target → exit at open |
| intrabar | low ≤ stop first, then high ≥ target | high ≥ stop first, then low ≤ target |
| trail | 3 × ATR under the highest high of earlier bars, never lowered | 3 × ATR over the lowest low of earlier bars, never raised |
| gross R | (exit − entry) / risk | (entry − exit) / risk |
| frictions | entry "buy", exit "sell" | entry "sell", exit "buy" |

**Short costs (my call):** slippage and commission come from
`swingbot/core/edge/frictions.py` as today, applied once per fill. Besides
those, a short pays a borrow fee of **0.5% a year**, added to `frictions.py`
as one function (`borrow_r(entry, risk, days)` = entry × 0.005 / 365 ×
calendar days from entry date to exit date / risk; entry is the fill price,
including in level mode), charged once on event and null trades alike — a
test pins that both paths call it exactly once. S&P 500 names are general-collateral borrows (roughly 0.25–0.5%); 0.5%
is the conservative end. Dividends need no adjustment: the cache is fetched
with `auto_adjust=True` (`scripts/data/fetch_backtest_data.py:99`), so the
adjusted series never drops on an ex-date and a short on it already pays
the dividend.

The matched null is unchanged in how it draws (same ticker, month and
`close > SMA200` state, K = 20) and is raced in **the idea's direction**.
Forward drift is printed sign-adjusted for shorts (event minus null of
−forward return), so "positive" means "good for the trade" in both
directions. The verdict's four clauses are unchanged.

The sign flip for drift and per-year rank correlation is applied once, in
`forward.py` (the forward return is negated for a short idea before
`excess_drift` and `yearly_rank_corr` read it), never again in
`diagnostics.py`; a test pins that a mirrored frame raced short gives the
same drift and correlation as the original raced long. An idea module
declares `DIRECTION` and `ENTRY` constants beside `RACE`, read by `_load()`
with the same `getattr` default pattern.

The results doc prints the direction in its header (it already writes
"`{idea.direction}` only", `screen_idea.py:546`), and the ledger hypothesis
names it.

**Calibration, required before any short idea runs** (a results doc,
`docs/superpowers/results/<date>-short-race-calibration.md`, never a ledger
row):

1. **Mirror identity (test):** reflect a frame (`P' = c − P` for O/C, High'
   = c − Low, Low' = c − High, ATR unchanged). A short race on `P` gives the
   same outcome codes, exit offsets and gross R as a long race on `P'`, for
   both shapes, on random and on hand-built frames (gap through stop, gap
   through target, same-bar stop and target, timeout). Hand-built frames use
   dyadic prices (multiples of 1/8, c a power of two) so reflection is exact
   and ties stay ties; random frames compare gross R within 1e-9 and compare
   outcome codes only where no price lies within 1e-9 of a stop or target.
2. **A/A (my call: the v163 method, not a real-cache run):** 200 seeded
   synthetic replicates (fat-tailed, as `results/2026-10-16-trail-race-calibration.md`),
   random events, short direction, through the screen's race, null and
   verdict. Gate: false-pass rate ≤ 5%; coverage reported, not gated. It
   never reads the 2010–2019 cache. Extend the v163 calibration script with
   a direction argument rather than writing a second one. The generator must
   emit OHLC bars with a real intrabar range (High ≥ max(Open, Close),
   Low ≤ min(Open, Close)), not closes only; if v163's is close-driven, add
   that. Seeds 0..199, recorded in the doc. Decision rule: the observed
   false-pass count ≤ 10 of 200 (5%); the Wilson 95% interval is printed
   beside it, not gating. **If it fails:**
   stop, fix the race, re-run the calibration; no short idea runs and no
   ledger row is written until it passes.

### Part B — the level-entry race mode (resting sell-stop)

Today the race always enters at the next open. A resting sell-stop instead
fills **on the event bar** at the stop level (or at the open if the bar
gaps below it). Existing precedent screens such entries as close-confirmed
(`ideas/turtle_soup.py` docstring). The partner wants the resting stop
measured as itself, so the race gets an `ENTRY` constant per idea:
`"next_open"` (default, everything that exists) or `"level"`.

`"level"` (short shown; the long mirror is defined but unused):

- The idea's `events()` returns, besides the boolean series, the level per
  event bar (`levels()` function in the module). The level must be known
  from bars ≤ t−1 (the order is placed before bar t opens).
- **The order lives one bar.** It is placed before the open of bar t and
  cancelled at bar t's close if unfilled. (With the first-break rule an
  unfilled order means no event, so a longer life would change nothing
  but the bookkeeping.)
- Entry bar = the event bar t; entry = `min(Open[t], level)`. The event
  inequality and the fill agree: `Low[t] < level` fires, a bar that only
  touches the level does not.
- **Stop-market slippage (my call):** a level-mode entry is a stop-market
  order through a broken level, so its entry slippage is **2 ×** the
  `frictions.py` base (10 bps instead of 5), for events and null alike. A
  gap fill at `Open[t]` gets the same 2 ×, assuming full size at the open
  (S&P 500 names; a liquidity floor is the follow-on spec's job). The
  results doc also prints the book repriced at 3 × base, never gating.
- Risk = 1.5 × ATR14[t−1] (the ATR known when the order was placed, not the
  event bar's own).
- **Entry bar, conservative:** the stop counts as hit on bar t if
  `High[t] ≥ stop` (the high may have come before the fill; the screen
  assumes the worst). The target never counts on bar t. Bars t+1..t+cap race
  as usual.
- Cap counts from bar t+1, as now.
- **The matched null copies each event's fill depth (my call, revised
  after the panel).** An event's fill comes after price fell from the open
  to the level, so the worst-case entry-bar rule is pessimistic for it; a
  null filled at its open would face it accurately, biasing the comparison
  against the idea. A uniform draw would not fix that (three reviewers: an
  A/A where both sides draw the same way passes by construction). Instead,
  each event e records its depth `d_e = (Open[t] − fill) / ATR14[t−1]`
  (0 for a gap fill at the open). Each of e's null bars fills at
  `Open − d_e × ATR14` of that bar, a sell-stop the same ATR distance below
  its own open. A null bar whose Low does not reach that level is not a
  fill: it is replaced by another draw from the same candidate pool (same
  ticker, month, trend state); if the pool runs out, the event keeps fewer
  null trades, counted as `null_unfilled` in the results doc. Null trades
  face the identical entry-bar rule and slippage.
- **Random stream:** the level-mode replacement draws come from a child
  generator (`np.random.default_rng([seed, 1])`), never from the stream
  `matched_null` uses for positions (`null.py:81-90`), and run only in
  level mode, so every next-open idea's null is byte-identical to today's.
  A test pins that.
- Overlap: an exit on the entry bar has `exit_pos = t`; the non-overlap rule
  is unchanged (next event must start after `exit_pos`). `entry_date` in
  level mode is `index[t]`. Warm-up is checked at t−1, where ATR is read.

`ENTRY` is frozen with the idea and pinned in the registry test like
`RACE`. Calibration adds:

3. **Equivalence (test):** level mode with level = open and no entry-bar
   stop hit reproduces the next-open race shifted one bar.
4. **Synthetic A/A in level mode,** same method and gate as (2). Its job is
   only to show the level-mode code adds no false passes. It **cannot**
   show the null is fair to real events, and the spec does not claim it
   does.
5. **Fill-depth check on the real cache, outcome-blind:** for
   `range_breakdown_stop`, print the distribution (quartiles, share of gap
   fills) of event depths `d_e` and of the realised null depths, plus the
   `null_unfilled` share. No race, no R. This runs inside `--count-only`.
   Gate: null median depth within 0.05 ATR of the event median and
   `null_unfilled` ≤ 20% of the null draws. If it fails,
   `range_breakdown_stop` is not run and the partner is told; the close
   idea can still run.

If (4) fails: stop, fix, re-run; no level-mode idea runs until it passes.

### Part C — the two breakdown ideas

Both share one frozen range and trend definition (my call; the numbers are
the idea and never tuned after the run):

- **Window:** the 30 bars t−30..t−1 (t excluded).
- **Support S** = min Low over the window; **resistance R** = max High.
- **A range, not a slide:** `R − S ≤ 5 × ATR14[t−1]`.
- **Touches:** at least two window bars with `Low ≤ S + 0.25 × ATR14[t−1]`,
  the earliest and latest of them at least 5 bars apart; the same for
  `High ≥ R − 0.25 × ATR14[t−1]`.
- **Own downtrend:** `SMA50[t−1] < SMA50[t−11]` and `Close[t−1] < SMA50[t−1]`.
  No SPY condition (partner's choice).
- **First break only:** `Close[t−1] ≥ S` (the prior bar was still inside).
- **Numerics:** every clause ends in `.fillna(False)`; ATR14[t−1] that is
  NaN or ≤ 0 means no event. Warm-up: an event needs 61 completed bars
  before t (SMA50 at t−11 needs 60, the window 30, ATR 14); the
  warm-up check reads t−1 for both ideas. No-lookahead: S, R, ATR, SMA and
  touches read bars ≤ t−1; the trigger reads bar t (its Close for the close
  idea, its Low for the stop idea, which fills inside bar t). The truncation
  test truncates after t, and for the stop idea checks that nothing beyond
  bar t's Open/Low is read to place the order.

**`range_breakdown_close`** — `Close[t] < S`. `ENTRY = "next_open"`,
`RACE = "fixed"`, `CAP = 20`, direction short.

**`range_breakdown_stop`** — `Low[t] < S`. `ENTRY = "level"` with level
`S`, `RACE = "fixed"`, `CAP = 20`, direction short.

`SOURCE` for both: Schwab, "The Ins and Outs of a Swing Trade" (2025-03-07),
downswing breakout. `SUMMARY` states the rule above in one line.

Two ideas mean two shots, each one-shot under the unchanged pass rule. The
results docs print both under BH q across the ledger (reported, never
gating), as today. **They are nested:** every close event is a bar whose
Low also broke S, so they are two looks at one hypothesis and the chance
that at least one false-passes is above the per-idea 5%. Stated up front:

- Each results doc prints the event overlap (share of close events whose
  bar is also a stop event, and the reverse).
- Both pass: the follow-on spec picks the trigger, citing both.
- Only one passes: the follow-on spec may use only that trigger and must
  say the other failed; it treats the pass as weaker than a lone pass
  (family of two, BH q printed).
- Neither: both closed.

**Descriptive blocks in each results doc, never gating:**

- **Trend-only control:** the screen's null matches `close > SMA200`, but
  the idea also requires a falling SMA50 below price. A pass could come
  from that short-term downtrend alone. So the doc prints the same race,
  short, over bars that meet the trend clauses and the first-break
  arithmetic against a 30-bar low but **not** the range clauses (height,
  touches), as ΔExpR against the same null. A pass whose ΔExpR is not
  clearly above this control cannot be credited to the range.
- **SPY regime split:** event ΔExpR split by SPY above/below its 200-day
  average, to inform the follow-on spec's RS-gate and regime choices.

**Event count before the shot (my call).** `--dry-run` cannot do this: it
races and prints the verdict, and the guardrail caps it at three tickers. So
`screen_idea.py` gets a `--count-only` flag that computes events, the
member/warm-up/window drops and non-overlap (using a race-free exit bound:
non-overlap assumes every trade lasts the full cap, the most conservative
count) and prints only those counts — no race, no R, no verdict, no file,
no ledger row. It runs over the full universe; it is not `--dry-run`, so the
dry-run guardrail does not apply, and it reveals nothing about outcomes.
It calls the same `events()`, drop and non-overlap functions the real run
uses, never a reimplementation. In level mode an entry-bar exit makes the
real count higher, so the full-cap bound errs on the safe side. Each
count is recorded in a short counts note
(`docs/superpowers/results/<date>-v182-counts.md`: window, universe,
command, counts, and check 5's depth table), committed before any run.

- Count ≥ 300: the real one-shot run follows.
- Count < 300: **no run, no ledger row**; the shot is not spent (the same
  logic as Stage −1 reachability, "refused, budget intact"). The builder
  reports to the partner. Loosening a number would be a new idea with a new
  name, so it is the partner's call. At most **one** renamed variant per
  idea may be cut from count feedback alone; it is listed in the counts
  note and both names count as one family in the results doc.
- A real run that still ends under 300 after the race's actual exits is
  `SCREEN-UNDERPOWERED`, recorded and closed like a fail, as today.

### What a pass buys, and what comes after (not this spec)

A `SCREEN-PASS` buys a spec, not a verdict. That spec (Edge: volume, Screen:
the passing ledger id) would build the live plan from Schwab's levels:
stop just above the broken support (Schwab: "since a retreat to that price
would keep losses to a minimum"), TP1 at S − ½(R − S), TP2 at S − (R − S),
and would run the unchanged acceptance funnel. It would also decide whether
the breakdown bypasses the RS gate. That spec must also settle, before it can claim
the plan is placeable:

- **Order form:** the stop idea as a sell-stop placed before the open,
  valid for the day; the close idea as an alert after the close with a
  next-open entry. What the alert says when the open is already below TP1,
  or above the planned stop (a gap through the stop on a short): skip.
- **Short-specific risks the screen cannot see:** squeeze risk (short
  interest ≥ 10% of float, Schwab "What's a Short Squeeze"), earnings or
  an ex-dividend date inside the hold, hard-to-borrow names, the uptick
  rule (SEC Rule 201) after a −10% day.
- **A liquidity floor:** the screen runs on S&P 500 names; the live
  watchlist may hold thinner ones.

A fail closes exactly the frozen definition (30-bar two-touch range,
falling SMA50, that trigger, the fixed 20-bar race, short only), not
"breakdowns" in general.

## Testing

- Mirror identity, both shapes, hand-built and random frames (Part A 1).
- Short frictions: entry "sell", exit "buy", borrow fee in R from a known
  holding period.
- `Idea` accepts `direction="short"`, rejects anything else; registry test
  pins direction and `ENTRY` for every idea; existing ideas keep `long` and
  `next_open`, and their pinned outcomes are byte-identical (a long run of
  an existing idea on a fixture frame matches its pre-change output).
- Level mode: gap below the level fills at the open; entry-bar stop rule;
  target ignored on the entry bar; level = open equivalence (Part B 3).
- Each breakdown idea: hand-built frames for every clause (range too tall,
  one touch only, touches too close, SMA50 rising, close above SMA50, prior
  close already below S, the trigger itself) — event fires only on the
  frame that satisfies all. No lookahead: every input reads bars ≤ t, and
  S/R/ATR/SMA read ≤ t−1 (`no-lookahead` skill applies).
- Sign-adjusted forward drift for a short idea.
- Calibration docs (A/A for next-open short and level short) committed
  before either ledger row exists.

## Out of scope

- Any live change: RS gate, regime penalty, strategy masks, short-universe
  flags all stay as they are.
- The live plan's stop and targets (the follow-on spec, after a pass).
- Borrow availability or locate checks (the alert already says "CHECK
  BORROW AVAILABILITY").
- The paper-book stop fill model (kept; partner's broker fills in extended
  hours) and the journal-before-fill R bug (separate integrity task).
- Rebound-to-a-lower-high shorts (Schwab's ZYX example): too close to closed
  Fade / Bull Trap.

## Parallelisation

- **A → B → C, sequential.** B extends the race A makes direction-aware;
  C's ideas need both. A's calibration must be committed before any C
  ledger row exists (one shot per idea).
- Inside C: the two idea modules and their tests can be written in
  parallel; the two screen runs are independent but each is one shot, so
  each runs once, by `backtest-runner`.

## Panel review

2026-10-21, on 4cac9ccc. Roles: quant-researcher (opus), quant-engineer,
veteran-trader (sonnet).

BLOCKING

- veteran-trader 1: resting sell-stop life, order-time knowledge and gap fill unstated -- applied (one-bar order placed before the open, level from bars ≤ t−1, gap fill at open with full size, stop-market slippage 2 ×).
- veteran-trader 2: frictions source and breakdown slippage unstated -- applied (`frictions.py` once per fill, 2 × base on level entries for events and null, 3 × repricing printed; borrow fee in `frictions.py`).

ADVISORY

- quant-researcher 1: v105 pending range continuation is the closest closed relative and was not cited -- applied (differentiation added; flagged to the partner before approval).
- quant-researcher 2 / quant-engineer 1 / veteran-trader 6: the level-mode A/A passes by construction and cannot show the uniform null is fair -- applied (null copies each event's fill depth; A/A scoped to code correctness only; outcome-blind fill-depth check 5 on the real cache gates the stop idea).
- quant-researcher 3: the two ideas are nested -- applied (overlap printed; one-pass and two-pass readings stated up front).
- quant-researcher 4: null not matched on the SMA50 downtrend -- applied (trend-only control block, never gating; a pass not above it is not credited to the range).
- quant-researcher 5: Edge line implied Schwab's exits were screened -- applied (trigger-only wording).
- quant-researcher 6: production figures lacked denominators -- applied.
- quant-researcher 7: count-driven renaming is a forking path -- applied (at most one renamed variant per idea, same family).
- quant-engineer 2: level draws must not share the null position stream -- applied (child generator, level mode only, pinned by test).
- quant-engineer 3: borrow fee location and formula -- applied.
- quant-engineer 4: float ties in the mirror test -- applied (dyadic hand frames, 1e-9 tolerance, tie-free code comparison).
- quant-engineer 5: NaN handling and warm-up bound -- applied.
- quant-engineer 6: level-mode truncation and inequality consistency -- applied.
- quant-engineer 7: `--count-only` must share the real code path, counts recorded -- applied (counts note committed before any run).
- quant-engineer 8: single application of the short sign flip -- applied (in `forward.py`, pinned by a mirror test).
- quant-engineer 9: calibration seeds and decision rule -- applied (seeds 0..199, ≤ 10 of 200, Wilson interval printed).
- veteran-trader 3: follow-on order form, expiry, gap-through-stop handling -- applied (listed as must-settle items for the follow-on spec).
- veteran-trader 4: short tradeability risks and liquidity -- applied (follow-on must-settle list, liquidity floor).
- veteran-trader 5: close-idea alert timing and gaps -- applied (follow-on order form).
- veteran-trader 7: no regime split promised -- applied (SPY 200-day split block, never gating).
