# v165 — P&L calendar day page: context, breakdown, rich trade rows, sparklines

**Version:** ui 1.24.0 · bot 2.5.2 (at writing)
**Bump:** ui minor; bot none — a new admin page (`/calendar/:date`) every admin user opens from the calendar, a richer day drawer, and filters in the calendar URL. The Discord bot is untouched.
**Edge:** none (integrity) — a better view of the realised book. It changes no signal, threshold, plan or badge.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, quant-engineer
**Status:** spec written 2026-10-15 from a brainstorm with the partner (three sections approved in chat).

## Why

Clicking a day on the P&L calendar opens a drawer (`frontend/src/app/workspaces/calendar/calendar.ts:223-290`, shipped c68bedeb) with seven tiles, contributors/detractors and a small trade-id link per trade. The partner wants three things it does not give:

1. **Day vs. normal** — is this a good day for *this book*: percentile among all trading days, rank in the month, month-to-date running P&L, an equity line with the day marked.
2. **What drove it** — the day split by strategy, horizon, direction and exit reason.
3. **Richer trade rows** — entry/exit/stop/targets, hold time, % return, shares, exit reason, a mini price sparkline, and an obvious "Open trade" button.

That is more than a side drawer holds, so it becomes a page at `/calendar/:date`; the drawer stays as the quick preview with an "Open full day" button.

## Facts the design rests on (verified 2026-10-15)

- `GET /calendar/pnl/day` is `calendar_pnl_day` (`swingbot/admin/api_v1/calendar.py:121`). It filters `pc.filter_rows(pc.load_rows(), ...)` to one day and composes the summary inline (running-R drawdown at `:162-168`). Unknown query params are a 400 against `_FILTERS = {"month","strategy","horizon","date"}` (`:26`).
- `pnl_calendar.load_rows` (`swingbot/core/analytics/pnl_calendar.py`) reads `TradeLog`, `JournalStore` and `PlanStore`; `joined_rows` already holds each trade's plan (`by_plan_id`) but uses it only for `legs_realized`. Rows (`_base_row`) carry no prices, stop, targets, shares or exit reason.
- **Prerequisite, uncommitted at writing:** a per-leg split of calendar rows (`leg_closed_at`, `_leg_parts`, `_leg_rows`, `leg_index`/`leg_total` in `ROW_KEYS`) sits uncommitted in the main tree, apparently another session's work. This spec builds on it. It must be committed on `main` before implementation starts.
- Trade record fields: `entry`, `stop_loss`, `take_profit`, `target2`, `shares`, `exit_price`, `realized_pnl_amount`, `opened_at`, `closed_at`, `close_reason`. Plan: `entry_price`, `stop_loss`, `tp1`, `tp2`, `legs_realized[] = {fraction, exit_price, r, reason, closed_at}` (older legs may lack `closed_at` / `r`).
- Exit reason has no single stored field. `metrics._exit_reason_bucket(trade)` (`swingbot/core/analytics/metrics.py:819`) maps `close_reason_text` + `resolve_outcome` onto `EXIT_REASONS` (`:27`: tp1, runner_tp2, runner_trail, runner_be, stop, scratch, timeout, reversed, other).
- Leg pricing on the Trades table: `api_v1/trades.py:_row_from_leg` (`:389`) — leg shares = trade shares × fraction, `pnl_pct` via `dash.closed_pnl`, `_held_hours` (`:166`).
- `/analytics/by-dimension` scopes by **trade**, not leg, so it would disagree with the calendar's per-leg rows on a scale-out day — not reused.
- No light per-ticker bar endpoint exists: `/market/chart/<ticker>` (`market.py:339`) is multi-pane and `window >= 20`.
- Daily bars for the admin side live in `market_data/daily/` behind `marketdata/data_store.load_from_disk` (known-traps § Two OHLCV caches). Spot metals (`XAUUSD`/`XAGUSD`) are never cached under their own name.
- Calendar filters are store signals only (`frontend/src/app/stores/calendar.store.ts:58-78`), not in the URL; trade links go to `['/trades', plan_id ?? trade_id]` (`calendar.ts:262`).

## D1 — Fuller rows (`pnl_calendar.py`, pure)

Each calendar row (whole trade or leg) gains:

| Field | Whole trade | Leg |
|---|---|---|
| `entry_price` | plan `entry_price`, else trade `entry` | same |
| `exit_price` | trade `exit_price` | leg `exit_price`; the remainder part takes the trade's `exit_price` |
| `stop_price` | plan `stop_loss`, else trade `stop_loss` | same |
| `tp1`, `tp2` | plan `tp1`/`tp2`, else trade `take_profit`/`target2` | same |
| `shares` | trade `shares` | trade `shares` × leg `fraction` (remainder part: × uncovered fraction) |
| `held_hours` | `opened_at` → `closed_at` | `opened_at` → the leg's `closed_at` |
| `return_pct` | signed `(exit − entry)/entry × 100` by direction | same, from the leg's exit price |
| `exit_reason` | `metrics._exit_reason_bucket(trade)` | the leg's own `reason` through the same bucketing (exact name, alias, else `other`); the remainder part uses the trade's bucket |

`_exit_reason_bucket` is promoted to a public `exit_reason_bucket` (old name kept as an alias in the same commit; no behaviour change) and a sibling `exit_reason_bucket_text(text)` covers the leg case without building a fake trade. Every missing input yields `null` — never `0`. `held_hours` reuses one shared helper with `trades._held_hours` (moved into `pnl_calendar` and imported back, as `leg_closed_at` already is).

## D2 — Day context (`pnl_calendar.py`, pure)

`day_context(day_rows_by_date, date)`, computed over **all history under the active filter** — the same scope the weekday stats already use:

- `percentile` — share of trading days with net P&L strictly below this day, ties counting half, × 100. A "trading day" is a date with ≥ 1 closed calendar row under the filter. `null` when fewer than **20** such days exist; `history_days` always returned so the page can say why.
- `month_rank` / `month_days` — rank of the day by net P&L within its month (1 = best).
- `mtd_pnl_amount`, `mtd_r` — the month's running total up to and including the day.
- `vs_avg_day` / `vs_weekday_avg` — `{pnl_amount, r}` deltas against the all-history mean day and the mean of the same weekday (reusing the weekday aggregation that feeds `day_of_week`).
- `month_curve` — `[{date, cum_pnl_amount, cum_r}]` for every trading day of the month, for the equity line.

Days with a null net P&L (no computable figure) are excluded from the percentile and ranks, never counted as 0.

## D3 — Day breakdown (`pnl_calendar.py`, pure)

`day_breakdown(rows)` → `{strategy|horizon|direction|exit_reason: [{key, n, pnl_amount, r, win_rate}]}`, built from exactly the rows in the day's `trades` list. Groups are sorted by P&L descending; a null key becomes `"unknown"`. Invariant: each dimension's `n` sums to `trade_count`, and its non-null `pnl_amount` / `r` sum to the tiles' totals.

## D4 — Endpoint changes (`swingbot/admin/api_v1/calendar.py`)

- `GET /calendar/pnl/day` adds `context` (D2) and `breakdown` (D3) to its response alongside the existing fields; existing fields and their meaning are unchanged, so the drawer keeps working. The inline summary code moves into a pure helper so the route stays under complexity 15.
- **New** `GET /calendar/pnl/day/sparklines?date=&strategy=&horizon=` → `{as_of, date, truncated, series: {"<trade_id>:<leg_index>": {closes: [{date, close}], entry, stop, tp1, tp2, exit, exit_date} | null}}`.
  - Reads `data_store.load_from_disk(ticker, "daily")` **only** — never a network fetch, never `backtest_cache`.
  - Window: 3 bars before `opened_at` to 3 bars after the row's close, **clipped at the close date's bar + 3**, never later than that (no "today" price on a historical card).
  - Caps: ≤ 400 bars per series, ≤ 50 series per day; beyond either, `truncated: true`.
  - A ticker with no cached file, a spot-metal symbol, or a window with no bars → `null` for that row.
  - Same `_reject_unknown_params` and date validation as the day route (invalid `YYYY-MM-DD` → 400).

## D5 — Day page (`frontend/src/app/workspaces/calendar/day/`)

Route `calendar/:date` inside `calendar.routes.ts`, query params `strategy`, `horizon`. A `CalendarDayStore` loads the day response and, after it, the sparklines (the page renders before sparklines arrive).

Layout, top to bottom (single column below the existing mobile breakpoint):

1. Header: `← Calendar · <Month YYYY>` (back link carries the filters), the long date, `‹ prev day` / `next day ›` — previous/next **trading day under the filter**, from `context.month_curve` plus one cross-month lookup when at the month's edge (`/calendar/pnl` for the adjacent month).
2. The seven existing tiles (same `sb-stat-tile` use as the drawer).
3. Two panels side by side: **How this day compares** (percentile with `of N trading days`, month rank, vs-avg-day, vs-avg-weekday; below 20 days: "Only N trading days so far — percentile hidden") and **Month so far** (equity line from `month_curve`, this day marked, MTD figures).
4. **What drove it**: one panel, tabs Strategy / Horizon / Direction / Exit; each row `key · n · P&L · R · win% · bar` (pos/neg tokens).
5. **Trades (n)** with sort (P&L, R, close time, ticker). Each card: ticker, direction, strategy, horizon, leg label, exit-reason chip, P&L, R, % return; prices line; held time, shares, MFE/MAE; sparkline (120×32, entry/stop/target ticks, exit dot; click → `/trades/<id>` Chart tab); **Open →** button to `/trades/<plan_id ?? trade_id>`; lesson and tags as today. `null` figures render `—`.

Empty day or a date with no rows: "No closed trades on <date> under this filter", prev/next still work. Malformed `:date` → the same empty state, no request.

## D6 — Drawer and calendar URL

- Drawer gains an **Open full day →** button linking to `/calendar/<date>?strategy=&horizon=`.
- The calendar page reads/writes `month`, `strategy`, `horizon` as query params (store initialises from the URL, writes back with `replaceUrl`), so the day page's back link returns to the same filtered month.

## Testing

- **Python** (`tests/analytics/test_pnl_calendar.py`, `tests/admin/test_api_v1_calendar.py`; no new test directory, suites unchanged): every D1 field for whole trade, leg and remainder part; null inputs; leg exit-reason bucketing; percentile ties and the < 20 days null; month rank; MTD at a month boundary equals the month's `totals`; day net equals that day's `/calendar/pnl` cell for the same filter; breakdown sums equal tiles; sparkline cache hit / miss / spot metal / truncation / clip after exit / bad date / unknown param.
- **Frontend specs**: route parsing and filter round trip; prev/next skipping empty days and crossing a month; percentile hidden below 20 days; breakdown tab switch; card Open link target and sort; sparkline null state; drawer "Open full day" link carries filters; calendar filters restored from the URL.
- Every new or changed function < complexity 15 (`radon cc -s -n C`).

## Out of scope

- Intraday (hourly) sparklines; any network fetch from the admin API.
- Changing how a day's P&L is computed (that is the per-leg split's job).
- Breakdowns on the month view.

## What follows

Nothing scheduled. If the breakdown proves useful, the same `day_breakdown` could feed a month-level "what drove it" panel.
