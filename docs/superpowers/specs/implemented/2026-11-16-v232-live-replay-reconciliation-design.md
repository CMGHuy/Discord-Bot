# v232 — Live versus replay reconciliation, per direction

**Version:** ui 1.44.0 · bot 2.19.1
**Bump:** none (a one-off measurement: a read-only export mode, one new public wrapper around the existing exit walk, a report script and a results doc; nothing the bot scans, alerts on or posts changes)
**Edge:** none (integrity). It measures how far the backtest is from the live paper book and where; it lifts nothing.
**Screen:** exempt (integrity)
**Panel:** quant-engineer, quant-researcher, veteran-trader
**Status:** spec written 2026-11-16 from a brainstorm with the partner; the four decisions in `## Partner decisions` were made in chat the same day. Revised the same day after the panel (`## Panel review`).

## Why

The partner asked how to change the backtest process so that LONG and SHORT
trades can each be profitable. v231 (same day) defines what "profitable"
means per direction. This spec answers the question underneath it: **when
the backtest scores a plan, how far is that from what the live bot did with
the same plan, and what makes the difference?**

Nothing in the repo answers it today.

- The live book (exits 2026-07-20 to 2026-11-16, autopsy of 2026-11-16) is
  negative net in both directions. The funnel's replay rows book no costs
  and enter at a daily close.
- **Live is intraday; the backtest is daily.** Live scans during the
  session, enters market plans at the current price
  (`planning/builders.py`, `entry_price=close` on an in-progress bar) and
  checks exits on a 60-second quote poll
  (`commands/scanning/loops.py:trade_monitor`,
  `planning/plan_manager.py:monitor_quotes`). Replay enters at the signal
  bar's close or the next open and walks daily bars (`exit_sim.py`,
  `exit_sim_v2.py`). v228 measured that 54% of live longs close the day
  they open.
- The existing parity reports compare other things: the exit engine against
  the legacy loop on TRAIN (`parity_exits.py`), stops against a frozen copy
  (`parity_sizing.py`), v2 plans against legacy numbers
  (`shadow_parity_report.py`), data providers
  (`provider_parity_report.py`). `execution_fidelity_report.py` (v173)
  replays a live trade's own plan through the exit engine, for manual
  closes only. No tool compares the live book with the backtest plan by
  plan.

## Partner decisions (2026-11-16)

1. **Measure before fixing.** The first realism work is a reconciliation,
   not stricter replay rules and not an ongoing monitor.
2. **Headline window: live trades opened after the exit-model deploy of
   2026-09-15.** Earlier trades are replayed too and shown in separate
   tables marked as including code changes.
3. **Two layers.** Layer 1 replays each live plan through the backtest
   engine. Layer 2 runs the live-like scan replay and matches its signals
   to live plans.
4. **Signals live never traded are counted and explained, never scored.**
   Computing how they turned out would read 2026 outcomes nobody has seen
   and use up 2026 as untouched confirmation data for the base scan. The
   cost, accepted: the report cannot say whether the trades live missed
   would have made money.

## Goals

1. For LONG and for SHORT separately, state the difference in R between
   what live did with its plans and what the backtest records for the same
   plans, with a descriptive interval.
2. Split that difference into **entry** (fill price and timing), **exit**
   (same entry, different outcome) and **modelled costs**, so that the parts
   add up trade by trade.
3. Report **selection** in counts: how many signals each side took that the
   other did not, and why where the data says.
4. Name the mechanisms behind each part (same-day exits, wicks the poll
   never saw, gaps, opening minutes, moved stops) with counts, so follow-up
   specs know what to change.
5. Leave a script that can be re-run on a later window with one command.

## Non-goals

- Changing any replay rule, fill model or cost. The findings motivate later
  specs. The one code addition in `swingbot/` is a public wrapper that
  calls the existing exit walk from a given fill; no existing function is
  edited.
- A scheduled monitor, an admin panel, a table or a migration.
- Recomputing intraday excursions (v228) or the deferred-entry
  counterfactual (v229).
- Reproducing live exactly. Watchlist removals are not stored
  (`WatchlistRepository.remove` hard-deletes) and `.env` snapshots are
  pruned after 30 days, so layer 2 is approximate and says so.
- Any outcome for a signal live did not trade (decision 4).
- Any verdict on a strategy, filter or knob.

## Anti-goals (a failure even if everything "works")

- **The report read as "the backtest is fine because the gap is small".**
  The live book is a paper book filled from a polled quote. A small gap
  shows that the backtest agrees with the paper engine, not that either is
  achievable with orders a person places. The results doc opens with the
  caveat paragraph in `### What a paper book cannot show`.
- A backtest number from 2026 read as evidence for or against any
  component.
- Any table, in Markdown or committed JSON, that shows backtest R by
  strategy, horizon, ticker, ledger or parameter.
- A part of the gap chosen for fixing because it closes this window's gap
  most (see `## What follows`).
- A residual defined as "whatever is left".

## Design

A report script, `scripts/reports/live_replay_reconcile.py`, with its
modules in `scripts/reports/reconcile/`, shaped like the book autopsy
(`scripts/reports/book_autopsy.py`, `scripts/reports/autopsy/`). It runs on
the dev machine from exported rows and local bars and writes
`docs/superpowers/results/<date>-v232-live-replay-reconciliation.md` and
`.json`.

### Inputs

- **Live rows.** A new read-only mode of `scripts/ops/export_book_rows.sh`,
  `reconcile`, writes JSONL: one line per plan created in the window, with
  the plan doc, and the trade doc and journal doc where they exist. The
  existing `rows` mode is unchanged (it lacks `source`, `ledger`, `origin`,
  `legs`, `status_history` and `tp1_fraction`). The mode also exports
  `gate_rejections` rows for the window (ticker, gate, strategy, horizon,
  signal_date), the current `watchlist` table and the VM's
  `backups/deploys.jsonl`.
- **Bars: unadjusted daily bars.** Live fills are real quotes; the v162
  store's bars are split- and dividend-adjusted (`alpaca_provider.py`,
  `Adjustment.ALL`), and a dividend drift of 1% is large against a stop of
  about 1.8%. The report therefore reads raw daily bars for the window's
  tickers, fetched once through the Alpaca provider into a scratch cache
  with its own manifest, and read through the store's own frame reader, not
  the autopsy's CSV loader. A ticker with a split inside the window is
  refused and listed. A ticker whose bars end before its last live exit is
  refused and listed.
- **Costs.** `edge/frictions.py`: `apply_frictions`, `commission_r` and, for
  shorts only, `borrow_r` over the days held. Each side is priced once with
  the same calls. Live `r_realized` is gross (`analytics/journal.py`, from
  `metrics.r_multiple`; the autopsy states "live rows store gross R only").

### Populations

A live trade is **scored** when it has a closed journal entry, its plan was
created in the window, and its bars are usable.

| Split | Rule |
|---|---|
| Headline | trade opened at or after `2026-09-15T08:54:50Z` (`scripts/reports/autopsy/eras.py:ERA_BOUNDARY_UTC`) |
| Earlier | opened before it; own tables titled "includes code changes"; its tag counts are never pooled with the headline |
| Manual | close reason `manual` or `manual_bulk`: discretionary exits; their own line in the table, never in a mean |
| Still open | opened in the window, not closed at export: counted per direction, scored on neither side |
| Unfilled | plan issued, never filled (expired or cancelled): counted per direction and reason, with whether the backtest entry rule would have filled it (yes / no only) |
| Ledger | `main` and `weak` both scored; the split is shown for **live** figures only |

The era boundary and the manual rule were both set after the autopsy had
read this book. That is acceptable for a description and is stated in the
results doc. Every deploy inside the headline window (from `deploys.jsonl`)
is printed with its date and commit, as a known confound.

### Time and sessions

One function, `issue_session(issued_at)`, converts the UTC stamp to
`America/New_York` with `zoneinfo` (in Python; Git Bash has no zone data)
and returns the latest regular session whose open is at or before it. A
plan issued before the open belongs to the previous session. `issued_at` is
used where present, else `created_at`, and the source is recorded per row.

### Layer 1 — same plan, backtest outcome against live outcome

**Rehydration.** Each stored plan doc is loaded with
`plan_types.plan_from_dict` and reset to its issued state: `working_stop`
cleared, `legs_realized` and `status_history` emptied, status pending. The
live trade's own later stop moves are kept aside for tagging. `scale_out`
is passed as true exactly when the issued `tp1_fraction < 1`.

**Three values per scored trade, all gross.**

| Value | Entry | Exit |
|---|---|---|
| `R_live` | the live fill | what live did (`r_realized`) |
| `R_exit_only` | the live fill price on the live fill date | the backtest's exit walk from the **bar after** the fill date |
| `R_as_backtest` | the backtest's own entry for this plan from its signal bar | the same engine |

- **Signal bar** = the bar of `issue_session`. The backtest computes
  signals on completed bars, so a plan live issued at 11:00 on day D is a
  day-D signal for the backtest, which enters at D's close (v1 walk) or
  D+1's open (v2 fills). That uses prices live did not have at 11:00, on
  purpose: it is what the backtest does.
- **`R_as_backtest`** is the public engine unchanged:
  `exit_sim.simulate_exit(df, signal_index, plan, scale_out=…)` and
  `exit_sim_v2.simulate_exit_v2(df, signal_index, plan, instrument, …)` with
  `V2_FILLS`. The engines already handle each entry type (market,
  `stop_entry` trigger scan, `limit`, v180 and v192 next-open plans), so
  the spec adds no entry rule of its own. A plan the engine does not fill
  (`not_triggered`, `gap_through_stop`) is `backtest_no_fill`.
- **`R_exit_only`** needs an entry the public API cannot take. One new
  public function in `exit_sim.py`,
  `simulate_exit_from_fill(df, fill_index, fill_price, plan, *, scale_out)`,
  calls the existing private walker (`_walk_for(plan, scale_out)`) with
  `j = fill_index` and applies the same hold-cap handling `simulate_exit`
  applies. A parity test pins that, given the backtest's own entry bar and
  price, it returns exactly what `simulate_exit` returns, for every entry
  type and for a v192 waiting plan.
- Both fill models are reported (the v1 walk the funnel scores on, and v2
  fills), so the report also says how much of the gap stricter fills
  already close.

**One R unit.** All three values are expressed in the **live trade's risk
unit**: `|live fill − issued stop|`. `R_as_backtest` is converted from its
own per-share result. The re-based figure (R on the backtest's own
entry-to-stop distance) is printed beside it, with the median shift in stop
distance in percent, because a backtest entry nearer the stop is a
different trade and inflates its own R.

**Effects, per trade and per fill model, in live R units.**

- **exit effect** = `R_live − R_exit_only`
- **entry effect** = `R_exit_only − R_as_backtest`
- **modelled cost effect** = live net minus live gross, shown against a
  zero-cost backtest (what the funnel books today) and against an equally
  costed one (zero by construction; printed as a check).

The split is one of two possible orders. The other would need the outcome
of the backtest's entry under live's intraday exit handling, which nobody
observed. The interaction between entry and exit therefore sits in "exit",
and the results doc says so. "Entry" includes the intraday drift between
the live issue and the daily close, and is labelled that way.

**Mechanism tags**, from data already in hand:

| Tag | Rule |
|---|---|
| `same_day_exit` | live closed on the fill date (the daily walk never sees that day) |
| `wick_missed` | a daily bar's range touches the stop in force on a day live held through |
| `both_levels_bar` | a daily bar after entry contains the stop and a target |
| `gap_through` | an open beyond the stop or a target; with the gap size in R and percent and the live exit price relative to that open and to the stop |
| `exit_outside_rth`, `entry_outside_rth` | the live fill or exit stamp lies outside the regular session (the v64 RTH gate should make these rare; a count above zero is a finding) |
| `first_15min` | live entry or exit within 15 minutes of the open |
| `live_stop_moved` | the trade's stop changed after issue (break-even, trail), from `status_history` and `legs` |
| `levels_edited` | stop or target differs from the issued plan for a reason the engine's rules do not produce |
| `scaled_out`, `time_stop` | a partial leg was booked; the close reason is a time or stall exit |
| `earnings_in_window` | `days_to_earnings` at entry is inside the holding period, where recorded |
| `short_gap_against` | a short whose position saw an open more than 3% above the prior close |
| `outcome_flip_live_better`, `outcome_flip_live_worse` | live and `R_exit_only` disagree on win / loss, by sign |

`entry_slip` and `poll_fill` are **distributions, not only tags**: the
difference between the live fill and the planned entry, and between the
live exit price and the level it hit, as median and 90th percentile in
basis points and in R, per direction. A trade is tagged when the
difference exceeds 0.05R (on a stop near 1.8% of price that is about 9
bps, close to the two modelled fills).

**Output per direction, headline window:** N, entry weeks, total R and the
largest single week's share of it; the mean of each effect with a
week-cluster interval; the win / loss / scratch / timeout confusion matrix
of live against `exit_only`; tag counts with the mean exit effect per tag
(no interval); the `entry_slip` and `poll_fill` distributions; counts of
`backtest_no_fill`, re-based trades and the stop-distance shift.

### Layer 2 — which signals each side took (counts only)

The report runs the live scan code over the window through
`swingbot/core/scanning/scan_replay.py` (`replay_base_scan`,
`replay_short_universe` with the lanes the live configuration has on
today), with today's parameters, one decision a day at the close.

**No replay outcome is read.** `scan_replay` computes an exit for every
alert; the reconcile adapter keeps ticker, direction, source, decision
date, horizon, strategy, entry, stop and target, and drops `outcome`,
`r_multiple` and `exit_date` before anything is stored or printed. A test
pins that no layer 2 structure carries those fields.

Printed at the top of the section, with a coverage line each:

- what the replay leaves out: the strategy-sourced pass, the alert cap,
  portfolio heat, the live track record; the decision price is the close;
- **tickers:** the union of the current watchlist and every ticker in a
  live plan, trade or gate rejection in the window. Tickers removed from
  the watchlist that never produced anything are missing, so replay-only
  counts are a lower bound, and the doc says so;
- whether `ReplaySpec.snapshot_fn` covers every session of the window, and
  whether the short reference panel (SPY, sector ETFs, extra symbols) has
  bars for it; sessions without coverage are listed.

**Match.** A replay alert and a live plan match when ticker and direction
are equal and the replay decision date is within one session of the live
plan's `issue_session`. Ties go to the same horizon, then the nearest date.
One-to-one. Live plans with `source = "strategy"` are set aside as "outside
the replay" (they stay in layer 1).

| Class | Meaning | Reported |
|---|---|---|
| matched | both sides produced it | N; the difference between the two plans' levels: entry in percent, stop distance as a ratio, target distance as a ratio (levels only) |
| live-only | live issued it, replay did not | N by issue time (open to 10:30, mid-day, last hour, outside the session); live R as the autopsy already knows it; the unexplained share |
| replay-only | replay alerted, live issued nothing | N by reason: a `gate_rejections` row for that ticker and date (gate named), an open live position in that ticker, unexplained. **No R.** |

### The reconciliation table

One table per direction and fill model, headline window, in total R (live
units), so the lines add. Every line is the sum of per-trade rows, and the
self-check recomputes each from the rows:

```
SHORT, trades opened 2026-09-15 to 2026-11-16, v1 walk
                                                    total R    N
  Backtest of the plans live traded (zero cost)        …       …
  + entry effect                                       …
  + exit effect                                        …
  = Live, gross, scored trades                         …       …
  − modelled costs                                     …
  = Live, net, scored trades                           …       …
  + backtest would not have filled (live net)          …       …
  + manual closes (live net)                           …       …
  + not scoreable: bars refused (live net)             …       …
  = Live book, net                                     …       …

  Selection, counts only: matched … · live-only … · replay-only …
  · outside the replay (strategy-sourced) … · still open … · unfilled …
```

There is no remainder line. If the per-trade sums do not reproduce the live
book's total within 0.01R the run fails.

### Statistics

- Intervals come from `instrument/stats.py:week_cluster_bootstrap` with
  `WEEK_BOOTSTRAP_SEED`, on the per-trade effect as a one-arm series
  clustered by entry week. No reimplementation.
- The headline window holds about nine entry weeks. Every interval is
  labelled "descriptive; under-covers below 20 clusters", and each cell
  carries N, the cluster count, total R, the largest week's share and the
  autopsy's `is_thin` flag (`scripts/reports/autopsy/cells.py`).
- Tag-level means carry no interval.
- The results doc prints how many cells it shows (tags × directions × fill
  models × eras, plus sub-reasons), so one large mean is read against the
  number looked at.

### Holdout discipline

- **What the run reads:** for plans live traded, the daily-bar outcome of
  the same plan, per direction. Live already traded these and the autopsy
  already read their R. **What it does not read:** any outcome of a signal
  live did not trade.
- The ledger row is `v232-reconciliation`, verdict `DESCRIPTION` (no p,
  outside the BH family), `instrument` v1, `n` per direction. Its
  hypothesis text states the two sentences above.
- Backtest R appears per direction only. The committed JSON holds
  aggregates. Per-trade rows, which carry strategy, horizon and ticker,
  are written to a git-ignored path; the doc records their SHA-256.
- **Citation rule, as strict as v190's:** a later spec may cite mechanism
  counts and shares from this report. It may not cite a backtest-R effect
  size from it as evidence, and it still owes its own screen or
  pre-registration.

### What a paper book cannot show

The results doc opens with this paragraph, verbatim in substance:

> The live book is a paper book. Entries and exits are filled at a quote
> polled once a minute, with no spread, no queue, no partial fills, no
> rejected orders and no failed locates. Costs in this report are modelled
> (5 bps a fill, commission, 0.5% a year borrow on shorts), not paid, and
> borrow availability is not modelled at all. A stop that a real order
> would fill at a gapped open is filled here where the poll saw it. So this
> report measures the backtest against the paper engine. It does not show
> that either is achievable in a real account; the eToro demo stage is the
> first place that can be measured. The "unexplained" shares carry the same
> warning.

## Constraints

- Read-only on production: the export is a `COPY` through
  `scripts/ops/ssh-hetzner.sh`; `.env` values are never printed.
- No-lookahead where it matters: `R_exit_only` walks from the bar after the
  fill date; the signal-bar rule is the backtest's timing by definition and
  is labelled as such.
- Layer 1 writes one result row per trade as it goes; layer 2 checkpoints
  per ticker; a restart skips finished units and the results are assembled
  from the checkpoint files.
- Deterministic and reproducible: the manifest records input SHA-256s, the
  raw-bar cache manifest, the commit, the scan parameters used for layer 2
  and the invocation.
- Every function under cyclomatic complexity 15.

## Testing

- `simulate_exit_from_fill` parity with `simulate_exit` for market,
  `stop_entry`, `limit`, a v180 next-open strategy and a v192 waiting plan;
  hold-cap handling included.
- Rehydration: a plan with a live break-even or trail replays from its
  issued stop; `scale_out` follows `tp1_fraction`.
- Layer 1 on synthetic bars: a long and a short for each of win, loss,
  scratch, timeout; each tag's positive and negative case; `gap_through`
  sizes; `backtest_no_fill`.
- One R unit: effects telescope (`R_live − R_as_backtest` = exit + entry)
  for every fixture trade; the re-based figure differs when the entry
  differs.
- Costs: a short pays borrow, a long does not; equal costing gives zero.
- Sessions: `issue_session` before the open, in session, after the close,
  on a weekend, and across the 2026-11-01 clock change.
- Layer 2: the adapter drops outcome fields; exact date, one session early,
  one late, two candidates, none; one-to-one; strategy-sourced plans set
  aside; each replay-only reason; each issue-time bucket.
- Populations: era boundary; manual closes on their own line; still-open
  and unfilled counted; a split ticker and a short-bars ticker refused and
  listed; an empty direction.
- The table: the self-check fails on a tampered row.
- The renderer and the committed JSON never carry backtest R keyed by
  strategy, horizon, ticker, ledger or parameter (a test over headings and
  JSON keys).
- Export: the new mode's fields pinned; the old `rows` mode unchanged.
- The tests join the suite that holds the autopsy tests
  (`tests/suites.toml`); split by feature if it passes `max_tests`.

## Plans

One plan: export mode; `simulate_exit_from_fill` and its parity tests;
layer 1; layer 2; table, statistics and renderer; the run itself
(dispatched to `backtest-runner`) and the results doc with its ledger row.

## Left to the builder

- The JSONL field names and the JSON results layout.
- How much of `execution_fidelity_report.py` and the autopsy's loaders is
  imported rather than copied.
- How the provider is asked for raw bars, provided the store's adjusted
  files are not touched.
- How `levels_edited` is told apart from engine stop moves in
  `status_history`.

## Claude's calls, for the partner to check

1. **Daily bars only.** The question is how far the *backtest* is from
   live, and the backtest is daily. A same-day exit is tagged and counted,
   not re-simulated on intraday bars (v228's job).
2. **Selection is reported in counts, not R**, following decision 4. The R
   table therefore covers only plans live traded.
3. **The backtest's signal bar is the session of issue**, so "entry"
   includes the intraday drift up to the close.
4. **Everything in the live trade's R unit**, with the re-based figure
   beside it.
5. **Raw bars fetched once for the window**, because adjusted bars and live
   fills are not the same prices.
6. **One new public function in `exit_sim.py`** that wraps the existing
   walk; nothing existing is edited.
7. **Today's parameters for the scan replay**, deploys listed.
8. **Per-trade rows stay out of git**; only their hash is committed.
9. **Tag cut-offs** (0.05R, 3% short gap, 15 minutes, one session for
   matching) are descriptive and frozen here.
10. **Panel roles:** quant-engineer, quant-researcher, veteran-trader.

## Clarifications from the code brief (2026-11-16, Claude's calls)

Found while gathering code for the plan; each resolves something the text
above left open.

1. **`R_exit_only` under v2 fills** reuses the v173 precedent,
   `analytics/override_fidelity.py:engine_path` (`fill_bar_exit`, then
   `walk_v2`), behind a small public from-fill function beside
   `simulate_exit_v2`. The v1 function is `simulate_exit_from_fill` as
   written.
2. **The fill-day check.** The engine runs `_fill_bar_exit` for limit and
   compression-short plans and not for market or `stop_entry` plans. Both
   from-fill functions take `fill_bar_check: bool`. The parity tests pass
   the engine's own setting per entry type; layer 1 always passes `False`,
   because the fill day is exactly the day the daily walk does not see.
3. **Raw bars** come from a defaulted `adjustment` parameter on the
   provider's daily fetch (default unchanged, `Adjustment.ALL`), written to
   a scratch store selected with `HISTORY_STORE_DIR` and read with
   `history_store.load(ticker, "daily")`. This is the second and last
   addition inside `swingbot/`; existing behaviour is byte-identical.
4. **`issue_session` is new**, built on `session.nyse_calendar()`,
   `US_MARKET_TZ` and `RTH_OPEN`. `override_fidelity.assign_session` maps a
   pre-open time to the same day and is not reused.
5. **Layer 2 counts depend on replay exit dates.** `scan_replay._alert`
   uses each alert's simulated exit day to apply the one-open-trade rule to
   later alerts in the same ticker. That use stays (it is the live rule);
   the outcome fields are still dropped at the adapter, and the results doc
   says that replay-only counts rest on replay holding periods.
6. **Export.** The `reconcile` mode uses `psql -At` with `row_to_json`, so
   the script stays free of write keywords and of a second `COPY`;
   `tests/scout/test_export_script.py` gains per-mode cases and keeps its
   read-only guards. The `rows` column list is untouched.
7. **One-arm bootstrap:** `week_cluster_bootstrap` is called with an empty
   baseline arm and a statistic over the drawn rows, whose items expose
   `entry_date`.
8. **Suite:** the new tests join `scout` (about 286 of 1,200).
9. **Per-trade rows** are written under a git-ignored directory chosen in
   the plan; the plan adds the ignore rule if none fits.

## What follows

1. Specs for realism changes (for example a same-day exit model, entry at
   the next open in the funnel, costs on funnel rows as v230 and v231
   carry). **Rule, frozen now:** such a change is justified by mechanism
   counts, and is judged by whether it reproduces live on a **later,
   unread window** (item 2). It is never chosen among alternatives by how
   much of this window's gap it closes. An entry filter suggested by a tag
   still needs a `SCREEN-PASS`.
2. Re-running the script on a later window.
3. If selection counts are large: storing watchlist history and a config
   snapshot on each plan, so the next reconciliation can be exact.

## Parallelisation

- The export mode, `simulate_exit_from_fill`, and `issue_session` are
  independent: parallel.
- Layer 1 needs the wrapper and the row shape: after those.
- Layer 2 needs the row shape and `issue_session`: after those, parallel to
  layer 1.
- Table, statistics and renderer need both layers: after both.
- The run needs everything plus the raw bars: last, a group of one.

## Panel review (2026-11-16)

quant-engineer (4 blocking, 8 advisory):

- BLOCKING: `R_exit_only` not expressible through `simulate_exit` --
  applied: `simulate_exit_from_fill` and its parity test.
- BLOCKING: the table had a plug (layer 2 replay R against layer 1 effects)
  -- applied: layer 2 carries no R; every line is a per-trade sum; no
  remainder line.
- BLOCKING: "signal bar's close" wrong per entry type; signal bar undefined
  -- applied: public engines unchanged decide the entry; signal bar is the
  issue session, labelled.
- BLOCKING: bar source and adjustment -- applied: raw bars, store reader,
  split tickers refused.
- Shared R denominator; rehydration reset -- applied.
- `scale_out` rule; earlier-era tags not pooled -- applied.
- Layer 2 input coverage -- applied: coverage lines.
- Inferred watchlist hides replay-only trades -- applied: current watchlist
  added, lower bound stated.
- Time zones and the 2026-11-01 switch -- applied.
- Costs applied once; `r_realized` content -- applied: gross confirmed.
- Layer 1 checkpointing, seed, manifest -- applied.
- Hand-off items -- taken by the other seats.

quant-researcher (2 blocking, 9 advisory):

- BLOCKING: replay-only outcomes read the 2026 holdout for the base scan --
  applied by partner decision 4: counted, never scored.
- BLOCKING: ledger split and an unnamed short mode would show component R
  -- applied: ledger split on live figures only; layer 2 has no R; heading
  and JSON-key test extended.
- Per-trade JSON a leak -- applied: git-ignored, hash committed.
- `DESCRIPTION` row and a citation rule -- applied.
- Nine clusters -- applied: descriptive label, cluster count, largest week,
  thin flag, no tag intervals.
- Attribution order -- applied: stated.
- R-unit inflation -- applied: live R units, re-based figure beside.
- Survivorship, unfilled plans -- applied: counted, one rule both sides.
- Manual closes and when the splits were chosen -- applied.
- Cell count -- applied.
- "What follows" invited selection on this window -- applied: rule frozen.

veteran-trader (11 advisory):

- No tag for a wick the poll missed; flips unsigned -- applied.
- 0.1R too coarse -- applied: distributions, 0.05R.
- Extended hours, opening minutes -- applied.
- Scale-outs, break-even, time stops, unfilled plans, earnings -- applied.
- Silent level changes -- applied: `levels_edited`.
- Short-specific items -- applied: `short_gap_against`, borrow caveat. A
  low-dollar-volume short tag -- rejected: no point-in-time liquidity field
  on live rows; the caveat paragraph covers it.
- 15:30 sub-reason -- applied: issue-time buckets, unexplained share.
- Modelled against paid costs -- applied: label and caveat.
- "The backtest is fine" reading -- applied: anti-goal and mandatory
  paragraph.
- Re-basing counts and stop-distance shift -- applied.
- Gap size and live exit relative to the open -- applied.

## Panel review (pre-close-out, merged diff 17a58dd5..b723d526)

quant-engineer, quant-researcher and veteran-trader all returned FINDINGS with no BLOCKING item. Every finding is ADVISORY and about what the printed figures invite a reader to conclude; none changes a committed number. All are deferred to the results doc's follow-up notes, never edited into the generated report by hand.

- quant-engineer: window end defaults to the run day, so a run during the session could score a partial bar; layer 2 reads today's dividend-adjusted store; per-trade rows and raw bars are not archived, only hashes -- deferred: record an explicit `--until` and run after the close on a rerun.
- quant-engineer and quant-researcher: tag means and confusion grids use all scored rows while the v2 effect rows use only trades the v2 backtest filled (N 413 against 296), and the v1 and v2 confusion grids are identical -- deferred: label the populations or compute per fill model.
- quant-engineer: live R is rescaled by `trade.stop_loss`, which may be the moved stop on the 186 stop-moved longs -- deferred: pin with a stop-moved test or use the issued stop as the unit.
- quant-researcher: the re-based backtest total (+1040.63R long headline v1) comes from five trades with near-zero stop distance and the effect means are tail-driven (mean +0.427 against median +0.071) -- deferred: show a median or trimmed column and flag the re-based figure; thin tag cells carry no thin flag; ledger `n` is combined (504) with the split in the record; layer 2 matches 54 of 494 long headline plans, so its counts describe the replay's setup more than live selection.
- quant-researcher: the 2026 per-direction backtest R is now published before v233 Spec 2 freezes its one holdout shot -- raised to the partner: whether v233 needs a disclosure line is their call.
- veteran-trader: `gap_through` pools stop gaps and target gaps; entry slip and poll fill are zero by construction in the paper engine; 94 of 413 long exits and entries are outside regular hours; 186 stop moves with no count of announced ones; `same_day_exit` flips sign with the fill model and is untestable on daily bars; the caveat omits CFD-versus-stock fills, borrow and squeeze, and metals having no bars; the pre-open plan subset has no gap result -- deferred: split the gap tag, label the zero-by-construction rows, add the missing caveats.

Skills: none affected (`rows` export mode and every engine function are unchanged; the new report lives under `scripts/reports/reconcile/`).
