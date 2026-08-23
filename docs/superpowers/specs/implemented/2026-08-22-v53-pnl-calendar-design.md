Version: ui 1.8.1 · bot 1.3.3
Bump: ui patch (1.8.1 → 1.8.2) — a wholly new, additive workspace page; nothing
an existing user of `/dashboard`, `/trades`, `/analytics`, `/watchlist`,
`/risk` or `/system` sees today changes shape. `bot` none — every new endpoint
is a read-only aggregation over data the bot already writes (`trades.json`,
`journal.json`); no scan, planning, sizing or tracking code path is touched.
Edge: none (integrity) — this is an observability page. It surfaces patterns
(day-of-week, streaks) a human can act on, but the spec itself changes no
gate, discriminator, exit or sizing rule, so it claims no expectancy, harvest
or volume effect on its own.

# P&L calendar admin page

## Problem

The admin UI has no day-by-day view of realized performance. `analytics.ts`
has a strategy×horizon heatmap and rolling win-rate series, `trades.ts` has a
flat sortable list, and `dashboard.ts` has a 30-day equity line — but none of
them answer "was last Tuesday good or bad, and does that P&L amount, or that
outcome, correspond to a real dollar swing or just one R-multiple's worth of
noise?" or "do Mondays consistently look different from Fridays?" A calendar
month grid, color-coded per day with a drill-down into that day's trades, is
the natural view for this and is a well-understood pattern (trading-journal
apps universally have one) that this repo has never built.

## Non-goals (v1)

- **No goal/target tracking.** No monthly-$ or monthly-R target, no progress
  bar. Deferred to a later iteration that can reuse this page's data layer
  once it exists.
- **No week or year view.** Month grid only, with prev/next month navigation.
- **No new charting library.** Built as a DIY component in `ui/`, consistent
  with `Histogram`/`LineChart`/the existing `Heatmap` cell rendering — not a
  reason to add a calendar library as a new frontend dependency.
- **No write path.** Purely a read/aggregation view; nothing here creates,
  edits or closes a trade.

## Data sources and the join

Two existing stores hold complementary, non-overlapping fields for a closed
trade:

- **`TradeLog` / `data/trades.json`** (`swingbot/core/tracking/performance.py`)
  — the source of truth for realized dollars. `_settle_account_balance()`
  (lines 418-476) sets `realized_pnl_amount` at close time from the actual
  `shares` snapshotted at open (`compute_position_size`, config-driven via
  `RISK_PER_TRADE_PCT` / `POSITION_SIZING_MODE`). Also carries `ticker`,
  `strategy`, `horizon_key`, `entry`, `exit_price`, `stop_loss`, `closed_at`,
  `status`. R-multiple is derivable here from `(exit_price - entry) /
  (entry - stop_loss)` (sign-adjusted for shorts) since the raw prices are
  present.
- **`data/journal.json`** (`swingbot/core/tracking/retrospective.py` /
  `swingbot/core/analytics/journal.py`) — the source of truth for
  already-computed `r_realized`, `mfe_r`, `mae_r`, `exit_efficiency`,
  `outcome`, `tags`, `auto_lesson`, `note`, keyed by `trade_id`. No dollar
  field.

The new backend module joins the two by `trade_id` (falling back to
`ticker` + `closed_at` if a `trade_id` is ever missing on one side — log a
warning and drop the trade from the join rather than guess a match). A trade
present in `TradeLog` but absent from the journal still contributes its
dollar amount and grid cell color; it simply has no MFE/MAE/tags/lesson in
the drill-down panel.

## Backend design

**New core module:** `swingbot/core/analytics/pnl_calendar.py`.

Names below are the ones the plan implements; the exact signatures live in
each task's `Interfaces` block.

- `day_of(closed_at)` — the day key, per "Timezone and day boundaries" below.
- `joined_rows(trades, entries)` — the join described above, one row per
  closed trade.
- `filter_rows(rows, strategy=None, horizon=None)` and
  `available_filters(rows)` — narrowing, and the dropdown vocabulary. The
  vocabulary is derived from the **unfiltered** set, so a dropdown never
  shrinks to only the option already chosen.
- `bucket_by_day(rows)` — groups rows by day key.
- `day_summary(day, rows)` → `{date, net_pnl_amount, net_r, trade_count,
  win_rate}`.
- `month_grid(rows, month)` → one `day_summary` per day-with-trades in the
  month (days with none are simply absent — the frontend renders those as
  empty cells), plus the month total over the month's rows as one pool, so a
  1-trade day and a 9-trade day do not carry equal weight in the win rate.
- `day_of_week_breakdown(rows)` → per-weekday (Mon–Fri only — no weekend
  trading) `{weekday, avg_pnl_amount, avg_r, win_rate, trade_count}`,
  averaged **per trade** rather than per day, across all history. All five
  weekdays are always present so the table does not reflow as a filter
  narrows.
- `best_worst_days(rows)` → `{best, worst}`, each a full `day_summary` — a
  *day*, not a trade, since the worst day in the book is usually several
  ordinary losses rather than one spectacular one.
- `day_streak(rows)` → `{direction: "winning"|"losing"|"flat"|None, days}`,
  counting back from the most recent day that had a close. A gap with no
  trades does **not** break the run; treating it as a break would cap almost
  every streak at five.

All of these are pure functions over lists of dicts.
`load_rows(trade_log=None, journal=None)` is the module's single I/O
boundary, so each route does exactly one join pass, and the injectable
stores let tests avoid monkeypatching `config.DATA_DIR`.

**New route file:** `swingbot/admin/api_v1/calendar.py`, registered in
`swingbot/admin/api_v1/__init__.py` alongside `analytics`, `trades`,
`dashboard`.

- `GET /api/v1/calendar/pnl?month=YYYY-MM&strategy=&horizon=` →
  `{month_grid: [...], totals: {...}, day_of_week: [...], best_day: {...},
  worst_day: {...}, streak: {...}}`. `strategy`/`horizon` are optional
  querystring filters, same names as `analytics.py`'s existing filter params
  for consistency.
- `GET /api/v1/calendar/pnl/day?date=YYYY-MM-DD&strategy=&horizon=` →
  `{date, trades: [...]}` — the joined per-trade list for the drill-down
  panel. 404 (not empty 200) if the date has no closed trades, so the
  frontend can distinguish "no data yet" from "a real empty day" — though in
  practice every returned date in `month_grid` already has ≥1 trade, so this
  path is only reachable via a stale/direct request.

## Frontend design

**New top-level workspace:** `frontend/src/app/workspaces/calendar/`,
following the established per-workspace layout:

- `calendar.ts` — the route component (inline template/styles, per the
  existing convention every workspace but `shell/` follows).
- `calendar.helpers.ts` — month-grid date math (which weeks/days belong in
  the visible grid, including the leading/trailing days from adjacent
  months needed to fill the first/last week row).
- `calendar.spec.ts`.

**Paired store:** `frontend/src/app/stores/calendar.store.ts` (ngrx signals,
matching `analytics.store.ts`/`risk.store.ts`), holding: current
`year`/`month`, `strategy`/`horizon` filter selection, the fetched month
grid + totals + day-of-week + best/worst/streak, the selected day (drives
the drill-down panel), and that day's fetched trade list. Two calls to the
new endpoints; the day-list call fires only when a day is clicked (lazy, not
prefetched for the whole month).

**Route:** add `/calendar` to `app.routes.ts` (lazy `loadComponent`, same
`canMatch: [authGuard]` as the other five workspaces) with a nav entry
alongside dashboard/trades/analytics/watchlist/risk/system.

**Month grid UI:**

- Classic 7-column (Mon–Sun) month grid. Weekend cells render in a neutral,
  non-interactive style (greyed, no hover/click) since no trades ever close
  on a weekend for this bot's universe.
- Each weekday cell with ≥1 closed trade shows: the day number, the
  headline number (**dollar P&L by default**, per explicit direction — not
  R), and a background color/intensity driven by that same displayed metric
  (so the color always agrees with the number on screen). A cell with zero
  closed trades on a trading day renders neutral/empty, not zero-colored —
  "no data" and "flat $0 day" must look visually distinct.
- A **$ / R toggle** above the grid switches both the displayed number and
  the color basis together on every cell at once (this was explicitly
  chosen over "color always follows R regardless of toggle").
- **Filter dropdowns** for strategy and horizon, matching the existing
  filter control style in `analytics.ts`, feeding the `strategy`/`horizon`
  querystring params on both endpoints.
- Prev/next month navigation; no other granularity in v1.

**Summary stats strip** (above or beside the grid):

- Month totals: net $, net R, win rate, trade count for the currently
  visible month (updates as the user navigates months).
- Day-of-week breakdown: a small table or bar chart, avg $/R and win rate
  per weekday, computed over full history (not scoped to the visible
  month) subject to the same strategy/horizon filter.
- Best-day / worst-day callouts and the current streak, same full-history +
  filter scope as the day-of-week breakdown.

**Day drill-down:** clicking a weekday cell with trades opens a **side
panel/drawer** (not a modal, not a navigation away from the calendar) listing
every trade closed that day: ticker, strategy, horizon, $ P&L, R-multiple,
outcome, and — where the journal join found a match — tags, auto-lesson, and
MFE/MAE. The calendar grid stays visible and interactive behind the open
drawer so adjacent days can be compared without closing it first.

## Timezone and day boundaries

**A day is `closed_at[:10]` — the UTC calendar day, taken as a string slice.**

This section originally specified Europe/Berlin, matching the admin's
`is_today_berlin` helper. That was corrected while writing the plan, on
three findings:

- The established convention in `core/analytics` is already the slice —
  `metrics.calendar_returns` buckets on `closed_at[:7]` and
  `cumulative_pnl_by_strategy` on `closed_at[:10]`. A Berlin-converted day
  here would put a late close on a different day than the *monthly* figures
  the Analytics page renders from the same records.
- `closed_at` is always written as UTC ISO
  (`datetime.now(timezone.utc).isoformat()`), so the slice is unambiguous
  and needs no `zoneinfo` dependency in a pure module.
- In practice the two rarely differ: US market close is 20:00–21:00 UTC,
  which is the same calendar date in both zones.

The slice must be applied identically in the bucketing and in the
day-drill-down lookup — otherwise a trade appears in one grid cell but 404s
when that cell is clicked.

## Testing

- Unit tests for `pnl_calendar.py`: day-bucketing correctness (including a
  trade closing near a Berlin midnight boundary), the `TradeLog`↔journal join
  (including a trade present in one source but not the other), day-of-week
  aggregation, and streak calculation (including a streak broken by a
  no-trade day vs. a losing day — a no-trade day must not reset a streak).
- Flask route tests for both new `calendar.py` endpoints: happy path,
  strategy/horizon filtering, the day-not-found 404 case, and a month with
  zero closed trades (empty `month_grid`, zeroed totals, not an error).
- Frontend `calendar.spec.ts` and `calendar.store.ts` spec: month navigation,
  the $/R toggle updating both number and color together, filter changes
  triggering a re-fetch, and the drill-down panel opening/closing correctly
  keyed to the clicked date.

## Parallelisation

- **Group 1 (parallel):** the core `pnl_calendar.py` module and its unit
  tests — one task, no dependency on the route layer, can start immediately.
- **Sequential:** the `calendar.py` route file depends on `pnl_calendar.py`
  existing (consumes its functions) — must follow Group 1. The frontend
  `calendar.store.ts` depends on the route response shape being finalized —
  must follow the route task. `calendar.ts` (the component) depends on the
  store's signals — must follow the store task. `app.routes.ts` registration
  is a one-line addition that can happen any time after `calendar.ts` exists.
- **Group 2 (parallel, after Group 1 + routes land):** `calendar.helpers.ts`
  (pure date math, no dependency on the store) can be written and tested
  concurrently with `calendar.store.ts`, since neither file touches the
  other.
