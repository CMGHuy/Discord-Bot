# v230 — Screen v2, the replication ladder and the additive-strategy gate

**Version:** ui 1.44.0 · bot 2.19.1
**Bump:** none (measurement instruments, one batch of screen runs and a gate module; nothing the live bot scans, alerts on or posts changes)
**Edge:** none (integrity). Three instruments, never a lift by themselves. The widening that pairs with the tightening is stated in `## Why` § What this buys.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, veteran-trader
**Status:** spec written 2026-11-16 from a brainstorm with the partner; design approved in chat the same day. The partner's four decisions are recorded in `## Partner decisions`.

## Why

The partner asked why new features keep ending as no-lift. The ledger
(`docs/superpowers/results/preregistration-ledger.jsonl`, 81 rows on
2026-11-16) holds 5 `PASS` rows, all from August, 2 `SCREEN-PASS`, 3 `OPEN`
and the rest dead. Since the idea screen went live on 2026-10-08, 12 screens
ran and 2 passed; every funnel or diagnostic verdict after that date is
`NO-LIFT`. Three procedural defects explain most of it.

### Defect 1: the screen's null conditions on the future

`swingbot/core/backtesting/screen/null.py` (`candidates`, `month_key`) draws
each event's K = 20 null bars from the **same ticker, the same calendar month
and the same trend state**, on either side of the event bar. A month that
contains a trigger is not a random month:

- a dip trigger (`uptrend_pullback`, `turtle_soup`) sits in a month that
  contains a sharp drop, so null bars before the event race into that drop;
- a breakout trigger (`high52w`, `gap_volume`) sits in a month that contains
  a run-up, so null bars before the event ride it.

The recorded arms show the size. The event's own mean R is nearly the same
for "passes" and "fails"; only the null moves:

| Idea | Verdict | mean R_event | mean R_null | ΔExpR |
|---|---|---|---|---|
| `uptrend_pullback` | SCREEN-PASS | +0.078 | −0.289 | +0.367 |
| `turtle_soup` | SCREEN-PASS | +0.07 | (not recomputed here) | +0.316 |
| `high52w` | SCREEN-FAIL | about +0.07 | +0.44 | −0.366 |
| `gap_volume` | SCREEN-FAIL | about +0.12 | +0.58 | −0.464 |

Sources: `results/2026-10-08-screen-uptrend_pullback.md`,
`results/2026-10-09-v140-screen-summary.md` (null means +0.58R and +0.44R),
`results/2026-10-23-v180-turtle-soup-result.md` (raw event mean +0.07R). The
`high52w` and `gap_volume` event means are null plus Δ, not read from their
docs. A random entry raced 1.5/3 ATR should average near minus costs for
every idea; a null that swings from −0.29R to +0.58R between long ideas is
measuring the trigger's own neighbourhood. v214 attributed the pattern to
the 2010–2019 decade; the per-idea swing points at the matching.

**This is inferred, not yet measured.** The mechanism is confirmed in code;
its size on data with no edge is Part A's first deliverable.

### Defect 2: the screened shape is never the shape that is tested next

`turtle_soup` passed on a 1.5/3 ATR race, PIT S&P 500, 2010–2019, yfinance
bars. v180 then tested a different stop (`Low[t] − 0.25 × ATR14`), a
different target (nearest level in the 1.5–2.5 band), the 67-ticker
watchlist, 2018–2022 and Alpaca bars in one step. 24.6% of signals became
trades (risk cap 48.0%, no level in band 18.8%). Its results doc says the
record "does not say which explains it". Arm A, the screened shape, closed
without a run.

### Defect 3: an added strategy is judged by the book's pooled win rate

v180 was refused at Stage 0 on pooled ΔWR (−0.21pp against a paired MDE of
0.31pp); its own spec predicted "a fail on the win-rate clause as the base
case". The v72 gate makes win rate the objective because it was built for
**filters** on one population. An added strategy at reward:risk 2 breaks
even at 33% and lowers a pooled win rate while paying. `CLAUDE.md` ranks
pooled ExpR first and win rate as a constraint; no gate applies that order
to added rows. v180 also compared net added rows with a gross book.

### What this buys

`Edge: none (integrity)`, and not only a tightening. Part A adds one clause
(absolute event R) and removes a bias that fails breakout and momentum ideas
mechanically. Part B lets an idea ship in the shape that was proven. Part C
stops refusing paying strategies on a pooled statistic. The batch re-screen
returns twelve ideas to an unbiased measurement, once.

## Partner decisions (2026-11-16)

1. Scope: Parts A, B and C in one spec.
2. **The twelve `screen-v1` rows are re-screened once, as one batch, under
   `screen-v2`.** This is an explicit, dated exception to "closed
   pre-registrations never re-run", granted because the instrument was
   defective, not because a result was unwelcome. It covers these twelve
   rows and nothing else.
3. Additive gate: own net ExpR is the objective; win rate must clear the
   strategy's **own break-even**, not the book's.
4. Ladder end: when rung 1 holds and the bot's stop or target does not, the
   strategy goes to the funnel in the **screened shape**, sized to the 2%
   dollar-risk rule. No mixed shapes.

## Goals

1. Measure the v1 null's bias on data with no edge, and ship a null that
   scores zero there.
2. Re-screen the twelve recorded ideas once under the fixed instrument.
3. Carry a screen pass to the bot's shape one change at a time, so a failure
   names its cause.
4. Give added entry strategies a gate that scores their own rows.

## Non-goals

- The live plan constructor for an ATR-shape strategy (entry next open, ATR
  stop and target, dollar-risk sizing). It belongs to the first strategy
  spec that reaches the funnel in the screened shape.
- Mapping the funnel's Stage 2 and Stage 3 to instrument v3
  (`V3_FUNNEL_REFUSAL` stays).
- More than one race shape per idea.
- Any change to the v72 filter gate, the v92 harvest gate, avoid mode's
  clauses or the trail race.
- Reopening any funnel row. v180's structural Turtle Soup arm stays closed.

## Anti-goals (a failure even if everything "works")

- A null chosen because it produces more passes. The placebo decides, on
  synthetic data, before any real idea is read under v2.
- A second re-screen. `screen2-<name>` ids are one shot like every screen id.
- The ladder becoming three more places to tune. Each rung is one frozen
  shot with no parameters of its own.
- The additive gate applied to a filter, or to a strategy that removes rows.

## Design

### Part A — screen v2

**A1. Placebo harness** (`swingbot/core/backtesting/screen/placebo.py`,
`scripts/backtest/screen_placebo.py`). Two synthetic universes with no edge
by construction:

- `gbm`: 200 tickers × 2,520 bars, driftless geometric random walk, daily
  volatility drawn per ticker from the cached universe's ATR% quartiles,
  open/high/low built from an intraday range model fitted to the same
  quartiles; seed 42.
- `shuffled`: the real `data/backtest_cache_ext` bars with trading days
  permuted in 5-day blocks, **the same permutation for every ticker**, so
  cross-sectional correlation survives and time structure does not; prices
  rebuilt from the permuted daily returns and intraday ratios; seed 42.

Five placebo triggers, defined in the harness and never registered as ideas:
`p_high20` (close above the prior 20-bar high), `p_rsi2_dip` (close >
SMA200 and RSI(2) < 10), `p_gap_up` (open ≥ prior close + 0.5 × ATR14),
`p_sweep20` (low under the prior 20-bar low, close back above), and
`p_market_down` (market scope: the equal-weight synthetic index closes down
more than 1.5 of its own 20-day standard deviations).

The harness runs each trigger through the unchanged screen pipeline (race,
costs, week-clustered bootstrap) under a named null. Output:
`docs/superpowers/results/<date>-v230-null-placebo.md`, one row per
universe × trigger × null: N, mean R_event, mean R_null, Δ, 95% interval.

- Under `v1` the table **is the measurement of Defect 1**. It is recorded
  as found. If every |Δ| is within 0.02R, the premise of this spec is wrong:
  the results doc says so, Parts A2–A5 do not run, and Parts B and C proceed
  on their own.
- Under `v2` the acceptance rule is: every universe × trigger has
  |Δ| ≤ 0.02R **and** an interval containing zero. One failing cell stops
  Part A. No fallback null is tried inside this spec.

**A2. The v2 null** (`null.py`, selected by `NULL_VERSION`; v1 stays
callable so the placebo can run it and so old results reproduce).

- **Ticker-scope ideas (default): same-date cross-section.** For an event on
  ticker *i* at date *t*, the pool is every other PIT member *j* that is
  eligible at *t* (member, warmed up, race completes inside its data), has
  the same trend state (`close > SMA200`) at *t*, and has no event of this
  idea at *t*. K = 20 drawn without replacement, floor
  `MIN_CANDIDATES` = 5, seed `null_seed(idea + ":v2", date)`. Each null bar
  is raced in the event's shape with its own ATR14. This controls the market
  regime on the exact day and never reads the event ticker's own path.
- **Market-scope ideas** declare `SCOPE = "market"` (default `"ticker"`,
  part of the frozen definition, pinned in `test_ideas_registry.py`):
  triggers that fire for every member on the same date (`turn_of_month`,
  `bond_spike_rebound`, `dollar_drop`). A same-date pool is empty for them.
  Their pool is the same ticker and trend state on dates within ±126 trading
  days of the event, **excluding every date within `CAP` bars of any event
  date**, floor 5, seed `null_seed(idea + ":v2", ticker)`.
- An idea whose ticker-scope events leave fewer than 5 candidates on more
  than half of its event dates is misdeclared: the run refuses with
  `SCOPE_MISMATCH` before any outcome is read.
- Level-entry ideas (`_draw_level`) and avoid-mode control arms keep their
  mechanics; only the candidate pool changes.

**A3. Pass rule.** `SCREEN-PASS` under `screen-v2` needs the four v1
clauses unchanged (ΔExpR ≥ +0.10R, lower 95% bound > 0, ≥ 7 of 9 years,
N ≥ 300) **and** a fifth: the week-clustered lower 95% bound of mean
R_event, net of costs, is above zero. The fifth clause applies to
`MODE = "edge"` only. Avoid mode's six clauses are unchanged, read against
the v2 pool.

**A4. Instrument and ids.** Ledger `instrument` is `screen-v2`. A new idea
keeps the id `screen-<name>`; `screen_idea.py` runs v2 only from this plan's
merge. Every results doc prints the null version and scope.

**A5. Batch re-screen.** The twelve ideas with a `screen-v1` row
(`high52w`, `uptrend_pullback`, `gap_volume`, `turn_of_month`,
`bond_spike_rebound`, `dollar_drop`, `sweep_reclaim_bos`, `turtle_soup`,
`range_breakdown_close`, `shock_support_break_short`,
`shock_failed_bounce_short`, `fvg_overhead_aged`) run once each under v2
with every parameter, race shape, mode, cap, window, universe and data
source as first run.

- Ids `screen2-<name>`; `screen_idea.py --rescreen-v1` accepts exactly these
  twelve names and refuses a `screen2-` id that already exists.
- The twelve p-values form their own Benjamini-Hochberg family of twelve,
  reported in the summary and never gating (as today).
- The v1 rows stay in the ledger untouched. Each `screen2-` row's record
  names its v1 row.
- **The v2 verdict supersedes the v1 verdict for licensing.** A v1 pass that
  fails v2 no longer licenses a spec. A v1 fail that passes v2 has earned
  the ladder (Part B), nothing more.
- Summary: `docs/superpowers/results/<date>-v230-rescreen-summary.md`, old
  and new verdict side by side, both arms' means.
- The scout slate of 2026-11-16 and any other unscreened idea run on v2
  after this batch, as ordinary first shots.

`backtest-methodology.md` § Stage −2 gains the v2 null, the fifth clause,
`SCOPE`, and one dated paragraph recording partner decision 2 and its limit.

### Part B — the replication ladder

`scripts/backtest/replicate_idea.py`, core in
`swingbot/core/backtesting/screen/ladder.py`. It takes a `SCREEN-PASS` idea
(`screen-v2` instrument) and runs three rungs in order. Every rung is one
frozen shot with a ledger row `ladder-<name>-r<N>`, instrument `ladder-v1`.

| Rung | Changes from the rung above | Population |
|---|---|---|
| 1 | data source, period, universe year set | the screen's trigger and race shape on the PIT S&P 500 Alpaca store `data/market_data_pit/`, warm-up from 2016-01-04, events 2017-01-01..2020-12-31, v2 null |
| 2 | the stop | rung 1's kept events, the bot's stop for that entry, the screened target distance in R held constant |
| 3 | the target | rung 2's events, the bot's target band (1.5–2.5 R:R, nearest level, no level means no trade) |

- **Hold rule, every rung:** the week-clustered lower 95% bound of net mean
  R is above zero, N ≥ 300. N < 300 is `LADDER-UNDERPOWERED`; any other miss
  is `LADDER-FAIL`; else `LADDER-HOLD`. Rung 1 also needs ΔExpR against the
  v2 null to be positive (the sign replicates); the size is reported.
- Rungs 2 and 3 call the live stop and target functions on each event bar
  (the builder names them; no reimplementation). Costs are 5 bps a side plus
  commission on every rung. Rung 2 sizes to fixed dollar risk, so a wider
  stop means a smaller position, not a dropped trade; the share of events
  the bot's 2% price-distance clamp would have dropped is reported.
- Each rung reports the paired difference to the rung above on the shared
  events, with its interval, and rung 3 reports attrition (no level in band,
  risk cap, open through the stop).
- The watchlist subset of rung 1 is printed beside it, never gating.
- 2017–2020 lies inside the funnel's selection side for both instruments.
  The ladder never reads 2021 or later.

**What a ladder buys (partner decision 4):**

| Outcome | Next step |
|---|---|
| rung 1 fails or is underpowered | idea closed as a non-replication; rungs 2–3 do not run |
| rungs 1, 2 and 3 hold | a strategy spec in the bot's shape |
| rung 1 holds, rung 2 or 3 does not | a strategy spec in the **screened shape**, sized to the 2% dollar-risk rule; the failed rung closes that bot stop or target for this idea |

A strategy spec's `**Screen:**` line cites the `SCREEN-PASS` id as today;
from this spec's merge its body must also cite its `ladder-<name>-r1` row
and name the shape the ladder selected. That is a documentation rule in
`document-conventions.md`, not a new header line.

### Part C — the additive-strategy gate

`swingbot/core/backtesting/acceptance_additive.py`, selected by
`validate_component.py --gate additive`. It applies when the component arm
**only adds rows** to the baseline (Stage −1 reports removed = 0 and
changed = 0 apart from displacement, below). Anything else is refused with
`ADDITIVE_GATE_MISUSE` and belongs to v72 or v92.

| # | Clause | Instrument | Threshold |
|---|---|---|---|
| 1 | `own_expectancy` (objective) | added rows' net ExpR, ticker-cluster bootstrap | lower 95% bound > 0 |
| 2 | `win_rate_above_breakeven` | added rows' decided win rate against `1 / (1 + median planned R:R)` of those rows, same bootstrap | lower 95% bound > break-even |
| 3 | `book_no_harm` | paired change in the book's total R (sum, not mean), strategy on against off, ticker-cluster bootstrap | lower 95% bound > 0 |
| 4 | `stability` | per-fold net ExpR of the added rows, folds 2021 / 2022 / 2023 | > 0 in ≥ 2 of 3, no fold below −0.10R, per-fold N ≥ 30 |
| 5 | `not_luck` | clause 1's one-sided bootstrap p | < 0.05, validation stage only |

- **Displacement** is why clause 3 exists: an added position can block a
  baseline plan through the heat or one-position rules. Displaced baseline
  rows are counted in clause 3 and listed in the results doc.
- Costs are net on **both** arms, fixing the net-against-gross comparison
  v180 disclosed.
- Stages are the funnel's: −1 reachability; 0 a precision precheck (the
  half-width of clause 1's interval on fold-train must be ≤ the fold-train
  point estimate, else `REFUSED`, budget intact); 1 clause 1–3 on fold-train
  with `plateau_report()` where a knob exists; 2 clause 4; 3 one VALIDATION
  shot, all five.
- No geometry lock and no pooled win-rate clause: an added strategy does not
  move the baseline rows' geometry, and clause 2 replaces the pooled
  comparison with the strategy's own arithmetic.
- The badge threshold (`win_rate >= 50`) is untouched. A strategy that ships
  through this gate carries the tier its own cell earns.

`backtest-methodology.md` gains `## Additive gate` beside `## Harvest gate`.

## Constraints

- No-lookahead: the v2 pool is built from information at *t* only (member,
  trend state and event flag at *t*). Race completeness is an eligibility
  rule on data length, as in v1.
- One shot per id for `screen2-*` and `ladder-*`; a crashed run that wrote
  no result may be re-run once, and the results doc says so.
- Long runs checkpoint per ticker (screen, re-screen, ladder) and a restart
  skips finished units.
- Every new or changed function stays under cyclomatic complexity 15.
- `screen_idea.py` already carries about a thousand lines; the re-screen
  mode and null selection go in modules, not in the script.
- Determinism: fixed seeds, and a golden test pins one small v2 draw.

## Testing

- Placebo harness: the two universes are reproducible from the seed; a
  planted edge (events followed by an injected +0.5 ATR drift) is recovered
  under v2 within its interval, so the null is not blind.
- v2 pool: no candidate has an event at *t*; no candidate is the event
  ticker; trend state matches; market-scope pools exclude the embargo;
  `SCOPE_MISMATCH` fires on a market-wide trigger declared ticker-scope.
- Verdict: the fifth clause in edge mode, absent in avoid mode; v1 verdict
  functions unchanged (existing tests stay green untouched).
- Re-screen: refuses a thirteenth name, refuses an existing `screen2-` id,
  leaves v1 rows byte-identical.
- Ladder: rung order enforced, rung 2 refused without a rung 1 hold, hold
  rule edge cases at N = 299 / 300 and bound = 0.
- Additive gate: each clause at its boundary, misuse refusal when the arm
  removes a row, displacement counted, both arms net of costs.
- `tests/hooks/` doc tests for the methodology and conventions edits; the
  Codex mirror (`AGENTS.md`, synced skills) in the same commits.

## Plans

1. **Plan 1 — screen v2 and the re-screen** (Part A): placebo harness and
   the v1 measurement, v2 null and `SCOPE`, the fifth clause, the batch
   re-screen, methodology docs and the `screen` skill.
2. **Plan 2 — ladder and additive gate** (Parts B and C). Independent of
   Plan 1's code except that the ladder imports the v2 null; it starts after
   Plan 1's null lands.

## Left to the builder

- The intraday range model for `gbm` bars and the exact rebuild of
  `shuffled` prices.
- Which live functions rung 2 and rung 3 call, and how levels are computed
  on the PIT store without the watchlist's caches.
- How `validate_component.py` detects an add-only arm.

## Claude's calls, for the partner to check

- The 0.02R placebo tolerance and "no fallback null inside this spec".
- The fifth screen clause gating edge mode only. In a rising decade it is
  easy for longs and hard for shorts; a short idea that beats its null but
  loses money outright will fail it, by design.
- Rung 1's window (2017–2020) and N ≥ 300 per rung.
- Clause 3 as total R with a lower bound above zero, and clause 4's −0.10R
  fold floor.
- Power is still thin in Part C. On the 67-ticker watchlist an added
  strategy with about 200 trades and a per-trade spread near 1.2R needs
  roughly +0.16R to clear clause 1. The gate asks the right question; the
  v3 funnel mapping (below) is what gives it enough rows.

## What follows

1. A methodology spec mapping funnel Stages 2–3 to instrument v3 for
   components that did not exist when v3's folds were tainted. It is the
   power fix for Part C and for every Stage 0 refusal.
2. Strategy specs for whatever the re-screen and ladder pass.
3. A small pre-registered exit family per idea, if the re-screen shows
   signals dying on shape.

## Parallelisation

- Plan 1 is a chain: placebo harness → v1 measurement → v2 null → placebo
  acceptance → fifth clause → re-screen runs → docs. Each step reads the
  previous step's result, and the acceptance step can stop the plan.
- Plan 2 has two independent groups after Plan 1's null lands: the ladder
  (Part B) and the additive gate (Part C) share no files. They join at the
  methodology-doc task.
- Plans 1 and 2 are sequential on one edge only: the ladder imports the v2
  null.
