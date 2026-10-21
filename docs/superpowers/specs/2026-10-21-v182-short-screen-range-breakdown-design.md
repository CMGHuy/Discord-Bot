# v182 — Idea screen for shorts, and two Schwab range-breakdown short screens

**Version:** ui 1.33.1 · bot 2.14.2 (at writing)
**Bump:** none — backtesting instrument (`swingbot/core/backtesting/screen/`, `scripts/backtest/screen_idea.py`) and two one-shot screen runs; nothing the bot or admin serves changes.
**Edge:** none (integrity) — the short race is instrument plumbing and the two screens are measurements. A `SCREEN-PASS` would license a later `Edge: volume` short-entry spec carrying Schwab's stop and targets; this spec claims no edge.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, veteran-trader
**Status:** spec written 2026-10-21 from a brainstorm with the partner (sources: Schwab "The Ins and Outs of a Swing Trade", "Short Selling: The Risks and Rewards", TradingView short-idea format). Partner decisions: more shorts *and* a higher short win rate is the goal; breakdowns only in the stock's own downtrend, no SPY gate; screen both entry triggers; later spec targets TP1 at half the projected move, TP2 at the full projection.

## Why

The live book issues few shorts and its recent shorts lose. Production,
trades opened 2026-07-06..2026-10-21, read 2026-10-21 (read-only):

- 333 of 983 closed trades are shorts; their share fell from 45% of July
  closes to 11% of October's; none open now.
- Shorts: WR 51.3%, ExpR −0.124R (N with R 267). Longs: WR 50.1%, ExpR
  +0.003R (N 509). Recent months: September WR 25% (N 16), October 36%
  (N 14) — thin.
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

**Short costs (my call):** besides slippage and commission, a short pays a
borrow fee of **0.5% a year**, pro rata per calendar day held, converted to
R. S&P 500 names are general-collateral borrows (roughly 0.25–0.5%); 0.5%
is the conservative end. Dividends need no adjustment: the cache is fetched
with `auto_adjust=True` (`scripts/data/fetch_backtest_data.py:99`), so the
adjusted series never drops on an ex-date and a short on it already pays
the dividend.

The matched null is unchanged in how it draws (same ticker, month and
`close > SMA200` state, K = 20) and is raced in **the idea's direction**.
Forward drift is printed sign-adjusted for shorts (event minus null of
−forward return), so "positive" means "good for the trade" in both
directions. The verdict's four clauses are unchanged.

The borrow fee is charged to null trades too. The per-year rank
correlation is sign-flipped for shorts like the drift. An idea module
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
   through target, same-bar stop and target, timeout).
2. **A/A (my call: the v163 method, not a real-cache run):** 200 seeded
   synthetic replicates (fat-tailed, as `results/2026-10-16-trail-race-calibration.md`),
   random events, short direction, through the screen's race, null and
   verdict. Gate: false-pass rate ≤ 5%; coverage reported, not gated. It
   never reads the 2010–2019 cache. Extend the v163 calibration script with
   a direction argument rather than writing a second one. **If it fails:**
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
  event bar (`levels()` function in the module).
- Entry bar = the event bar t; entry = `min(Open[t], level)`.
- Risk = 1.5 × ATR14[t−1] (the ATR known when the order was placed, not the
  event bar's own).
- **Entry bar, conservative:** the stop counts as hit on bar t if
  `High[t] ≥ stop` (the high may have come before the fill; the screen
  assumes the worst). The target never counts on bar t. Bars t+1..t+cap race
  as usual.
- Cap counts from bar t+1, as now.
- **The matched null mirrors the fill, not just the mode (my call).** An
  event's fill comes after price fell from the open to the level, so the
  worst-case entry-bar rule is pessimistic for it. A null filled at its open
  would face the same rule accurately, which biases the comparison against
  the idea before any edge is measured. So each null bar gets a seeded
  intraday level drawn uniformly in `[Low, Open]` of that bar (a sell-stop
  below the open that the bar reached), fills at it, and faces the identical
  entry-bar rule. Null bars with `Low = Open` fill at the open. The level
  draw uses the null's existing per-idea, per-ticker seed.
- Overlap: an exit on the entry bar has `exit_pos = t`; the non-overlap rule
  is unchanged (next event must start after `exit_pos`). `entry_date` in
  level mode is `index[t]`. Warm-up is checked at t−1, where ATR is read.

`ENTRY` is frozen with the idea and pinned in the registry test like
`RACE`. Calibration adds: (3) level mode with level = open and no entry-bar
stop hit reproduces the next-open race shifted one bar (test); (4) the same
synthetic A/A as (2) in level mode, events and null both drawing levels the
same way, gate false-pass ≤ 5%. If (4) fails, the asymmetry is not solved:
`range_breakdown_stop` is not run and the partner is told; the close idea
can still run.

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

**`range_breakdown_close`** — `Close[t] < S`. `ENTRY = "next_open"`,
`RACE = "fixed"`, `CAP = 20`, direction short.

**`range_breakdown_stop`** — `Low[t] < S`. `ENTRY = "level"` with level
`S`, `RACE = "fixed"`, `CAP = 20`, direction short.

`SOURCE` for both: Schwab, "The Ins and Outs of a Swing Trade" (2025-03-07),
downswing breakout. `SUMMARY` states the rule above in one line.

Two ideas mean two shots, each one-shot under the unchanged pass rule. The
results docs print both under BH q across the ledger (reported, never
gating), as today.

**Event count before the shot (my call).** `--dry-run` cannot do this: it
races and prints the verdict, and the guardrail caps it at three tickers. So
`screen_idea.py` gets a `--count-only` flag that computes events, the
member/warm-up/window drops and non-overlap (using a race-free exit bound:
non-overlap assumes every trade lasts the full cap, the most conservative
count) and prints only those counts — no race, no R, no verdict, no file,
no ledger row. It runs over the full universe; it is not `--dry-run`, so the
dry-run guardrail does not apply, and it reveals nothing about outcomes.

- Count ≥ 300: the real one-shot run follows.
- Count < 300: **no run, no ledger row**; the shot is not spent (the same
  logic as Stage −1 reachability, "refused, budget intact"). The builder
  reports to the partner. Loosening a number would be a new idea with a new
  name, so it is the partner's call.
- A real run that still ends under 300 after the race's actual exits is
  `SCREEN-UNDERPOWERED`, recorded and closed like a fail, as today.

### What a pass buys, and what comes after (not this spec)

A `SCREEN-PASS` buys a spec, not a verdict. That spec (Edge: volume, Screen:
the passing ledger id) would build the live plan from Schwab's levels:
stop just above the broken support (Schwab: "since a retreat to that price
would keep losses to a minimum"), TP1 at S − ½(R − S), TP2 at S − (R − S),
and would run the unchanged acceptance funnel. It would also decide whether
the breakdown bypasses the RS gate. That spec also covers short-specific
risks the screen cannot see: squeeze risk (short interest ≥ 10% of float,
Schwab "What's a Short Squeeze"), holding across earnings or an ex-dividend
date, and the uptick rule (SEC Rule 201) after a −10% day.

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
