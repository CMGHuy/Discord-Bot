# v172 — Equity candlestick chart: see the account move like a market

**Version:** ui 1.26.0 · bot 2.7.0 (at writing)
**Bump:** ui minor — the Dashboard's equity sparkline becomes a candlestick chart with timeframes, a basis toggle and an OHLC readout; bot minor — the scan loop starts recording an equity sample every scan into a new table, and a new API endpoint serves candles.
**Edge:** none (integrity) — a way to read the account. It changes no signal, gate, stop, size or badge.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, quant-engineer
**Status:** spec written 2026-10-17 from a brainstorm with the partner (basis, history source, placement, timeframes and approach approved in chat).

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
| What a candle measures | **Both, with a toggle.** Mark-to-market (realized balance + open positions' unrealized P&L) by default; realized-only as the alternative. |
| Where history comes from | **Backfill + record.** A one-off backfill rebuilds daily mark-to-market candles from cached daily bars and the trade log; from deploy onward every scan records an exact sample. |
| Placement | **Replace the sparkline in place**, inside the Trading performance panel. |
| Timeframes | **1H · 4H · 1D · 1W**, 1D the default. |
| Architecture | **Approach A:** raw samples in Postgres, candles built in the API on request. |

Rejected: pre-built hourly candles (approach B), since an update bug would
corrupt history with no raw rows to rebuild from. Rejected: building candles
in the browser (approach C), since the payload grows without limit and the
basis logic would be duplicated in TypeScript.

## Design

### 1. Storage: `equity_samples`

A new Postgres table, added by an Alembic revision following
`docs/claude/schema-evolution.md`:

| Column | Type | Meaning |
|---|---|---|
| `id` | bigserial PK | |
| `at` | timestamptz, indexed | when the sample was taken (UTC) |
| `realized_balance` | numeric | starting balance + Σ realized P&L of trades closed at or before `at` |
| `unrealized_pnl` | numeric | Σ unrealized P&L amount of positions open at `at` |
| `equity` | numeric | `realized_balance + unrealized_pnl` |
| `open_n` | integer | open positions counted |
| `skipped_n` | integer | open positions left out because they have no position size |
| `source` | text, `live` or `backfill` | a backfill row is a daily bound, not a measured moment |
| `kind` | text, `point`, `day_high` or `day_low` | see § 3; live rows are always `point` |

A unique index on `(at, source, kind)` makes a re-run backfill idempotent.

### 2. Recording (bot)

After each scan in `swingbot/commands/scanning/loops.py` (the
`@tasks.loop(minutes=config.SCAN_INTERVAL_MINUTES)` loop), once open trades
have been priced, write one `live`/`point` sample:

- `unrealized_pnl` uses the same per-trade amount the Trades page shows
  (`dash.unrealized_pnl_amount`, reached through `_attach_unrealized_pnl` in
  `swingbot/admin/api_v1/trades.py`). The plan extracts one shared helper
  rather than copying the formula, so the chart and the Trades page cannot
  disagree.
- `realized_balance` comes from the same realized walk `equity_curve` uses,
  so the realized basis and the mark-to-market basis share one origin.
- **Prices are the ones the scan already fetched.** Recording makes no
  market-data call of its own.
- **Never breaks a scan.** Every failure is caught, logged once per process
  per error type, and the sample is skipped. A missed sample is a gap, never
  an invented value.
- A position with no price this scan is left out of `unrealized_pnl` and
  counted in `skipped_n`, the same treatment as an unsized one. It is never
  priced at 0.

Samples are written only while scans run (session hours), so intraday
candles exist only for session hours.

### 3. Backfill (one-off script)

`scripts/data/backfill_equity_samples.py`, run once on the VM after deploy.
Dry-run by default and `--apply` to write. Re-runs are idempotent through the
unique index.

For each trading day `D`, from the earliest `opened_at` to the day before
the first `live` sample:

- `realized(D)`: realized balance after every close dated ≤ `D`.
- For each position open at any point on `D`, with a position size, take
  its daily bar from the **backtest/market-data CSV cache** (the cache
  `known-traps.md` names; the plan pins which of the two OHLCV caches). For a
  position closed on `D`, its realized P&L is already in `realized(D)` and it
  contributes no unrealized amount at the close.
- Write four rows per day, all `source=backfill`:
  - `point` at the session open: `realized(D−1) + Σ unrealized at bar open`
  - `day_high`: `realized(D) + Σ per-position favourable extreme` (bar high
    for longs, bar low for shorts)
  - `day_low`: `realized(D) + Σ per-position adverse extreme`
  - `point` at the session close: `realized(D) + Σ unrealized at bar close`
- **The high and low are outer bounds, never measured values.** Positions
  do not all peak at the same moment, so the true intraday range sits inside
  them. The API marks every candle built from backfill rows as `approx`.
- A day where any open position has no cached bar is written with that
  position left out and counted in `skipped_n`. It is not interpolated.

Backfill writes daily rows only. 1H and 4H candles exist only from the
first `live` sample onward.

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
     "change": 59.9, "change_pct": 0.59, "samples": 96, "approx": false}
  ],
  "skipped_max": 0,
  "as_of": "2026-10-17T14:35:00Z"
}
```

Bucketing rules:

- **Bucket timezone:** America/New_York, the market's session. 1H buckets
  are clock hours. 4H buckets start at 00:00, 04:00, 08:00, 12:00, 16:00 and
  20:00 NY time. 1D is the NY calendar day. 1W starts on Monday. `t` is the
  bucket start: an ISO date for 1D and 1W, an ISO datetime for 1H and 4H.
- **mtm:** `o` is the first sample's `equity` in the bucket, `c` the last,
  `h`/`l` the max/min over every sample (including `day_high`/`day_low`
  rows). `approx` is true when any row in the bucket is `source=backfill`.
- **realized:** built from the trade log, not the samples. Each close is a
  step. `o` is the balance before the first close in the bucket, `h`/`l` the
  extremes across the steps, `c` the balance after the last. A bucket with no
  close is left out rather than drawn as a flat candle. `approx` is always
  false.
- **Empty buckets are omitted.** Weekends and out-of-session hours produce
  no candle.
- `change` and `change_pct` are measured against the previous candle's `c`
  (the first candle uses its own `o`).
- 1H and 4H with `basis=mtm` never read backfill rows. They begin at the
  first `live` sample.

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
- **Controls** (one row above the chart, wrapping on narrow widths):
  timeframe chips `1H · 4H · 1D · 1W` and a segmented `MTM | Realized`
  toggle. Both are kept per viewer in `ui/table-prefs`-style local
  preferences, wrapped so a blocked storage falls back to the defaults.
- **Readout:** on crosshair move (hover on desktop, tap or drag on touch),
  a line above the chart shows
  `date/time · O · H · L · C · ±€ · ±%`, plus a muted `approx` tag on a
  backfilled candle with tooltip "Range is an outer bound rebuilt from daily
  bars". With no crosshair it shows the latest candle.
- **States:** loading uses the panel's existing skeleton. An error uses
  `sb-async`'s retry. An empty series (e.g. 1H before any live sample) shows
  "No hourly samples yet — recording started <date>" and never an empty
  axis.
- **Skipped positions:** when `skipped_max > 0`, a muted footnote "N open
  positions without a size or price are not counted".
- **Refresh:** refetches on the same `scan` event the tape store listens to,
  so the newest candle grows during the session.

#### Three devices (`docs/claude/ui-design.md`)

| Width | Chart height | Controls |
|---|---|---|
| Phone (< 640px) | 160px | chips and toggle wrap to two lines; each target ≥ 44px tall; readout wraps under the controls |
| Tablet (640–1023px) | 200px | one row |
| Desktop (≥ 1024px) | 200px | one row; readout inline at the right of the controls |

No horizontal page scroll at any width. The chart fills its panel's width,
and `lightweight-charts`' time scale handles candle density.

## Error handling

| Failure | Behaviour |
|---|---|
| Sample write fails during a scan | caught, logged, sample skipped; scan unaffected |
| Position unpriced or unsized | left out of `unrealized_pnl`, counted in `skipped_n` |
| Backfill bar missing for a day | position left out that day, counted in `skipped_n` |
| Bad `tf` / `basis` / `limit` | 400 with the allowed values |
| Table empty (fresh install) | `candles: []`; the UI shows the empty state |

## Testing

- **Bucketing (pure function):** samples → candles for each `tf`, including
  the NY timezone edge (a sample at 23:59 vs 00:01 NY), weekly Monday start,
  omitted empty buckets, `approx` propagation, and `change` against the
  previous candle.
- **Realized basis:** a fixture trade log with several closes in one day →
  the expected step OHLC; a day with no closes → no candle.
- **Recording:** a scan with one priced, one unpriced and one unsized
  position writes one row with the right `unrealized_pnl` and
  `skipped_n=2`; an exception inside recording does not propagate out of
  the scan.
- **Parity:** the recorded `unrealized_pnl` for a fixture position equals
  what `_attach_unrealized_pnl` reports for it on the Trades page.
- **Backfill:** a two-position fixture over three days → four rows per day
  with the bound semantics above; a second run writes nothing new.
- **API:** shape, defaults, 400s, `limit` cap, auth required.
- **Frontend:** `sb-equity-candles` renders the readout from a crosshair
  event, shows the `approx` tag, shows the empty state for an empty series,
  and keeps the chosen timeframe across reloads; checked at 390px, 768px and
  1280px widths.
- New `tests/` files join an existing suite in `tests/suites.toml`.

## Out of scope

- Retiring `equity_30d` and the sparkline component (other callers remain).
- A volume-like sub-pane (P&L per candle) and drawing tools.
- Intraday backfill. 1H and 4H history starts at deploy, by design.
- Showing equity candles on the Analytics page's equity curve.

## Success criteria

1. On the Dashboard, the Trading performance panel shows daily equity
   candles back to the first trade, with a working 1H/4H/1D/1W switch and
   MTM/Realized toggle.
2. Hovering or tapping a candle shows its O, H, L, C and change; backfilled
   candles say `approx`.
3. During a session, the current 1H and 1D candle update after each scan.
4. A scan in which recording throws still completes and posts its alerts.
5. Readable, with no horizontal scroll, at phone, tablet and desktop widths.
