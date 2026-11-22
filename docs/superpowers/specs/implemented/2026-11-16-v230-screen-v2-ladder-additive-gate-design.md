# v230 — Screen v2, the replication ladder and the additive-strategy gate

**Version:** ui 1.44.0 · bot 2.19.1
**Bump:** none (measurement instruments, one batch of screen runs and a gate module; nothing the live bot scans, alerts on or posts changes)
**Edge:** none (integrity). Three instruments, never a lift by themselves. The widening that pairs with the tightening is stated in `## Why` § What this buys.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, veteran-trader
**Status:** spec written 2026-11-16 from a brainstorm with the partner; design approved in chat the same day; panel review applied the same day (see `## Panel review`). The partner's four decisions are recorded in `## Partner decisions`.

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
(absolute event R, new ideas only) and removes a bias that fails breakout
and momentum ideas mechanically. Part B lets an idea ship in the shape that
was proven. Part C stops refusing paying strategies on a pooled statistic.
The batch re-screen returns twelve ideas to an unbiased measurement, once.

## Partner decisions (2026-11-16)

1. Scope: Parts A, B and C in one spec.
2. **The twelve `screen-v1` rows are re-screened once, as one batch, under
   `screen-v2`.** This is an explicit, dated exception to "closed
   pre-registrations never re-run", granted because the instrument was
   defective, not because a result was unwelcome. It covers these twelve
   rows and nothing else.
3. Additive gate: own net ExpR is the objective; win rate must clear the
   strategy's **own break-even**, not the book's.
4. Ladder end: when the screened shape holds and the bot's stop or target
   does not, the strategy goes to the funnel in the **screened shape**,
   sized to the 2% dollar-risk rule. No mixed shapes. The panel found a
   consequence the partner has not yet ruled on: see `## Open for the
   partner`.

## Goals

1. Measure the v1 null's bias on data with no edge, and ship a null that
   scores zero there.
2. Re-screen the twelve recorded ideas once under the fixed instrument.
3. Carry a screen pass to the bot's shape one change at a time, so a failure
   names its cause.
4. Give added entry strategies a gate that scores their own rows.

## Non-goals

- The live plan constructor for an ATR-shape strategy. It belongs to the
  first strategy spec that reaches the funnel in that shape;
  `## What a screened-shape strategy spec must state` lists what that spec
  owes.
- Mapping the funnel's Stage 2 and Stage 3 to instrument v3
  (`V3_FUNNEL_REFUSAL` stays).
- More than one race shape per idea at the screen.
- Any change to the v72 filter gate, the v92 harvest gate, avoid mode's
  clauses or the trail race.
- Reopening any funnel row. v180's structural Turtle Soup arm stays closed.
- A point-in-time earnings calendar for the ladder's window. None exists
  for 2017–2020, so earnings inside the holding window are not reported.

## Anti-goals (a failure even if everything "works")

- A null chosen because it produces more passes. The placebo decides, on
  synthetic data, before any real idea is read under v2.
- A second re-screen. `screen2-<name>` ids are one shot like every screen id.
- The ladder becoming more places to tune. Each rung is one frozen shot
  with no parameters of its own.
- The additive gate applied to a filter, or to a strategy that removes rows.

## Design

### Part A — screen v2

**A1. Placebo harness** (`swingbot/core/backtesting/screen/placebo.py`,
`scripts/backtest/screen_placebo.py`). Two synthetic universes with no edge
by construction, each written to its own cache directory **on the real
trading calendar 2010-01-04..2019-12-31**, with a membership file giving
every synthetic ticker one all-window span and a synthetic `SPY` built as
the universe's equal-weight index after generation:

- `gbm`: 200 tickers, driftless geometric random walk whose daily
  volatility follows a two-state (calm / stressed) Markov regime per ticker
  with a shared market state, levels drawn from the cached universe's ATR%
  quartiles, so volatility clusters and ATR14 lags it; open/high/low from an
  intraday range model fitted to the same quartiles. One seed per ticker,
  derived from seed 42 and the ticker name, so the universe does not change
  with the ticker count.
- `shuffled`: the real `data/backtest_cache_ext` bars with **single trading
  days** permuted, the same permutation for every ticker, so each day's
  cross-section survives and no serial structure does; prices rebuilt from
  the permuted daily returns and intraday ratios; seed 42; the results doc
  records the source files' hashes.

Six placebo triggers, defined in the harness and never registered as ideas:
`p_high20` (close above the prior 20-bar high), `p_rsi2_dip` (close >
SMA200 and RSI(2) < 10), `p_gap_up` (open ≥ prior close + 0.5 × ATR14),
`p_sweep20` (low under the prior 20-bar low, close back above), and two
market-scope triggers: `p_market_down` (the synthetic index closes down
more than 1.5 of its own 20-day standard deviations) and `p_month_turn`
(the last trading day of the month).

The pipeline's window constants, membership path and context loader take
parameters where they are module constants today; defaults keep today's
behaviour byte-identical. The harness writes its own manifest and does not
use `--pin-context`.

Output: `docs/superpowers/results/<date>-v230-null-placebo.md`, one row per
universe × trigger × null: N, mean R_event, mean R_null, Δ, 95% interval.

- Under `v1` the table **is the measurement of Defect 1**, recorded as
  found. If every |Δ| is within 0.02R, the premise of this spec is wrong:
  the results doc says so, A2–A5 do not run, and Parts B and C proceed on
  the v1 null.
- Under `v2` the acceptance rule is: every cell has |Δ| ≤ 0.02R, and every
  cell's interval half-width is ≤ 0.02R (a cell too noisy to judge is
  enlarged by more synthetic tickers, never waved through). Intervals are
  reported; "contains zero" is not a clause, because twelve cells at 95%
  would reject a correct null about half the time. One failing cell stops
  Part A. No fallback null is tried inside this spec.
- A planted-edge check: with a +0.5 ATR drift injected after `p_high20`
  events, v2 recovers a Δ whose interval contains the planted value, so the
  null is not blind.

**A2. The v2 null** (`swingbot/core/backtesting/screen/null_v2.py`). v1's
`null.py` is not edited: a golden test pins one v1 draw, and
`null_seed`'s signature stays. v2 is a different pipeline shape, in three
stages, because the pool for an event on one ticker is made of other
tickers:

1. **Panel pass (per ticker, checkpointed per ticker).** For every member:
   on the shared calendar, the eligible flag (member, warmed up, race
   completes inside its own data, as v1), the trend state
   (`close > SMA200`), ATR14 as a percent of close, the idea's event flag
   and, in avoid mode, its control flag. Stored as one panel artefact. Every
   value at *t* is a function of that ticker's bars ≤ *t*, except race
   completeness, which reads the ticker's data end exactly as v1 does; the
   results doc says so.
2. **Draw pass (per date, one artefact).** For an event on ticker *i* at
   date *t*, the pool is every other ticker *j* that is eligible at *t*, has
   the same trend state, sits in the **same ATR% tercile of that date's
   eligible cross-section**, and has no event of this idea at *t*. K = 20
   drawn without replacement, floor `MIN_CANDIDATES` = 5. One generator per
   date, seeded `null_seed(idea + ":v2", t.isoformat())`, consumed over that
   date's events in sorted ticker order. The draw table (event, null ticker,
   null position) is written once and is the only source for stage 3.
3. **Race pass (per null ticker, checkpointed per ticker).** Null bars are
   grouped by their own ticker, raced on that ticker's frame with that
   ticker's ATR14, and scattered back to their events. No more than one
   frame is resident at a time.

- **Level-entry ideas:** the event's depth in ATR units is applied to the
  null ticker's own ATR14 and prices; an unfilled null slot is replaced
  from the rest of the same date's pool. **Avoid mode's control arm** is
  the same draw with the control flag required of *j*. Both are new code
  paths in `null_v2.py`, not a pool swap.
- **Market-scope ideas** declare `SCOPE = "market"` (default `"ticker"`,
  part of the frozen definition, pinned in `test_ideas_registry.py`):
  triggers that fire for every member on one date (`turn_of_month`,
  `bond_spike_rebound`, `dollar_drop`). Their pool is the same ticker and
  trend state on dates in the **252 trading days before** the event,
  excluding every date within `CAP` bars of any event date; floor 5; seed
  `null_seed(idea + ":v2", ticker)`. Trailing only, so no null bar postdates
  the event.
- **Refusals before any outcome is read:** `SCOPE_MISMATCH` when a
  ticker-scope idea leaves fewer than 5 candidates on more than half of its
  event dates; `NULL_STARVED` when a market-scope idea does.
- The checkpoint manifest carries `null_version`, `SCOPE` and the stage; a
  v1 checkpoint never resumes under v2.
- **What a v2 delta means.** The same-date null removes market timing: a
  ticker-scope pass says the trigger picks better names than its peers on
  that day, a different question from v1's. Every v2 results doc says so and
  prints, for both arms, the mean cost in R, the per-regime means (2011–2017,
  2018 Q4, the rest) and, where a sector map is available, the sector mix.

**A3. Pass rule.** `SCREEN-PASS` under `screen-v2` needs the four v1
clauses unchanged (ΔExpR ≥ +0.10R, lower 95% bound > 0, ≥ 7 of 9 years,
N ≥ 300) **and**, for an idea screened for the first time under v2, a
fifth: the week-clustered lower 95% bound of mean R_event, net of costs, is
above zero. The fifth clause applies to `MODE = "edge"` only. Avoid mode's
six clauses are unchanged, read against the v2 pool.

**A4. Instrument and ids.** Ledger `instrument` is `screen-v2`. A new idea
keeps the id `screen-<name>`; `screen_idea.py` runs v2 only from this
plan's merge. Every results doc prints the null version and scope.

**A5. Batch re-screen.** The twelve ideas with a `screen-v1` row
(`high52w`, `uptrend_pullback`, `gap_volume`, `turn_of_month`,
`bond_spike_rebound`, `dollar_drop`, `sweep_reclaim_bos`, `turtle_soup`,
`range_breakdown_close`, `shock_support_break_short`,
`shock_failed_bounce_short`, `fvg_overhead_aged`) run once each under v2
with every parameter, race shape, mode, cap, window, universe, data source
and cost model as first run.

- **The fifth clause is reported for these twelve and never gates them.**
  Their event arm is unchanged by the re-screen and has already been read
  (this spec's own table prints four of the means), so a threshold on it
  would be chosen after the data. Their absolute return is tested on unread
  data by the ladder's hold rule instead.
- Ids `screen2-<name>`; `screen_idea.py --rescreen-v1` accepts exactly these
  twelve names and refuses a `screen2-` id that already exists.
- The twelve p-values join the ledger's one Benjamini-Hochberg family, as
  every screen does; q-values are reported and never gate.
- The v1 rows stay in the ledger untouched. Each `screen2-` row's record
  names its v1 row.
- **The v2 verdict supersedes the v1 verdict for licensing.** A v1 pass that
  fails v2 no longer licenses a spec. A v1 fail that passes v2 has earned
  the ladder (Part B), nothing more.
- Summary: `docs/superpowers/results/<date>-v230-rescreen-summary.md`, old
  and new verdict side by side, both arms' means.
- The scout slate of 2026-11-16 and any other unscreened idea run on v2
  after this batch, as ordinary first shots with all five clauses.

`backtest-methodology.md` § Stage −2 gains the v2 null, the fifth clause,
`SCOPE`, and one dated paragraph recording partner decision 2 and its limit.

### Part B — the replication ladder

`scripts/backtest/replicate_idea.py`, core in
`swingbot/core/backtesting/screen/ladder.py`. It takes a `SCREEN-PASS` idea
(`screen-v2` instrument) and runs four rungs in order. Every rung is one
frozen shot with a ledger row `ladder-<name>-r<N>`, instrument `ladder-v1`.

| Rung | Changes from the rung above | Population |
|---|---|---|
| 1 robustness | data source and period | the screen's trigger and race shape on the PIT S&P 500 Alpaca store `data/market_data_pit/` (bars from 2016-01-04), events 2017-03-01..2020-12-31, v2 null |
| 2 orderable | where the levels are anchored | rung 1's events; stop and target at the same ATR multiples but measured from the **signal close**, so both prices and the share count are known when the alert posts; entry still the next open |
| 3 bot stop | the stop | rung 2's events, the bot's stop for that entry, the target distance in R held constant |
| 4 bot target | the target | rung 3's events, the bot's target band (1.5–2.5 R:R, nearest level, no level means no trade) |

- **Rung 1 is a robustness check, not an independent replication.** 2017–2019
  lies inside the screen's window on the same universe; only the data source
  and 2020 are new. Each results doc prints 2020 on its own line. For
  `turtle_soup` a screen-style race on Alpaca 2018–2022 (watchlist) has
  already been read at −0.046R in v180's results doc; its rung 1 doc
  discloses that.
- **Hold rule, every rung:** the week-clustered lower 95% bound of net mean
  R is above zero, N ≥ 300. N < 300 is `LADDER-UNDERPOWERED`; any other miss
  is `LADDER-FAIL`; else `LADDER-HOLD`. Rung 1 also needs ΔExpR against the
  v2 null to be positive.
- **Fills, every rung.** No event is dropped for a gap. A stop gapped
  through fills at the open, at its realised R, worse than −1R. On rung 2
  and below, an open already beyond the stop is an entry at that open
  followed by the stop, at its realised loss; an open beyond the target is
  an entry at the open with the target order resting above nothing, raced
  from there. Each doc counts gap-through events and their summed R.
- Costs are 5 bps a side plus commission on every rung, with the book
  re-priced at 2 × slippage beside it, never gating. Short ideas also carry
  whatever borrow cost the engine's frictions module charges shorts.
- Rungs 3 and 4 call the live stop and target functions on each event bar
  (`swingbot/core/planning/targets.py:select_structural_target` and the
  stop builders in `swingbot/core/planning/builders.py`; the builder names
  the exact entry points). Levels are computed from the frame truncated at
  the event bar; a truncation test proves the stop and target do not change
  when later bars are removed. Runs checkpoint per ticker.
- Rung 3 sizes to fixed dollar risk, so a wider stop means a smaller
  position, not a dropped trade; the share of events the 2% price-distance
  clamp would have dropped is reported.
- Each rung reports the paired difference to the rung above on the shared
  events, with its interval. Rung 4 reports attrition (no level in band,
  risk cap) and the share of events that survive one position per ticker
  and the bot's concurrent-position limit, with signals per day at p95 and
  maximum. These are reported, never gating: the book is judged in Part C.
- The watchlist subset of rung 1 is printed beside it, never gating.
- An idea whose `CONTEXT` series is missing from the store (the store has
  SPY and TLT, no UUP, so `dollar_drop`) is refused `LADDER-UNAVAILABLE`,
  no shot spent. The membership file is checked against the store's tickers
  before the run.
- The ladder never reads 2021 or later.

**What a ladder buys (partner decision 4):**

| Outcome | Next step |
|---|---|
| rung 1 fails or is underpowered | idea closed as a non-replication; later rungs do not run |
| rungs 1–4 hold **and** rung 4's paired difference to rung 2 is not significantly negative (its interval is not wholly below zero) | a strategy spec in the bot's shape |
| rungs 1 and 2 hold, the line above does not | a strategy spec in the **orderable screened shape** (rung 2), sized to the 2% dollar-risk rule; the failed rung closes that bot stop or target for this idea |
| rung 1 holds, rung 2 does not | see `## Open for the partner` |

A strategy spec's `**Screen:**` line cites the `SCREEN-PASS` id as today;
from this spec's merge its body must also cite its ladder rows and name the
shape the ladder selected. That is a documentation rule in
`document-conventions.md`, not a new header line.

### What a screened-shape strategy spec must state

A strategy that ships in the rung 2 shape is traded by the partner with
resting orders. Its spec owes, in its own text:

- the order set placed at the alert: a market-on-open entry, a stop order
  and a limit target at the alert's prices, and the share count from the
  close-anchored risk; and the broker cut-off for market-on-open orders;
- the time-cap exit: a closing order on session `CAP` that the partner must
  place or that the bot must ping, never a resting order left to outlive the
  plan;
- that a `trail`-shape idea is not shippable until a nightly stop-update
  path exists (already in `backtest-methodology.md` § Stage −2);
- the realised risk when the open gaps: actual dollar risk differs from the
  2% plan by the gap, and the spec must show its distribution.

### Part C — the additive-strategy gate

`swingbot/core/backtesting/acceptance_additive.py`, selected by
`validate_component.py --gate additive`. It applies when the component arm
**only adds rows** to the baseline, apart from displacement (below).
Anything else is refused with `ADDITIVE_GATE_MISUSE` and belongs to v72 or
v92.

| # | Clause | Instrument | Threshold |
|---|---|---|---|
| 1 | `own_expectancy` (objective) | added rows' net ExpR, week-cluster bootstrap | lower 95% bound > 0 (one-sided p reported) |
| 2 | `win_rate_above_breakeven` | added rows' decided win rate against the **realised** break-even `avg loss / (avg win + avg loss)` of those rows, same bootstrap | lower 95% bound > break-even |
| 3 | `book_net_gain` | paired change in the book's total R (sum, not mean), strategy on against off | point estimate > 0 and lower 95% bound > −10% of the added rows' total R; `SKIPPED` when no baseline row is displaced |
| 4 | `stability` | per-fold net ExpR of the added rows, folds 2021 / 2022 / 2023 | > 0 in ≥ 2 of 3, no fold below −0.10R, per-fold N ≥ 30 |

- **Week clusters, not ticker clusters.** An added strategy's signals bunch
  on market days (v180: up to 15 a day), so one bad week is one bet. This
  follows v192's week-clustered gate.
- **Displacement** is why clause 3 exists: an added position can block a
  baseline plan through the heat or one-position rules. A displaced row is a
  baseline key absent from the component arm; they are counted in clause 3
  and listed in the results doc, with the cause where the replay exposes it.
  Every other baseline row must be identical in both arms.
- **Costs are net on both arms.** Arm files gain a stamp `r_basis`
  (`net` / `gross`); the gate refuses arms whose stamps differ or are
  missing. This fixes the net-against-gross comparison v180 disclosed.
- **Stages.** −1 reachability. 0 an MDE precheck against an effect frozen
  before fold-train is read: the pre-registration states the expected own
  ExpR as half the selected ladder rung's net mean R (the measured 50–60%
  shrinkage), fold-train N comes from a count-only pass, and the shot is
  refused, budget intact, when the MDE at that N exceeds the expected
  effect. 1 clauses 1–3 on fold-train, with `plateau_report()` where a knob
  exists. 2 clause 4. 3 one VALIDATION shot, all four clauses.
- **Disclosures, never gating:** the added rows' maximum drawdown in R,
  longest losing streak, the share of total R from the five best weeks,
  signals per day at p95 and maximum, and the same-week correlation of the
  added rows' R with the baseline book's.
- No geometry lock and no pooled win-rate clause: an added strategy does not
  move the baseline rows' geometry, and clause 2 replaces the pooled
  comparison with the strategy's own arithmetic.
- The badge threshold (`win_rate >= 50`) is untouched. A strategy that ships
  through this gate carries the tier its own cell earns.

`backtest-methodology.md` gains `## Additive gate` beside `## Harvest gate`.

## Constraints

- No-lookahead: the v2 panel holds information at *t* only, apart from race
  completeness as stated in A2. A truncation test cuts every ticker's tail
  and shows the pool at *t* changes only through the completeness flag.
- One shot per id for `screen2-*` and `ladder-*`. A crashed run that wrote
  no result may be re-run once; the crash is recorded in a marker file
  beside the checkpoints and in the results doc.
- Long runs checkpoint per ticker or per stage as A2 and Part B describe,
  and a restart skips finished units.
- Determinism: seeds as stated, event order fixed (sorted ticker within a
  date), and golden tests pin one v1 draw and one v2 draw.
- Every new or changed function stays under cyclomatic complexity 15.
- `screen_idea.py` already carries about a thousand lines; the v2 stages and
  the re-screen mode go in modules, not in the script.

## Testing

- Placebo harness: both universes reproduce from their seeds; the
  planted-edge check; the acceptance rule at its boundaries (|Δ| = 0.02,
  half-width = 0.02).
- v2 pool: no candidate has an event at *t*; none is the event ticker; trend
  state and ATR% tercile match; market-scope pools are trailing and exclude
  the embargo; `SCOPE_MISMATCH` and `NULL_STARVED` fire before outcomes;
  level-entry depth uses the null ticker's ATR; avoid control flag honoured.
- Verdict: the fifth clause gates a first-shot edge idea, is reported-only
  for a `screen2-` id, absent in avoid mode; v1 verdict functions unchanged
  (existing tests stay green untouched).
- Re-screen: refuses a thirteenth name, refuses an existing `screen2-` id,
  leaves v1 rows byte-identical.
- Ladder: rung order enforced, a rung refused without the hold above it,
  hold rule edge cases at N = 299 / 300 and bound = 0, gap-through fills
  priced not dropped, the truncation test for stops and targets,
  `LADDER-UNAVAILABLE` on a missing context series.
- Additive gate: each clause at its boundary, misuse refusal when the arm
  removes a non-displaced row, clause 3 `SKIPPED` with no displacement,
  mixed or missing `r_basis` refused, Stage 0 refusal.
- `tests/hooks/` doc tests for the methodology and conventions edits; the
  Codex mirror (`AGENTS.md`, synced skills) in the same commits.

## Plans

1. **Plan 1 — screen v2 and the re-screen** (Part A): placebo harness and
   the v1 measurement, the three-stage v2 null and `SCOPE`, the fifth
   clause, the batch re-screen, methodology docs and the `screen` skill.
2. **Plan 2 — ladder and additive gate** (Parts B and C). It starts after
   Plan 1's null lands, because the ladder's rung 1 uses it. Written
   2026-11-19 as plan **v238**
   (`plans/2026-11-19-v238-replication-ladder-additive-gate_0-index.md`);
   rung 1 runs on the v1 null (stop gate 2 = STOP) and the ladder also
   accepts `screen-v1` passes, flagged biased-null (partner, 2026-11-19).

## Found while briefing Plan 1 (2026-11-16)

The code brief found five things Part A did not name. The rulings:

- **`screen-v2` joins `stats.INSTRUMENTS`**, or `validate_ledger_row`
  rejects every new row.
- **A ledger row has fixed fields.** A `screen2-` row names its v1 row in
  its hypothesis text and in its results doc, not in a new column.
- **The guardrail hook refuses the re-screen today.**
  `.claude/hooks/guardrails.py` (`_rule_screen_rerun`) denies a real run of
  any idea that has a `screen-<idea>` row and whitelists the script's
  options. Plan 1 extends it narrowly: `--rescreen-v1` is allowed for
  exactly the twelve names in A5, each only while its `screen2-<name>` row
  is absent; every other re-run stays denied. The change ships with tests
  in `tests/hooks/test_guardrails.py` and its `.codex/hooks.json` mirror.
  This implements partner decision 2 and widens nothing else.
- **One multiple-comparison family.** `screen2-` rows and every later
  `screen-v2` row report q over all ledger rows, as `publish` computes it.
  `diagnostics.screen_family_q`'s per-instrument text ("across the
  `screen-v1` family") is updated to match, with its pinned tests.
- **Descriptive blocks that read the null draw** (forward-drift excess,
  restricted, shock and level blocks) are computed from each null bar on
  its own ticker's frame. A block that cannot be computed that way is
  omitted and its results doc says so. None of them gates.

None of the twelve re-screen ideas uses a level entry or the trail race, so
the batch exercises the next-open path only; the level-entry v2 path is
still built and tested, for new ideas.

## Left to the builder

- The intraday range model for `gbm` bars and the exact rebuild of
  `shuffled` prices.
- The panel artefact's format and the exact live entry points for rungs 3
  and 4.
- How `validate_component.py` detects an add-only arm and where the replay
  exposes a displacement cause.
- Whether a sector map exists for the PIT universe; without one the sector
  mix line is omitted and the doc says so.

## Claude's calls, for the partner to check

- The 0.02R placebo tolerance and "no fallback null inside this spec".
- ATR% tercile matching in the v2 pool (costs are a smaller share of R for
  volatile names, so an unmatched pool would favour gap and breakout
  events).
- The fifth screen clause gating edge mode only. In a rising decade it is
  easy for longs and hard for shorts; a short idea that beats its null but
  loses money outright will fail it, by design. The per-regime lines are
  there so a short is not read on the bull years alone.
- Rung 1's window and N ≥ 300 per rung; the bot shape winning only when its
  paired difference to rung 2 is not significantly negative.
- Clause 3's −10% tolerance and clause 4's −0.10R fold floor.
- Power is still thin in Part C. On the 67-ticker watchlist an added
  strategy with about 200 trades and a per-trade spread near 1.2R needs
  roughly +0.16R to clear clause 1. The gate asks the right question; the
  v3 funnel mapping (below) is what gives it enough rows.

## Open for the partner

Decision 4 said "ship the screened shape". The veteran-trader seat found
that the screened shape as raced cannot be placed as resting orders when
the alert posts: its stop and target are offsets from the next open, a
price that does not exist yet. Rung 2 was added to measure the same shape
anchored to the signal close, which can be placed. One case is left
undecided: **rung 1 holds and rung 2 does not** (the edge needs
open-anchored levels). Shipping it would mean a market-on-open entry with
the stop and target placed by hand after the fill. This spec does not
decide that case; the first ladder result that lands in it brings the
question to the partner with its numbers.

## What follows

1. A methodology spec mapping funnel Stages 2–3 to instrument v3 for
   components that did not exist when v3's folds were tainted. It is the
   power fix for Part C and for every Stage 0 refusal.
2. Strategy specs for whatever the re-screen and ladder pass.
3. A small pre-registered exit family per idea, if the re-screen shows
   signals dying on shape.
4. A point-in-time earnings calendar for 2017–2020, so the ladder can report
   earnings inside the holding window (fundamental-analyst seat).

## Parallelisation

- Plan 1 is a chain: placebo harness → v1 measurement → v2 panel, draw and
  race stages → placebo acceptance → fifth clause → re-screen runs → docs.
  Each step reads the previous step's result, and the acceptance step can
  stop the plan. Inside the v2 null, the level-entry and avoid-mode paths
  are independent of each other once the draw pass exists.
- Plan 2 has two independent groups after Plan 1's null lands: the ladder
  (Part B) and the additive gate (Part C) share no files. They join at the
  methodology-doc task.
- Plans 1 and 2 are sequential on one edge only: the ladder imports the v2
  null.

## Panel review

Spec review, 2026-11-16, serial: quant-researcher, quant-engineer,
veteran-trader. Line numbers refer to the spec as first committed
(`68c6f7c0`).

**BLOCKING**

- quant-researcher: the fifth clause gates twelve re-screens whose event arm
  is already read (spec:186-203) -- applied: reported-only for `screen2-`
  ids, gating for first-shot ideas (A3, A5).
- quant-engineer: the same-date pool cannot be built in the per-ticker loop
  (`screen_idea.py:610-634`) -- applied: three-stage v2 pipeline (A2).
- quant-engineer: the per-ticker checkpoint cannot hold v2 and its manifest
  lacks the null version (`screen_idea.py:538-556`) -- applied: staged
  checkpoints, manifest fields (A2).
- quant-engineer: seed and generator order undefined for date-keyed draws
  (`null.py:35-37`, `:153-166`) -- applied: one generator per date, ISO date
  key, sorted-ticker order, golden tests (A2, Constraints).
- quant-engineer: level-entry and avoid mode are not "unchanged"
  (`null.py:106-150`, `screen_idea.py:399-410`) -- applied: named as new
  code paths with their rules (A2).
- quant-engineer: synthetic universes do not fit the pipeline's hard-wired
  window, membership and context (`screen_idea.py:68-70`, `:491-504`) --
  applied: real calendar, membership file, synthetic SPY, parameterised
  constants (A1).
- quant-engineer: rung 1 data gaps, no UUP and a tight warm-up
  (`data/market_data_pit/`) -- applied: events from 2017-03-01,
  `LADDER-UNAVAILABLE`, membership check (Part B).
- veteran-trader: the screened shape cannot be placed as resting orders at
  the alert (spec:251-257) -- applied: rung 2 "orderable", the strategy-spec
  obligations section, and the undecided case in `## Open for the partner`.
- veteran-trader: gap-through stops counted as attrition, not priced
  (spec:243-246) -- applied: fills rule on every rung, gap-through count and
  R reported (Part B).

**ADVISORY**

- quant-researcher: "interval contains zero" over ten cells rejects a
  correct null about 40% of the time -- applied: tolerance on Δ plus a
  half-width requirement (A1).
- quant-researcher: 5-day blocks keep serial structure; constant-volatility
  `gbm` hides ATR lag -- applied: single-day permutation, regime-switching
  volatility (A1).
- quant-researcher, veteran-trader: no volatility matching; market timing
  netted out; beta and sector unmatched -- applied: ATR% tercile matching,
  the "what a v2 delta means" statement, cost-in-R and sector mix reported
  (A2). Sector matching in the pool itself -- rejected: it would cut pools
  below the floor on thin dates; the mix is reported instead.
- quant-researcher: the market-scope pool included post-event bars and had
  one placebo trigger -- applied: trailing 252 days, `p_month_turn` added.
- quant-engineer: market-scope pools can starve; the mismatch check was
  one-sided -- applied: `NULL_STARVED`.
- quant-researcher: a separate BH family of twelve departs from the
  ledger's one family -- applied (A5).
- quant-researcher: rung 1 is not independent (2017–2019 overlap; Turtle
  Soup's Alpaca race already read) -- applied: renamed robustness, 2020
  printed alone, disclosure (Part B).
- quant-researcher: rungs held on an absolute bound alone, so a weaker bot
  shape could win -- applied: paired-difference condition (Part B table).
- quant-researcher: clause 5 duplicated clause 1 -- applied: removed.
- quant-researcher: clause 3 demanded a lift under the name "no harm" and
  was redundant without displacement -- applied: `book_net_gain`, tolerance,
  `SKIPPED` case.
- quant-researcher: the Stage 0 precheck re-read fold-train -- applied: MDE
  against an effect frozen in advance.
- quant-researcher, veteran-trader: planned R:R understates break-even --
  applied: realised break-even (clause 2).
- quant-engineer: race completeness reads each ticker's data end -- applied:
  stated, truncation test (A2, Constraints).
- quant-engineer: live stop and target per event need point-in-time levels
  and cost control -- applied: truncation test, per-ticker checkpoints.
- quant-engineer: arms carry no net/gross marker and no displacement cause
  -- applied: `r_basis` stamp, displacement defined by key (Part C).
- quant-engineer: determinism details and a crash marker -- applied
  (Constraints); v1 pinned by a golden test -- applied.
- veteran-trader: entry form, liquidity and cost realism missing from the
  ladder -- applied in part: rung 2 covers the order form, 2 × slippage
  reported. A limit-entry rung and a size-against-volume check -- rejected:
  the universe is S&P 500 members and the screened entry is the open; a
  limit entry is a different idea needing its own screen.
- veteran-trader: the ladder is scored per event, not per book -- applied as
  reported lines on rung 4; gating stays in Part C, which replays the book.
- veteran-trader: what a screened-shape strategy must tell the trader --
  applied: its own section.
- veteran-trader: no drawdown, streak, concentration or correlation view;
  ticker clusters ignore same-day bunching -- applied: week clusters and
  the disclosure list (Part C). A gating drawdown clause -- rejected: no
  threshold can be frozen without reading a first result; revisit after the
  first strategy passes through.
- veteran-trader: shorts judged on a bull decade; borrow costs unnamed --
  applied: per-regime lines, borrow cost on the ladder. Borrow cost in the
  re-screen -- rejected: the re-screen freezes the first run's cost model.
- veteran-trader: earnings and OPEX inside the holding window -- rejected
  for now: no point-in-time earnings calendar exists for 2017–2020; listed
  under What follows.

## Panel review of Plan 1 (V230-1..5), 2026-11-18

quant-researcher, quant-engineer and veteran-trader reviewed the merged diff and the v1 results doc: no BLOCKING finding, stop gate 1 = BIAS stands (8 of 12 cells wholly outside ±0.02R). Advisories carried into plan v234 (not applied here, the v1 results are a closed measurement):

- quant-researcher: until v234 re-screens them, the `uptrend_pullback` (+0.367) and `turtle_soup` (+0.316) SCREEN-PASS rows sit inside the null bias (+0.27..+0.37R) and are not evidence of edge; "Cells past 0.02R" counts two NOISY shuffled cells as bias; `accept_cell` FAILs a wholly-outside interval before the half-width check (doc rule line omits it); a PASS still allows ~0.02R residual bias; the shuffled event means are positive (real drift), so the absolute-R fifth clause also measures beta; shuffled `copies>1` blends SPY across copies; v234 must freeze the maximum copies/tickers before any v2 cell is read (optional stopping).
- quant-engineer: `_month_turn` flags the final bar (not real lookahead, pin it in a test); placebo and scope/null-version are not in the checkpoint manifest, so a changed seed/trigger/null could resume stale pickles (key on the universe manifest hash and null version in v234); results doc lacks command, commit, bootstrap seed and gbm source hashes; shuffled universe is survivor-conditioned; `EVENT_START` default bound at definition time.
- veteran-trader: GBM gaps/regime/volume are unrealistic, shuffled market cells are effectively one series, only next-open long arms were tested (no limit entries, no shorts): the BIAS is proven for that arm only, not sized for real setups.
