# v172 — Equity candlestick chart: see the account move like a market

**Version:** ui 1.26.0 · bot 2.7.0 (at writing)
**Bump:** ui minor — the Dashboard's equity sparkline becomes a candlestick chart with timeframes, a basis toggle and an OHLC readout; bot minor — the trade monitor starts recording equity samples into a new table, and a new API endpoint serves candles.
**Edge:** none (integrity) — a way to read the account. It changes no signal, gate, stop, size or badge.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, quant-engineer
**Status:** spec written 2026-10-17 from a brainstorm with the partner (basis, history source, placement, timeframes and approach approved in chat); revised the same day after the panel (see `## Panel review`).

## Why

The Trading performance panel shows equity as a 30-point sparkline
(`frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts`), fed by
`_equity_30d()` in `swingbot/admin/api_v1/dashboard.py`. That series has two
limits the partner wants gone:

1. **It moves only when a trade closes.** `equity_curve` in
   `swingbot/core/analytics/metrics.py` adds one point per closed trade with
   `realized_pnl_amount`, and open positions do not count. A day full of open
   risk and no closes looks flat.
2. **It has no time axis or detail.** Thirty points are thirty closes, not
   thirty days, and nothing can be hovered.

The partner wants to read their money the way they read a ticker: candles
per hour, 4 hours, day or week, and a hover that gives the open, high, low
and close.

## Decisions taken in the brainstorm

| Question | Answer |
|---|---|
| What a candle measures | **Both, with a toggle.** Mark-to-market (realized balance + open positions' unrealized P&L) by default; realized-only ("Closed trades only") as the alternative. |
| Where history comes from | **Backfill + record.** A one-off backfill rebuilds daily mark-to-market candles from cached daily bars and the trade log; from deploy onward the trade monitor records exact samples. |
| Placement | **Replace the sparkline in place**, inside the Trading performance panel. |
| Timeframes | **1H · 4H · 1D · 1W**, 1D the default. |
| Architecture | **Approach A:** raw samples in Postgres, candles built in the API on request. |

Rejected: pre-built hourly candles (approach B), since an update bug would
corrupt history with no raw rows to rebuild from. Rejected: building candles
in the browser (approach C), since the payload grows without limit and the
basis logic would be duplicated in TypeScript.

## Design

### 0. One equity definition, in `swingbot/core`

A new module `swingbot/core/tracking/equity.py` owns the definition both
bases and both writers (live recorder, backfill) use. Nothing in
`swingbot/commands` or `swingbot/core` imports `swingbot.admin` today, and
this keeps it that way: the admin side imports the core helper.

- **Which trades:** the same ledger `refresh_snapshot` feeds `equity_curve`
  (`split_by_ledger`, `swingbot/core/analytics/snapshots.py`), for opens and
  closes alike. A weak-ledger open is never summed against a strong-ledger
  realized balance.
- **Realized balance at time `t`:** starting balance plus every realized leg
  closed at or before `t`, with legs taken from `expand_realized_legs`
  (`swingbot/core/tracking/performance.py:484`). A PARTIAL trade's banked TP1
  leg therefore counts as realized at its own time, so mark-to-market equity
  does not dip at TP1 and recover at the runner's close.
- **Unrealized P&L of one open position at price `p`:** the formula now in
  `unrealized_pnl_amount` (`swingbot/admin/dashboard.py`), moved here
  unchanged. It already leaves out a banked TP1 leg, which the realized side
  now counts. `swingbot/admin/dashboard.py` and `_attach_unrealized_pnl`
  (`swingbot/admin/api_v1/trades.py`) re-import it, so the chart and the
  Trades page cannot disagree.
- **Money:** `Decimal` throughout; rounded to 2 dp once, in the repository
  write. The API emits those rounded values as JSON numbers.

### 1. Storage: `equity_samples`

Alembic revision `v172_001_equity_samples` in
`swingbot/core/db/migrations/versions/`, `down_revision` = the head at the
time the plan task runs (`schema-evolution.md` § Revision ids). Repository
module `swingbot/core/db/repositories/equity_samples.py`. The table is
additive: rollback is the revision's `downgrade` (drop table), and leaving it
in place after a code rollback is also safe.

| Column | Type | Meaning |
|---|---|---|
| `id` | bigserial PK | |
| `at` | timestamptz | when the sample applies (UTC) |
| `realized_balance` | numeric(14,2) | § 0 realized balance at `at` |
| `unrealized_pnl` | numeric(14,2) | Σ § 0 unrealized P&L of positions open at `at` |
| `equity` | numeric(14,2) | `realized_balance + unrealized_pnl` |
| `open_n` | integer | open positions counted |
| `skipped_n` | integer | open positions left out (no size, no price, or a corporate action the backfill cannot rebase) |
| `source` | text, `live` or `backfill` | a backfill row is rebuilt from daily bars, not measured |
| `kind` | text, `point`, `day_high` or `day_low` | live rows are always `point` |
| `backfill_run` | text, nullable | backfill only: run id + cache as-of date, so a row names what it was built from |

Indexes: unique `(at, source, kind)` (the backfill upserts through it), and
`(source, at)` for the API's range reads.

**Size and owner.** The recorder writes at most one row per 5 minutes while
the trade monitor runs: about 170 rows a session day, about 45k a year,
plus four rows per backfilled day. No retention policy is needed at that
size; this spec's plan owns the table, and a later spec that retires the
chart removes it.

### 2. Recording (bot)

The scan loop never prices open trades. `trade_monitor`
(`swingbot/commands/scanning/loops.py:591`, every 60s) does, through
`_live_price_batch`. The recorder hooks in there:

- **After the tick has applied any closes**, so a trade that closes this
  tick is realized in this sample, never also unrealized.
- **Throttled to one sample per 5 minutes** (the first tick at least 5
  minutes after the last written sample). The prices are the ones this tick
  already fetched: recording makes no market-data call of its own.
- A position with no price this tick, or no position size, is left out of
  `unrealized_pnl` and counted in `skipped_n`. It is never priced at 0.
- **Never breaks the monitor.** Every failure is caught, logged once per
  process per error type, and the sample is skipped. A missed sample is a
  gap, never an invented value.

Samples exist only while the monitor runs, so intraday candles cover only
the hours it prices trades.

### 3. Backfill (one-off script)

`scripts/data/backfill_equity_samples.py`. Dry-run by default, `--apply` to
write.

**Bars:** daily bars from `swingbot/core/marketdata/backtest_cache.py`, the
backtest CSV cache, and never `market_data/` (`known-traps.md` § The
market_data cache never self-heals). Those bars are adjusted, and entry
prices are raw fills. Each bar is rebased to the raw basis with
`swingbot/core/marketdata/adjustments.py` before any P&L is computed. A
position whose span contains a corporate action that cannot be rebased is
left out of every day it spans and counted in `skipped_n`. It is never
priced on the adjusted basis.

**Per trading day `D`**, from the earliest `opened_at` to the day before
the first `live` sample, with session open = 09:30 and close = 16:00
America/New_York converted to UTC:

- For each position open at any point on `D`, with a position size, the
  favourable and adverse extremes are clamped to the time it was held:
  - **entry day:** the range runs from the entry price to the bar's close.
    The bar open and any high or low that may predate the entry are not
    used.
  - **exit day:** the position contributes no unrealized amount at the
    close (its leg is realized). Its intraday extremes run from the bar
    open to the exit price only, never the bar's full high or low.
  - **other days:** bar open, high, low and close.
- Four rows per day, all `source=backfill`:
  - `point` at session open: `realized(D−1) + Σ unrealized at the open`
    (positions entered on `D` contribute 0).
  - `day_high` at session open: `realized(D) + Σ favourable extremes`
  - `day_low` at session open: `realized(D) + Σ adverse extremes`
  - `point` at session close: `realized(D) + Σ unrealized at the close`
- **The high and low are outer bounds, not measured values.** Positions do
  not all peak at the same moment, so the true range sits inside them.
  Every candle built from these rows is `approx` and is drawn differently
  (§ 5).

**Reproducibility.** Each run gets an id (UTC timestamp) and records the
cache's as-of date in `backfill_run`. A re-run without `--replace` writes
only days with no backfill rows. With `--replace`, it deletes every backfill
row and rewrites them in one transaction, so a corrected cache always
replaces stale values. The dry run prints the run id, cache as-of date,
days covered and each skipped position with its reason.

**Coverage gate.** Before `--apply`, the script checks that the cache holds
a bar for every traded ticker on every day it was held. It refuses to write
on any gap unless `--allow-gaps` is passed, in which case gaps are counted
in `skipped_n`.

**`--recompute-realized`.** An admin edit or clear of trades changes the
realized walk after samples were written. This flag rewrites
`realized_balance` and `equity` on `live` rows from the current trade log,
keeping the measured `unrealized_pnl`, so the two bases agree again.

**VM run** (after the release deploys):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py"          # dry run, read the coverage report
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py --apply"
```

The `backtest_cache` mount must be current on the VM first. If the
coverage report shows gaps, refresh the cache before `--apply` rather than
passing `--allow-gaps`.

### 4. API: `GET /api/v1/equity/candles`

Auth as every `api_v1` route. Query parameters:

- `tf`: `1H` | `4H` | `1D` | `1W`, default `1D`. Anything else returns 400.
- `basis`: `mtm` | `realized`, default `mtm`.
- `limit`: number of most recent candles, default 120, maximum 500.

Response:

```json
{
  "tf": "1D", "basis": "mtm", "currency": "EUR",
  "candles": [
    {"t": "2026-10-16", "o": 10120.5, "h": 10210.0, "l": 10090.2, "c": 10180.4,
     "change": 59.9, "change_pct": 0.59, "samples": 78, "skipped": 0, "approx": false}
  ],
  "recording_since": "2026-10-20T13:35:00Z",
  "as_of": "2026-10-21T14:35:00Z"
}
```

`currency` is the account currency the dashboard already shows. The plan
names its config source and does not hard-code it.

Bucketing rules:

- **Bucket timezone:** America/New_York wall-clock. 1H buckets are clock
  hours. 4H buckets start at 00:00, 04:00, 08:00, 12:00, 16:00 and 20:00 NY
  time, so on the two DST change days a 4H bucket is 3 or 5 real hours
  long. 1D is the NY calendar day, and 1W starts on Monday. `t` is the
  bucket start: an ISO date for 1D and 1W, an ISO datetime with offset for
  1H and 4H.
- **mtm:** `o` is the earliest `point` row's `equity` in the bucket, `c` the
  latest `point` row's. `h`/`l` are the max/min over every row, including
  `day_high`/`day_low`. `skipped` is the bucket's max `skipped_n`. `approx`
  is true when any row is `source=backfill`.
- **realized:** built from § 0's realized legs, not the samples. Each leg is
  a step. `o` is the balance before the bucket's first leg, `h`/`l` the
  extremes across the steps, `c` the balance after the last. A bucket with
  no leg is left out. `approx` is always false.
- **Empty buckets are omitted.** Weekends and hours with no samples produce
  no candle.
- `change` and `change_pct` are measured against the previous candle's `c`
  (the first candle uses its own `o`).
- 1H and 4H with `basis=mtm` never read backfill rows. They begin at
  `recording_since`.

`_equity_30d()` and the `equity_30d` dashboard field stay as they are this
release. Other callers (`test_api_v1_dashboard.py`, the header change
figure) still read them. Retiring them is a separate change.

### 5. UI: the candle chart

A new `sb-equity-candles` component in
`frontend/src/app/workspaces/dashboard/panels/`, rendered by
`sb-portfolio-value` where `sb-sparkline` sits today. The large balance
figure and the "today" change line above it stay.

- **Library:** `lightweight-charts` (already a dependency), a candlestick
  series themed through `ui/chart/chart-theme.ts` so it matches the trade
  chart in light and dark mode. Up and down colours are `--pos` / `--neg`.
- **Approx candles look different, not only on hover.** A backfilled candle
  is drawn hollow: transparent body, coloured border, wick in
  `--text-faint`. Whenever an approx candle is in view, a persistent caption
  under the chart reads "Before <recording_since date>: rebuilt from daily
  bars — ranges are outer bounds". A vertical marker at `recording_since`
  labels the seam "Recording started".
- **Controls** (one row above the chart, wrapping on narrow widths):
  timeframe chips `1H · 4H · 1D · 1W` (default 1D) and a segmented toggle
  `Open + closed | Closed trades only` (`mtm` / `realized`). Both are kept
  per viewer in local preferences, wrapped so a blocked storage falls back
  to the defaults.
- **Readout:** on crosshair move (hover on desktop, tap or drag on touch),
  a line above the chart shows
  `date/time · O · H · L · C · ±€ · ±% vs prev close`, then the basis name,
  then `approx` on a backfilled candle and `N positions not counted` when
  `skipped > 0`. With no crosshair it shows the latest candle. The `±%`
  tooltip says it is the change from the previous candle's close, not a
  return on capital.
- **Account label:** a muted line under the chart: "Paper account · before
  tax", plus "after modelled costs" or "before costs". The plan reads which
  one from whether `realized_pnl_amount` includes v157's slippage and
  commission (`swingbot/core/edge/frictions.py`), and the label must state
  the fact.
- **No intraday excitement.** 1D is the default. Candles never flash or
  animate on update, and no notification hangs off intraday moves, because
  this is a swing system.
- **States:** loading uses the panel's existing skeleton. An error uses
  `sb-async`'s retry. An empty series (e.g. 1H before any live sample)
  shows "No hourly samples yet — recording started <date>" and never an
  empty axis.
- **Refresh:** refetches on the same `scan` event the tape store listens to,
  so the newest candle grows during the session.

#### Three devices (`docs/claude/ui-design.md`)

| Width | Chart height | Controls |
|---|---|---|
| Phone (< 640px) | 160px | chips and toggle wrap to two lines; each target ≥ 44px tall; readout and caption wrap under the chart |
| Tablet (640–1023px) | 200px | one row |
| Desktop (≥ 1024px) | 200px | one row; readout inline at the right of the controls |

No horizontal page scroll at any width. The chart fills its panel's width,
and `lightweight-charts`' time scale handles candle density.

## Error handling

| Failure | Behaviour |
|---|---|
| Sample write fails in the monitor | caught, logged, sample skipped; monitor unaffected |
| Position unpriced or unsized | left out of `unrealized_pnl`, counted in `skipped_n` |
| Backfill bar missing | `--apply` refuses; with `--allow-gaps`, left out that day and counted |
| Corporate action not rebasable | position left out of its whole span, counted |
| Bad `tf` / `basis` / `limit` | 400 with the allowed values |
| Table empty (fresh install) | `candles: []`; the UI shows the empty state |

## Testing

- **Equity definition (§ 0):** a PARTIAL trade's banked TP1 leg is realized
  at its time and absent from unrealized; weak-ledger trades are excluded on
  both sides; `Decimal` sums match to the cent.
- **Bucketing (pure function):** samples → candles for each `tf`, including
  23:59 vs 00:01 NY, both 2026 DST change days for 4H, the Monday week
  start, omitted empty buckets, `o`/`c` from `point` rows only while `h`/`l`
  include `day_high`/`day_low`, `approx` and `skipped` propagation, and
  `change` against the previous candle.
- **Realized basis:** a fixture with several legs in one day (including a
  TP1 leg) → the expected step OHLC; a day with no leg → no candle.
- **Recording:** a monitor tick with one priced, one unpriced and one
  unsized position writes one row with `skipped_n=2`. A trade closing in the
  same tick is realized, not unrealized. Two ticks under 5 minutes apart
  write one row. An exception inside recording does not propagate out of
  the monitor.
- **Parity:** the recorded `unrealized_pnl` for a fixture position equals
  `_attach_unrealized_pnl`'s amount for it, and the sample's
  `realized_balance` equals the realized walk at the same time.
- **Backfill:** a two-position fixture over three days with an entry day
  and an exit day checks the clamping and the four rows per day. A split
  inside a span is rebased, or the position is skipped when it cannot be. A
  re-run writes nothing new, `--replace` rewrites every row with the new
  `backfill_run`, the coverage gate refuses a gap, and
  `--recompute-realized` updates only the realized columns.
- **API:** shape, defaults, 400s, `limit` cap, auth required,
  `recording_since`.
- **Frontend:** `sb-equity-candles` renders the readout from a crosshair
  event, draws approx candles hollow with the caption and seam marker,
  shows the skipped note and the empty state, and keeps the chosen
  timeframe and basis across reloads. Checked at 390px, 768px and 1280px.
- New `tests/` files join an existing suite in `tests/suites.toml`.

## Out of scope

- Retiring `equity_30d` and the sparkline component (other callers remain).
- A volume-like sub-pane (P&L per candle) and drawing tools.
- Drawdown from peak in currency (a follow-up; the panel rated it the most
  useful next readout).
- Intraday backfill. 1H and 4H history starts at deploy, by design.
- Showing equity candles on the Analytics page's equity curve.

## Success criteria

1. On the Dashboard, the Trading performance panel shows daily equity
   candles back to the first trade, with a working 1H/4H/1D/1W switch and
   basis toggle.
2. Hovering or tapping a candle shows its O, H, L, C and change. Backfilled
   candles are drawn hollow, with the outer-bound caption visible.
3. During a session, the current 1H and 1D candle update every few minutes.
4. A monitor tick in which recording throws still completes.
5. Mark-to-market equity does not dip at a TP1 fill.
6. Readable, with no horizontal scroll, at phone, tablet and desktop widths.

## Panel review

Run 2026-10-17 on commit 9ae7e514 (staff-engineer, financial-advisor,
quant-engineer). 3 BLOCKING, 22 ADVISORY.

**BLOCKING**

- financial-advisor: backfilled wicks sum best and worst cases, so they overstate the range, and they were flagged only on hover -- applied: approx candles are drawn hollow with a persistent caption and a seam marker (§ 5).
- quant-engineer: the backfill cache was unpinned and adjusted bars were compared with raw entries -- applied: `backtest_cache.py` is pinned, bars are rebased with `adjustments.py`, and an unrebasable span is skipped (§ 3).
- quant-engineer: the backfill was not reproducible, and its unique index froze stale values -- applied: `backfill_run` column, `--replace` in one transaction, and the dry run prints the cache as-of date (§ 1, § 3).

**ADVISORY**

- staff-engineer: the banked TP1 leg was counted in neither basis -- applied: `expand_realized_legs` is used in § 0, with a test and a success criterion.
- staff-engineer: the scan loop never prices open trades -- applied: the recorder hooks into `trade_monitor`, throttled to 5 minutes (§ 2).
- staff-engineer: the shared helper had no home and risked a `core → admin` import -- applied: `swingbot/core/tracking/equity.py` (§ 0).
- staff-engineer: the ledger for open positions was unstated -- applied: the same `split_by_ledger` book for both sides (§ 0).
- staff-engineer: stored realized values drift after an admin edit of trades -- applied: `--recompute-realized` (§ 3).
- staff-engineer: no revision id, repository module or rollback -- applied (§ 1).
- staff-engineer: no VM run plan or cache coverage check -- applied: exact commands and a coverage gate (§ 3).
- staff-engineer: no growth, retention, owner or index plan -- applied (§ 1).
- staff-engineer: adjusted vs unadjusted bars -- applied, through quant-engineer's blocking finding.
- financial-advisor: a fake jump at the backfill/live seam -- applied: a seam marker; the gap itself is real, as below.
- financial-advisor: hard-coded currency, no paper, tax or cost labelling -- applied: currency comes from config, and an account label states paper, pre-tax and the cost basis (§ 4, § 5).
- financial-advisor: the change % basis was unstated -- applied: "vs prev close" in the readout, and the tooltip says it is not a return on capital.
- financial-advisor: intraday candles invite over-trading -- applied: 1D default, no flashing, no intraday notifications.
- financial-advisor: the realized basis can read as safety -- applied: the toggle is labelled "Closed trades only" and the readout names the basis.
- financial-advisor: skipped positions shown only as a whole-series max -- applied: `skipped` per candle, shown in the readout.
- financial-advisor: drawdown from peak would be the most useful readout -- rejected for this spec: listed as a follow-up in Out of scope.
- quant-engineer: entry-day and exit-day extremes can fall outside the holding window -- applied: clamping rules (§ 3).
- quant-engineer: the open at the bar open creates artificial gaps against the previous close -- rejected: an overnight gap in held positions is real and is drawn the way market candles draw it. `change` is measured from the previous close, so the readout shows it.
- quant-engineer: `numeric` vs floats, and float drift -- applied: `Decimal`, rounded once at the repository write (§ 0).
- quant-engineer: DST behaviour of 4H buckets and session-time conversion -- applied: stated, with both DST days tested (§ 3, § 4).
- quant-engineer: the sample's ordering against closes in the same tick -- applied: the sample is taken after closes, with a parity test (§ 2).
- quant-engineer: `day_high`/`day_low` timestamps and `o`/`c` ordering -- applied: these rows sit at session open, and `o`/`c` come from `point` rows only (§ 3, § 4).
