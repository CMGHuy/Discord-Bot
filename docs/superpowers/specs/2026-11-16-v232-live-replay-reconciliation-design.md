# v232 — Live versus replay reconciliation, per direction

**Version:** ui 1.44.0 · bot 2.19.1
**Bump:** none (a one-off measurement: a read-only export mode, a report script and a results doc; nothing the bot scans, alerts on or posts changes)
**Edge:** none (integrity). It measures how far the backtest is from the live book and where; it lifts nothing.
**Screen:** exempt (integrity)
**Panel:** quant-engineer, quant-researcher, veteran-trader
**Status:** spec written 2026-11-16 from a brainstorm with the partner; the three decisions in `## Partner decisions` were made in chat the same day.

## Why

The partner asked how to change the backtest process so that LONG and SHORT
trades can each be profitable. v231 (same day) defines what "profitable"
means per direction. This spec answers the question underneath it: **when
the backtest says a trade set pays, how much of that survives contact with
the live bot, and what eats the rest?**

Nothing in the repo answers it today.

- The live book (exits 2026-07-20 to 2026-11-16, autopsy of 2026-11-16) is
  negative net in both directions. The funnel's replay rows book no costs
  and enter at a daily close.
- **Live is intraday; the backtest is daily.** Live scans during the
  session, enters market plans at the current price
  (`planning/builders.py`, `entry_price=close` on an in-progress bar) and
  checks exits on a 60-second quote poll
  (`commands/scanning/loops.py:trade_monitor`). Replay enters at the signal
  bar's close or the next open and walks daily bars (`exit_sim.py`,
  `exit_sim_v2.py`). v228 measured that 54% of live longs close the day
  they open.
- The existing parity reports compare other things: exit engine against the
  legacy loop on TRAIN (`parity_exits.py`), stops against a frozen copy
  (`parity_sizing.py`), v2 plans against legacy numbers
  (`shadow_parity_report.py`), data providers
  (`provider_parity_report.py`). `execution_fidelity_report.py` (v173)
  replays a live trade's own plan through the exit engine, for manual
  closes only. No tool compares the live book with a replay of the same
  period, plan by plan.

## Partner decisions (2026-11-16)

1. **Measure before fixing.** The first realism work is a reconciliation,
   not stricter replay rules and not an ongoing monitor.
2. **Headline window: live trades entered after the exit-model deploy of
   2026-09-15.** Earlier trades are replayed too and shown in a separate
   table marked as including code changes.
3. **Two layers.** Layer 1 replays each live plan's exit through the
   backtest engine. Layer 2 runs the live-like scan replay and matches its
   signals to live plans. The gap per direction is split into selection,
   entry, exit and costs.

## Goals

1. For LONG and for SHORT separately, state the difference in R between
   what live did and what the backtest would have recorded, with an
   interval.
2. Split that difference into four named parts: **selection** (trades only
   one side took), **entry** (fill price and timing), **exit** (same plan,
   different outcome) and **costs**.
3. Name, for each part, the mechanism counts behind it (same-day exits,
   gaps, both levels in one bar, live gate rejections, open-position
   blocks), so the follow-up spec knows what to change.
4. Leave a script that can be re-run on a later window with one command.

## Non-goals

- Changing any replay rule, fill model or cost. The findings motivate
  later specs; this one changes no engine.
- A scheduled monitor, an admin panel, a table or a migration.
- Recomputing intraday excursions (v228) or the deferred-entry
  counterfactual (v229).
- Reproducing live exactly. Watchlist history is not stored
  (`WatchlistRepository.remove` hard-deletes) and `.env` snapshots are
  pruned after 30 days, so layer 2 is approximate and says so.
- Any verdict on a strategy, filter or knob.

## Anti-goals (a failure even if everything "works")

- A replay number from 2026 read as evidence for or against any component.
  The window is holdout data for instruments v2 and v3 (v161 boundary 5).
- A table by strategy, horizon or knob that shows replay R. It would be a
  holdout read for every component at once.
- An unexplained residual hidden inside one of the four parts.
- A layer 2 match rate reported without its unexplained share.

## Design

A report script, `scripts/reports/live_replay_reconcile.py`, with its
modules in `scripts/reports/reconcile/`, shaped like the book autopsy
(`scripts/reports/book_autopsy.py` and `scripts/reports/autopsy/`). It runs
on the dev machine from exported rows and local bars and writes
`docs/superpowers/results/<date>-v232-live-replay-reconciliation.md` and
`.json`.

### Inputs

- **Live rows.** A new read-only mode of `scripts/ops/export_book_rows.sh`,
  `reconcile`, writes JSONL: one line per plan created in the window, with
  the plan doc, and the trade doc and journal doc where they exist. The
  existing `rows` mode is not changed (it lacks `source`, `ledger`,
  `origin`, `legs`, `status_history` and `tp1_fraction`, which this report
  needs). It also exports `gate_rejections` rows for the window (ticker,
  gate, strategy, horizon, signal_date) and the VM's
  `backups/deploys.jsonl`.
- **Bars.** Daily bars from the v162 Alpaca store (`data/market_data/daily`,
  refreshed with `scripts/ops/pull_history_store.sh`), the same source the
  funnel names for new pre-registrations. The report refuses a ticker whose
  bars end before the last live exit, and lists it.
- **Costs.** `edge/frictions.py`: `apply_frictions`, `commission_r` and, for
  shorts only, `borrow_r` over the days held. Both sides are priced with
  the same calls.

### Populations

A live trade is in scope when it has a closed journal entry and its plan
was created in the window.

| Split | Rule |
|---|---|
| Headline | trade opened at or after `2026-09-15T08:54:50Z` (`scripts/reports/autopsy/eras.py:ERA_BOUNDARY_UTC`) |
| Earlier | trade opened before it; own tables, titled "includes code changes" |
| Manual | close reason `manual` or `manual_bulk`; counted and shown apart, never in a mean |
| Ledger | `main` and `weak` both scored; every table carries the split |
| Outside replay | live plans with `source = "strategy"` in layer 2 only, because `scan_replay.py` leaves the strategy pass out; they stay in layer 1 |

Every deploy inside the headline window (from `deploys.jsonl`) is printed
with its date and commit, as a known confound.

### Layer 1 — same plan, two outcomes

For each in-scope live trade the report takes the plan **as issued**
(direction, stop, targets, fractions, hold caps) and computes three R
values on daily bars, all gross:

| Value | Entry | Exit walk |
|---|---|---|
| `R_live` | the live fill | what live did (`r_realized`) |
| `R_exit_only` | the live fill price, on the live fill date | the backtest's exit engine from the **bar after** the fill date |
| `R_as_backtest` | where the backtest would have entered this plan: the signal bar's close for the v1 walk, the next open under v2 fills | the same engine from that entry |

`R_as_backtest` is computed twice, once per fill model (`simulate_exit`,
and `simulate_exit_v2` with `V2_FILLS`), because the funnel scores on the
first and the stricter instruments on the second. Plan levels stay at their
absolute prices; R is re-based on the new entry-to-stop distance, and a
plan whose backtest entry lies beyond its stop is a `gap_cancel`, counted.

Then, per trade and per fill model:

- **exit effect** = `R_live − R_exit_only`
- **entry effect** = `R_exit_only − R_as_backtest`
- **cost effect** = (net − gross) on the live side minus the same on the
  backtest side; the funnel's v1 rows book none, so this is reported both
  against zero-cost replay and against equally costed replay.

Each trade also gets mechanism tags, from data already in hand:

| Tag | Rule |
|---|---|
| `same_day_exit` | live closed on the fill date (the daily walk never sees it) |
| `both_levels_bar` | a daily bar after entry contains the stop and a target |
| `gap_through` | an open beyond the stop or a target |
| `poll_fill` | live exit price differs from the plan level it hit by more than 0.1R |
| `entry_slip` | live fill differs from planned entry by more than 0.1R |
| `outcome_flip` | live and `R_exit_only` disagree on win / loss |

Output per direction, headline window: N; mean of each effect with a
week-cluster bootstrap 95% interval (week of entry, seed 42, 10,000
resamples); the win / loss / scratch / timeout confusion matrix of live
against `exit_only`; tag counts and the mean exit effect within each tag.

### Layer 2 — which trades each side took

The report runs the live scan code over the window through
`swingbot/core/scanning/scan_replay.py` (`replay_base_scan`,
`replay_short_universe`), with today's parameters, one decision a day at
the close. Its known differences from live are printed at the top of the
section: no strategy-sourced pass, no alert cap, no portfolio heat, no live
track record, decision price is the close.

- **Tickers.** The inferred watchlist: every ticker that appears in a live
  plan, trade or gate rejection in the window. Stated as inferred.
- **Match.** A replay alert and a live plan match when ticker and direction
  are equal and the replay decision date is within one session of the live
  plan's session date (`issued_at`, else `created_at`). Ties go to the same
  horizon, then the nearest date. One-to-one.

| Class | Meaning | Sub-reasons |
|---|---|---|
| matched | both sides took it | entry-price difference in R |
| live-only | live traded, replay did not | plan issued before 15:30 ET (an intraday signal the close may not show); otherwise unexplained |
| replay-only | replay alerted, live did not trade | a `gate_rejections` row for that ticker and date (gate named); an open live position in that ticker; otherwise unexplained |

Per direction: N per class and sub-reason; for matched trades the paired
live-minus-replay R; for live-only the live R; for replay-only the replay
R, **as a total and a mean per direction only**.

### The reconciliation table

One table per direction, headline window, in total R so the parts add:

```
SHORT, trades opened 2026-09-15 to 2026-11-16
  Replay book (layer 2, zero costs)          total R   N
  − replay-only trades                          …      …
  + live-only trades                            …      …      selection
  entry effect on matched trades                …             entry
  exit effect on matched trades                 …             exit
  costs                                         …             costs
  residual (strategy-sourced, unmatched math)   …
  = Live book, net                            total R   N
```

The residual is its own line and the report fails its self-check when the
lines do not sum to the live total within 0.01R.

### Holdout discipline

- The run is recorded in the pre-registration ledger with verdict
  `DESCRIPTION` (as the v190 re-baseline was), id `v232-reconciliation`.
- Replay R is printed per direction and class only. No table by strategy,
  horizon, ticker or parameter shows replay R; the JSON carries per-trade
  rows for audit, and the Markdown says that reading them by component is a
  holdout read.
- The scan replay runs on instrument v1, whose windows end in 2025; it has
  no 2026 shot to spend. v2 fills appear only in layer 1, on the bot's own
  issued plans, where nothing is selected.
- Every row is exploratory. A later spec may cite a mechanism count or an
  effect size from here as motivation; it still owes its own screen or
  pre-registration.

## Constraints

- Read-only on production: the export is a `COPY` through
  `scripts/ops/ssh-hetzner.sh`; `.env` values are never printed.
- No-lookahead in layer 1: the exit walk for `R_exit_only` starts on the bar
  after the fill date; `R_as_backtest` uses bars up to the signal bar for
  its entry.
- Adjusted bars: a live price is compared with a bar only when the bar's
  close on the fill date lies within 25% of the live fill (the autopsy's
  guard, `scripts/reports/autopsy/bars.py`); failures are listed.
- The layer 2 run checkpoints per ticker and a restart skips finished
  tickers; results are assembled from the checkpoint files.
- Deterministic: fixed seed, input SHA-256 manifest and invocation printed,
  as the autopsy does.
- Every function under cyclomatic complexity 15.

## Testing

- Layer 1 on synthetic bars: a long and a short for each of win, loss,
  scratch, timeout; `same_day_exit`; `both_levels_bar`; a gap through the
  stop; a `gap_cancel`; R re-basing when the backtest entry differs.
- Effects add: `R_live − R_as_backtest` equals exit effect plus entry effect
  for every fixture trade.
- Costs: a short pays borrow, a long does not; equal costing on both sides
  gives a zero cost effect.
- Matching: exact date, one session early, one session late, two candidates
  (horizon tie-break), no candidate; one-to-one; strategy-sourced plans
  excluded from layer 2 and kept in layer 1.
- Sub-reasons: a gate rejection row, an open position, an early `issued_at`,
  none.
- Populations: era boundary inclusive on the right side; manual closes
  excluded from means; empty direction; a ticker with short bars refused
  and listed.
- The reconciliation table's self-check fails on a tampered line.
- The Markdown renderer never emits a replay-R table keyed by strategy,
  horizon or ticker (a test over the rendered headings).
- Export: the new mode's column list pinned; the old `rows` mode's output
  unchanged.
- The tests join the suite that holds the autopsy tests
  (`tests/suites.toml`); split by feature if it passes `max_tests`.

## Plans

One plan: export mode; layer 1; layer 2; table and renderer; the run
itself (dispatched to `backtest-runner`) and the results doc.

## Left to the builder

- The JSONL field names and the JSON results layout.
- How much of `execution_fidelity_report.py` and the autopsy's row and bar
  loaders is imported rather than copied.
- The exact session-date conversion for `issued_at` (ET sessions).

## Claude's calls, for the partner to check

1. **Daily bars only.** The question is how far the *backtest* is from live,
   and the backtest is daily. Intraday detail is v228's job; here a same-day
   exit is tagged and counted, not re-simulated.
2. **Both fill models in layer 1** (the v1 walk the funnel uses, and v2
   fills), so the report also says how much of the gap stricter fills
   already close.
3. **Today's parameters for the scan replay**, with deploys in the window
   listed. Per-era code checkout was declined in decision 2.
4. **Inferred watchlist** for layer 2.
5. **Replay R shown per direction only**, never by component, to keep the
   2026 holdout unread for every existing strategy.
6. **A ledger row with verdict `DESCRIPTION`.**
7. **Thresholds for tags** (0.1R for `poll_fill` and `entry_slip`, one
   session for matching, 15:30 ET for the live-only sub-reason, borrowed
   from v229) are descriptive cut-offs, frozen here.
8. **Panel roles:** quant-engineer, quant-researcher, veteran-trader.

## What follows

1. A spec per large part of the gap: for example a same-day exit model for
   replay, entry at the next open in the funnel, or costs on funnel rows
   (v230 and v231 already carry the last).
2. Re-running the script after those land, on a later window.
3. If selection dominates: storing watchlist history and a config snapshot
   on each plan, so the next reconciliation can be exact.

## Parallelisation

- The export mode and layer 1's pure functions are independent: parallel.
- Layer 2 needs the export's row shape: after the export mode.
- The table needs both layers: after both.
- The run needs everything, plus pulled bars: last, a group of one.
