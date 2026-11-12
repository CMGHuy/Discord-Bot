# v226 — Stop-width attribution: does a stop that is tight in ATR terms cost expectancy?

**Version:** ui 1.41.0 · bot 2.18.4
**Bump:** none (a measurement: a report flag and two attribution groupings; nothing the bot posts, trades or shows changes)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer

## Why

On 2026-11-12 the partner asked why production shows so many losing trades.
A read-only look at the live book found no defect:

- last 14 days: N = 223 closed, about +0.04R pooled, loss rate about 55%,
  and about 47% of trades stopped out the same day they opened;
- since 2026-10-01 every plan's stop sits 1.75–2.00% from entry (the v115
  clamp `builders._clamp_stop_to_hard_cap` plus `MIN_STOP_DISTANCE_PCT`
  1.75), about 0.35 × ATR14 on a watchlist whose ATR14 runs near 5% of price;
- trade volume rose from about 30 to 77–105 per week without a new source:
  the existing Fib, FVG and Trendline families fired more on a volatile tape,
  and fast stop-outs free slots for the next entry.

The obvious fixes are already measured and closed:

| idea | record | outcome |
|---|---|---|
| structural stop at the real level, dollar-risk sizing | v139 arm S | **NO_ELIGIBLE_CELL**: paired ΔExpR −0.026 to −0.033R, CI below zero; win rate up ≤ 1.3pp, planned RR 2.5 → 2.0 |
| no plan beyond a ceiling | v139 arm D | REFUSED at Stage 0 |
| ATR-band stops, keep or re-choose target | v191 arms K/R | UNDERPOWERED at Stage 0 (81% of band plans newly admitted, no paired twin) |
| regime gate | v17 P2a, v146 | 0 of 44 cells; bull_volatile only about 0.04R below bull_quiet on TRAIN |
| re-entry cooldown after a stop-out | live book, 2026-11-12 | re-entries within a day ≈ first entries (about −0.06R both) |

Widening the stop has been tried and costs expectancy. What has **never been
measured** is the other half of the same question: whether plans whose stop is
very tight *relative to the ticker's volatility* are a population that loses.
If they are, the answer is to skip those setups (a veto), not to widen the
stop. Neither v146 nor any replay split ExpR by stop distance in ATR (the v191
spec says so in its § Why).

## What changes

Two attribution groupings and one pre-registered verdict, added to the v146
attribution study and written to a report of their own. No stop, clamp,
filter, alert or sizing rule changes.

### The two groupings

- **`stop_atr`** — stop distance in ATR14 units, read from the row's
  `entry_context["stop_atr"]` (`swingbot/core/edge/context.py` `FEATURE_KEYS`).
- **`atr_pct`** — ATR14 as a percent of price, derived as
  `entry_context["stop_pct"] / entry_context["stop_atr"]`; no new feature
  is computed.

A row with either input missing, non-numeric, or `stop_atr <= 0` carries
`None` and the label `unknown`.

### Frozen bucket edges

Each grouping is cut at the **TRAIN quartiles of the feature values**, computed
from the TRAIN rows before any `r` is read (the function takes no `r` and is
tested to ignore it). Live rows are bucketed with the **TRAIN** edges, never
their own. Labels: `Q1 (<a)`, `Q2 (a–b)`, `Q3 (b–c)`, `Q4 (≥c)`, values to two
decimals. The live cut points seen on 2026-11-12 (0.35 / 0.5 / 0.75) are
**not** used: they were chosen after the outcomes were visible.

### The pre-registered verdict (TRAIN only, computed once)

For each of the 8 buckets (2 groupings × 4 quartiles; `unknown` is disclosed,
never a look) the study compares the bucket against **every other TRAIN row
with a known value in the same grouping**, using the existing week-clustered
bootstrap (`expectancy_attribution._look`, 10,000 resamples, seed 42):

A bucket is a **veto candidate** when all hold:

1. bucket ExpR − rest ExpR ≤ −0.10R (exactly −0.10 passes);
2. the upper 95% bound of that difference is < 0 (exactly 0 fails);
3. bucket N ≥ 300 (below that the bucket is `UNDERPOWERED` and cannot pass);
4. it survives Benjamini–Hochberg at q < 0.10 over the 8 looks.

The study verdict is `VETO-CANDIDATE` naming every passing bucket, or
`NO CANDIDATE`. The live book is printed beside TRAIN for each bucket, same
edges, and **never gates** (live N is small and correlated). VALIDATION is
never read.

What each verdict buys:

- **`VETO-CANDIDATE`** licenses a separate veto spec; the setup is skipped,
  its stop is never widened. That spec must settle how it is screened: the
  Stage −2 screen races its own 1.5 × ATR stop, so it cannot see the bot's
  stop geometry. Whether to grant an exemption or build a bot-replay screen
  is the partner's call at that point, not this spec's.
- **`NO CANDIDATE`** closes "tight stops on volatile names" as measured, and
  is recorded in `backtest-methodology.md` § Closed pre-registrations.

### Disclosures (printed, never gating)

Per bucket, both populations: N, win rate, ExpR net and gross, the share of
rows whose stop was clamped (`entry_context["stop_clamped"]`), the share of
losses closed on the entry day, median planned RR. Per grouping: count of
`unknown` rows. The TRAIN run's config snapshot of `CLAMP_STOP_TO_HARD_CAP`,
`MIN_STOP_DISTANCE_PCT` and `MAX_STOP_LOSS_PCT`.

## Data

- **TRAIN:** a fresh confluence replay over the v146 window
  (2020-01-06..2023-12-29 signal date) with
  `scripts/backtest/run_backtest_range.py --scenarios --train --trades-jsonl <path>`
  under today's live config, so every stop passes the v115 clamp as it does in
  production. A preflight fails the run if the three stop settings differ from
  production's `.env` (read-only check through `scripts/ops/ssh-hetzner.sh`).
  The run goes to `backtest-runner`. If the script does not already persist
  each finished ticker and skip it on restart, the plan adds that first
  (CLAUDE.md, long runs must checkpoint).
- **Live:** closed production trades from the local replica, after
  `/replicate-prod-db`.

## Code

- `swingbot/core/analytics/expectancy_attribution.py`:
  - `live_row` and `_train_row` gain `stop_atr` and `atr_pct`;
  - new `frozen_edges(rows, key) -> list[float]` (quartile cut points, reads
    only `key`);
  - new `edge_label(value, edges) -> str`;
  - new `stop_width_groups(train_rows, live_rows)` returning both
    populations bucketed on TRAIN edges;
  - new `stop_width_verdict(train_groups, *, seed) -> dict` implementing
    clauses 1–4.
- `scripts/reports/expectancy_attribution.py`: a `--study stop-width` flag
  writing `data/reports/stop-width-attribution.json` and printing the
  Markdown that becomes
  `docs/superpowers/results/2026-11-12-v226-stop-width-attribution.md`.
  Without the flag the script and its output are unchanged; the v146 verdict
  of record is never recomputed or overwritten.
- Every new or changed function stays below cyclomatic complexity 15.

## Tests

In the suite that already holds the attribution tests (`tests/suites.toml`):

- `frozen_edges` is outcome-blind: shuffling `r` leaves the edges identical;
- live rows are bucketed with the TRAIN edges, even when live quartiles differ;
- `stop_atr` of `None`, a string, `0` or a negative value gives `unknown`;
  `atr_pct` follows;
- edge values fall in the upper bucket (`≥ c` is Q4);
- verdict boundaries: Δ −0.10 passes, −0.099 fails; upper bound exactly 0
  fails; N = 299 is `UNDERPOWERED`, N = 300 can pass; BH removes a bucket that
  passes clauses 1–3 only on its raw p;
- the default report (no `--study`) is byte-identical to before (regression
  pin on a fixture);
- `--study stop-width` writes only its own file.

## Out of scope

Any change to stops, the clamp, `MIN_STOP_DISTANCE_PCT`, sizing, alerts or
admission; the veto itself; re-running v139 or v191; a regime gate; a re-entry
cooldown.

## Open questions

None for this spec. The screening route for a veto is deferred to the veto
spec, and is only needed on `VETO-CANDIDATE`.
