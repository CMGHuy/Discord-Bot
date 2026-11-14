# v226 — Stop-width attribution: does a stop that is tight in ATR terms cost expectancy?

**Version:** ui 1.41.0 · bot 2.18.4
**Bump:** none (a measurement: a report flag, one attribution grouping and replay checkpointing; nothing the bot posts, trades or shows changes)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer

## Why

On 2026-11-12 the partner asked why production shows so many losing trades.
A read-only look at the live book (production Postgres through
`scripts/ops/ssh-hetzner.sh`, `journal_entries` joined to `trades`; the
queries are in § Appendix) found no defect. These are observations of that
day, not re-derived figures:

- closed 2026-10-29..2026-11-12: N = 223, mean net R about +0.04, loss
  rate about 55%, and about 47% of trades stopped out the day they opened;
- every plan opened from 2026-10-01 to 2026-11-12 has its stop 1.75–2.00% of
  price from the signal close (the v115 clamp
  `builders._clamp_stop_to_hard_cap` plus `MIN_STOP_DISTANCE_PCT` 1.75), on a
  watchlist whose ATR14 runs near 5% of price;
- trades opened per week rose from about 30 (2026-09) to 77–105 (2026-11)
  without a new source: the existing Fib, FVG and Trendline families fired
  more, and fast stop-outs free slots for the next entry.

The obvious fixes are already measured and closed:

| idea | record | outcome |
|---|---|---|
| structural stop at the real level, dollar-risk sizing | v139 arm S (`results/2026-10-08-v139-armS.md`) | **NO_ELIGIBLE_CELL**: paired ΔExpR −0.026 to −0.033R on TRAIN, N ≈ 8,090, CI below zero; win rate up ≤ 1.3pp, planned RR 2.5 → 2.0 |
| no plan beyond a ceiling | v139 arm D (`results/2026-10-08-v139-armD.md`) | REFUSED at Stage 0 |
| ATR-band stops, keep or re-choose target | v191 arms K/R (`results/2026-10-24-v191-atr-band-stops.md`) | UNDERPOWERED at Stage 0 (81% of band plans newly admitted, no paired twin) |
| regime gate | v17 P2a (`backtest-methodology.md` § Closed pre-registrations); v146 (`results/2026-10-15-v146-expectancy-attribution.md` § regime2_state) | 0 of 44 cells; TRAIN 2020-01-06..2023-12-29: bull_volatile N = 934, ExpR −0.030 vs bull_quiet N = 2,438, +0.011 |
| re-entry cooldown after a stop-out | live book, all closed trades with `r_realized` to 2026-11-12 (§ Appendix query 2) | opened < 1 day after a same-ticker, same-direction loss: N = 169, −0.062R; never after a loss: N = 363, −0.056R |

Widening the stop has been tried and costs expectancy. What has **never been
measured** is whether plans whose stop is very tight *relative to the ticker's
volatility* form a population that loses. If they do, the answer would be to
skip those setups (a veto), not to widen the stop. Neither v146 nor any replay
split ExpR by stop distance in ATR (v191 spec § Why says so).

**What this study can and cannot show.** It is descriptive: it compares filled
TRAIN rows in one bucket with the rest. It does not estimate what a veto would
do to pooled ExpR, because a vetoed plan frees a slot that a different plan
would take. A `VETO-CANDIDATE` only licenses the screen and the paired replay
that would measure that (§ What each verdict buys).

## What changes

One attribution grouping and one pre-registered verdict, added to the v146
attribution study and written to a report of its own. Replay rows gain
per-ticker checkpointing. No stop, clamp, filter, alert or sizing rule changes.

### The grouping

**`stop_atr`** — stop distance in ATR14 units, as stored in the row's
`entry_context["stop_atr"]` (`swingbot/core/edge/context.py:90-94`):
`abs(signal close − stop) / ATR14`, both taken from the signal bar. It is
measured from the **signal close, not the planned entry or trigger**. It is
point-in-time because the replay passes the frame cut at the signal bar
(`scenario_rows.signal_fields`, `df.iloc[:hit.i+1]`). No existing test
truncates the frame for `entry_context["stop_atr"]`
(`test_signal_fields_ignore_every_bar_after_the_signal` covers
`signal_fields` only), so the plan adds one.

A row whose `entry_context` is absent, or whose `stop_atr` is missing,
non-numeric, or ≤ 0, is `unknown`.

**Why one grouping, not two.** Under the clamp `stop_pct` sits in a 1.75–2.00%
band, so `stop_atr ≈ stop_pct / atr_pct` is close to a monotone function of the
ticker's volatility. A second `atr_pct` grouping would repeat the same rows.
`atr_pct` (`stop_pct / stop_atr`) is therefore **disclosed only**: the report
prints the Spearman rho between `stop_atr` and `atr_pct` on TRAIN and the share
of rows that the `stop_atr` quartile and the reversed `atr_pct` quartile put in
the same bucket. If |rho| ≥ 0.8, the results doc states that the verdict is
about **ticker volatility**, not stop placement.

### Frozen bucket edges

`frozen_edges(rows, "stop_atr")` returns the TRAIN quartile cut points
(`numpy.quantile`, `method="linear"`) over known values only, reading no `r`.
Edges that coincide are merged, so there may be fewer than four buckets; an
empty bucket is never produced. A value equal to an edge goes to the upper
bucket. Live rows are bucketed with the **TRAIN** edges. Labels:
`Q1 (<a)`, `Q2 (a–b)`, `Q3 (b–c)`, `Q4 (≥c)`, values to two decimals. The
live cut points seen on 2026-11-12 (0.35 / 0.5 / 0.75) are **not** used: they
were chosen after the outcomes were visible.

### The pre-registered verdict (TRAIN only, computed once)

Expected TRAIN N: the v146 replay had 5,558 scored rows, so about 1,390 per
quartile if `unknown` is small.

Each bucket (at most 4 looks; `unknown` is disclosed, never a look) is compared
with **every other TRAIN row with a known `stop_atr`**, using the existing
week-clustered bootstrap (`expectancy_attribution._look`, 10,000 resamples,
seed 42). Δ = bucket ExpR − rest ExpR, in net R.

A bucket is a **veto candidate** when all six hold:

1. Δ ≤ −0.10R (exactly −0.10 passes);
2. the upper 95% bound of Δ is < 0 (exactly 0 fails);
3. bucket ExpR < 0 (removing a positive-ExpR bucket lowers Total R);
4. Δ < 0 in at least 3 of the 4 TRAIN calendar years 2020–2023 (a year with
   no bucket rows counts against);
5. bucket N ≥ 300;
6. Benjamini–Hochberg at q < 0.10 over **this study's own family** of bucket
   looks (at most 4), never pooled with v146's family or with live looks.

Study verdict:

- **`VETO-CANDIDATE`** naming every passing bucket;
- **`UNDERPOWERED`** when fewer than two buckets reach N ≥ 300. This does
  **not** close the question;
- **`NO CANDIDATE`** otherwise. This closes "tight stops in ATR terms" as
  measured, recorded in `backtest-methodology.md` § Closed pre-registrations.

This bar is weaker than the Stage −2 avoid screen (no 7-of-9-years clause, no
control arm). That is deliberate: this study only decides whether a veto idea
is worth screening at all.

For each bucket the report also prints the removal arithmetic: pooled ExpR with
and without the bucket, ΔTotal R from removing it, and N removed. The live
book is printed beside TRAIN for each bucket, with the same edges, and **never
gates** (live N is small and correlated). VALIDATION is never read.

### What each verdict buys

- **`VETO-CANDIDATE`** licenses a veto **idea**, not a veto. A volatility
  veto on a signal-bar feature is not exempt from the screen
  (`backtest-methodology.md` § Funnel stages: "A filter on anything known at
  the alert … is not exempt"). It must earn a `SCREEN-AVOID-PASS` from a
  Stage −2 avoid idea before its spec. That spec then measures the veto on
  the bot's own replay with replacement trades included (paired: the vetoed
  plan's slot is filled by whatever the bot would take next).
- **`NO CANDIDATE`** closes the question as above.
- **`UNDERPOWERED`** leaves the question open and names the N that would
  power it.

### Disclosures (printed, never gating)

Per bucket, TRAIN and live separately:

- N, win rate, ExpR net and gross, median planned RR;
- the mix: direction and horizon shares, plus Δ within each direction (long,
  short) where that stratum's bucket N ≥ 100. Strategy-family shares are
  **live only**: the TRAIN scenario row carries no strategy field
  (`scenario_rows.ROW_KEYS`), and the row contract is not widened for it;
- the share of rows flagged `stop_clamped`. This is a **lower-bound
  provenance flag**: it is identity-based (a natural stop that lands at 1.75%
  is flagged too) and reads `CLAMP_STOP_TO_HARD_CAP` at run time. `None` rows
  are excluded from its denominator, and their count is printed.
- **live only:** the share of losses closed on the entry day (from
  `opened_at`/`closed_at`). TRAIN rows carry only `signal_date`
  (`scenario_rows.ROW_KEYS`), so this half is not computed for TRAIN, and the
  row contract is not widened for it.

Per population: count of `unknown` rows (each falls outside the edges and the
bootstrap base), the `stop_atr`/`atr_pct` Spearman rho, and the mirrored-bucket
overlap.

## Data

- **TRAIN:** a fresh confluence replay over the v146 window
  (2020-01-06..2023-12-29 signal date) with
  `scripts/backtest/run_backtest_range.py --scenarios --train --trades-jsonl <path>`
  under today's live config, so every stop passes the v115 clamp as in
  production. It reads the v162 training-data store
  (`swingbot/core/marketdata/training_data`). A stale or truncated store fails
  the run (`known-traps.md`, the market_data cache never self-heals), and the
  store is not refetched mid-study.
- **Preflight:** the run fails if `CLAMP_STOP_TO_HARD_CAP`,
  `MIN_STOP_DISTANCE_PCT` or `MAX_STOP_LOSS_PCT` in the local
  `swingbot.config` differ from production `.env`. Production is read through
  `scripts/ops/ssh-hetzner.sh`, read-only, and values are compared without
  being printed.
- **Provenance:** `run_backtest_range.py:_write_provenance` today records the
  store snapshot only (`training_data.write_provenance`: data source, feed,
  adjustment, manifest hash, integrity sha). The plan adds a run sidecar beside
  the `--trades-jsonl` output (`<path>.run.json`) holding git HEAD, window,
  universe (watchlist and membership as-of), the command line and the three
  stop settings. The results doc quotes both files.
- **Checkpointing (named plan task, not conditional):** today
  `run_backtest_range.py` keeps rows in memory and writes them once at the end
  (lines 281-285); its `.progress` file holds a percent only, and the
  `on_ticker_done(done, total)` callback carries no ticker or rows. The plan
  adds a per-ticker completion hook carrying the ticker and its rows, appends
  each finished ticker's rows to the `--trades-jsonl` output plus a done-list,
  and skips finished tickers on restart (CLAUDE.md, long runs must
  checkpoint). After a restart, the printed pooled table is computed from the
  persisted rows, so it matches an uninterrupted run. The run goes to
  `backtest-runner`.
- **Live:** closed production trades from the local replica, after
  `/replicate-prod-db`.

## Code

- `scripts/backtest/run_backtest_range.py`: per-ticker row persistence and
  skip-on-restart for `--trades-jsonl`; output unchanged for a run that is
  never interrupted.
- `swingbot/core/analytics/expectancy_attribution.py`:
  - `live_row`, `_train_row` and `ROW_KEYS` are **unchanged** (tests pin
    `tuple(row) == ROW_KEYS`, and the default report must stay byte-identical).
    New `stop_width_row(base_row, source)` returns a separate dict: the base
    row's fields plus `stop_atr`, `atr_pct`, `stop_clamped`, and, for live
    rows only, `opened_at`, `closed_at` and `strategy`;
  - new `frozen_edges(rows, key) -> list[float]`;
  - new `edge_label(value, edges) -> str`;
  - new `stop_width_groups(train_rows, live_rows)` returning both populations
    bucketed on TRAIN edges;
  - new `stop_width_verdict(train_groups, *, seed) -> dict` implementing
    clauses 1–6 and the three study verdicts, with its own BH family.
- `scripts/reports/expectancy_attribution.py`: a `--study stop-width` flag
  writing `data/reports/stop-width-attribution.json` and printing the
  Markdown that becomes
  `docs/superpowers/results/2026-11-12-v226-stop-width-attribution.md`.
  Without the flag the script and its output are unchanged. The v146 verdict
  of record is never recomputed or overwritten.
- Every new or changed function stays below cyclomatic complexity 15.

## Tests

In the suites that already hold the attribution and backtest-script tests
(`tests/suites.toml`):

- `frozen_edges` is outcome-blind: shuffling `r` leaves the edges identical;
- duplicate values produce merged edges and no empty bucket;
- a value on an edge goes to the upper bucket;
- live rows use the TRAIN edges even when live quartiles differ;
- `entry_context` absent, `stop_atr` `None`, a string, `0` or negative gives
  `unknown`, and unknown rows are counted, never bucketed;
- verdict boundaries: Δ −0.10 passes and −0.099 fails; upper bound exactly 0
  fails; bucket ExpR exactly 0 fails clause 3; 3 of 4 years passes and 2 of 4
  fails; an empty year counts against; N = 299 is underpowered and 300 can
  pass; fewer than two powered buckets give study `UNDERPOWERED`;
- the BH family size equals this study's bucket count (≤ 4), never v146's,
  pinned by a test;
- removal arithmetic: pooled ExpR without the bucket equals rest ExpR, and
  ΔTotal R equals minus the bucket's summed R;
- `stop_clamped` `None` rows leave the clamped-share denominator;
- the default report (no `--study`) is byte-identical to before (regression
  pin on a fixture), and `--study stop-width` writes only its own file;
- replay checkpointing: an interrupted run restarted with the same arguments
  skips finished tickers and yields the same rows and the same printed table
  as an uninterrupted run; the run sidecar carries its six fields;
- `entry_context["stop_atr"]` is unchanged when every bar after the signal is
  altered (truncation test);
- `ROW_KEYS` and the `tuple(row) == ROW_KEYS` pins are unchanged.

## Out of scope

Any change to stops, the clamp, `MIN_STOP_DISTANCE_PCT`, sizing, alerts or
admission; the veto itself; re-running v139 or v191; a regime gate; a re-entry
cooldown; widening the TRAIN row contract.

## Open questions

None for this spec.

## Appendix: the 2026-11-12 live queries

1. Recent book: `journal_entries` with `closed_at > now() - 14 days`,
   grouped by `outcome` and by `doc->>'direction'`, `avg((doc->>'r_realized')::numeric)`,
   `avg((doc->>'holding_days')::numeric)`.
2. Re-entry after a loss: for each closed trade with `r_realized`, the latest
   same-ticker, same-direction `loss` with `closed_at <= opened_at`, bucketed
   by the gap (< 1 d, 1–3 d, 3–7 d, 7–14 d, ≥ 14 d, never).
3. Stop width: per opening day since 2026-09-25, min / median / max of
   `abs(entry - stop_loss) / entry * 100` on `trades`.

## Panel review

- quant-researcher: BLOCKING — regime and re-entry figures had no N, window or source -- applied (N, windows and sources in the § Why table; queries in § Appendix).
- quant-researcher: ADVISORY — `stop_atr` and `atr_pct` near-collinear under the clamp, so 8 looks are about 4 counted twice -- applied (one grouping; `atr_pct` disclosed with rho and overlap; volatility wording rule at |rho| ≥ 0.8).
- quant-researcher: ADVISORY — a volatility veto is not screen-exempt -- applied (the exemption option is removed; `SCREEN-AVOID-PASS` required).
- quant-researcher: ADVISORY — no clause requiring bucket ExpR < 0; no Total R -- applied (clause 3; removal arithmetic printed).
- quant-researcher: ADVISORY — descriptive only, ignores replacement trades -- applied (§ Why paragraph; the veto spec must run a paired replay).
- quant-researcher: ADVISORY — an all-underpowered result would close the question -- applied (study `UNDERPOWERED` verdict that does not close; expected N stated).
- quant-researcher: ADVISORY — no year-consistency clause -- applied (clause 4, 3 of 4 years; weaker-than-screen bar stated).
- quant-researcher: ADVISORY — no direction, horizon or family mix -- applied (mix disclosures, Δ within direction).
- quant-researcher: ADVISORY — BH family could widen through `assign_qvalues` -- applied (own family, pinned by test).
- quant-researcher: ADVISORY — preflight and checkpointing belong to quant-engineer -- applied (handled in quant-engineer's findings).
- quant-engineer: BLOCKING — the TRAIN same-day-loss share is not computable (`ROW_KEYS` has only `signal_date`) -- applied (live only; row contract not widened).
- quant-engineer: BLOCKING — checkpointing was hedged, and the script does not persist rows -- applied (named plan task with a restart test).
- quant-engineer: ADVISORY — `stop_atr` is measured from the signal close; point-in-time check -- applied (definition stated; truncation test cited or added).
- quant-engineer: ADVISORY — `stop_clamped` is identity-based and reads config at run time; `None` rows -- applied (lower-bound wording; `None` excluded and counted).
- quant-engineer: ADVISORY — config snapshot source not named; universe and command not recorded -- applied (`_write_provenance` named with its fields).
- quant-engineer: ADVISORY — data source not named -- applied (v162 training-data store; stale store fails; no refetch).
- quant-engineer: ADVISORY — absent `entry_context` test; TRAIN unknown count -- applied (test and count).
- quant-engineer: ADVISORY — quantile method and coinciding edges undefined -- applied (`numpy.quantile` linear; merged edges; tests).
- plan-briefer (post-panel code check): `_write_provenance` lacks HEAD/window/universe/command/config; no TRAIN strategy field; no stop_atr truncation test; `on_ticker_done` carries no rows; live row lacks timestamps and `ROW_KEYS` is pinned -- applied (run sidecar; family share live only; truncation test; per-ticker hook; separate `stop_width_row`, `ROW_KEYS` unchanged).
