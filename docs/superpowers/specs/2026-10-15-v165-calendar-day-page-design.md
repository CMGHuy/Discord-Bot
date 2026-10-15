# v165 — P&L calendar day page: context, breakdown, rich trade rows, sparklines

**Version:** ui 1.24.0 · bot 2.5.2 (at writing)
**Bump:** ui minor; bot none — a new admin page (`/calendar/:date`) every admin user opens from the calendar, a richer day drawer, and filters in the calendar URL. The Discord bot is untouched.
**Edge:** none (integrity) — a better view of the realised book. It changes no signal, threshold, plan or badge.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, quant-engineer
**Status:** spec written 2026-10-15 from a brainstorm with the partner (three sections approved in chat); revised the same day after the staff-engineer panel seat and a re-read of the prerequisite, which another session reshaped while this spec was written (see `## Panel review`).

## Why

Clicking a day on the P&L calendar opens a drawer (`frontend/src/app/workspaces/calendar/calendar.ts:223-290`, shipped c68bedeb) with seven tiles, contributors/detractors and a small trade-id link per trade. The partner wants three things it does not give:

1. **Day vs. normal** — is this a good day for *this book*: percentile among all trading days, rank in the month, month-to-date running P&L, an equity line with the day marked.
2. **What drove it** — the day split by strategy, horizon, direction and exit reason.
3. **Richer trade rows** — entry/exit/stop/targets, hold time, % return, shares, exit reason, a mini price sparkline, and an obvious "Open trade" button.

That is more than a side drawer holds, so it becomes a page at `/calendar/:date`; the drawer stays as the quick preview with an "Open full day" button.

## Facts the design rests on (verified 2026-10-15)

- `GET /calendar/pnl/day` is `calendar_pnl_day` (`swingbot/admin/api_v1/calendar.py:121`). It filters `pc.filter_rows(pc.load_rows(), ...)` to one day and composes the summary inline (running-R drawdown at `:162-168`). Unknown query params are a 400 against `_FILTERS = {"month","strategy","horizon","date"}` (`:26`).
- The day route answers **404** when the day has no rows (`calendar.py:143-144`); the drawer relies on that. This spec keeps the contract.
- **Prerequisite, uncommitted at writing and still moving:** another session's per-leg split. As of the revision it is `performance.expand_realized_legs(trade)` (uncommitted, `swingbot/core/tracking/performance.py`), consumed by `pnl_calendar._row_for(part, entry)` inside `joined_rows`; it also changes the Dashboard's realised card (`api_v1/dashboard.py`). Each part is `{**trade, legs: None, shares: shares × fraction, exit_price: leg exit, closed_at: leg close, status, leg_index, leg_total}` built from the **trade's** `legs` (`expand_trade_legs`, `performance.py:425-470`); the still-open remainder is dropped and the closing leg carries trade total minus earlier legs. A part does **not** carry the leg's `reason`. That work and its bump are the other session's; this spec only consumes it. **Plan task 1 re-verifies this shape on `main` and stops if the split has not landed or no longer matches.**
- Trade record fields: `entry`, `stop_loss`, `take_profit`, `target2`, `shares`, `exit_price`, `realized_pnl_amount`, `opened_at`, `closed_at`, `close_reason`, `legs[] = {fraction, exit_price, reason, closed_at}`.
- Exit reason has no single stored field. `metrics._exit_reason_bucket(trade)` (`swingbot/core/analytics/metrics.py:819`) maps `close_reason_text` + `resolve_outcome` onto `EXIT_REASONS` (`:27`: tp1, runner_tp2, runner_trail, runner_be, stop, scratch, timeout, reversed, other).
- Leg pricing already exists twice (`expand_trade_legs`; `api_v1/trades.py:_row_from_leg` `:389`). This spec adds no third copy: D1 reads the part's own fields.
- `/analytics/by-dimension` scopes by **trade**, not leg, so it would disagree with the calendar's per-leg rows on a scale-out day — not reused.
- No light per-ticker bar endpoint exists: `/market/chart/<ticker>` (`market.py:339`) is multi-pane and `window >= 20`.
- Daily bars for the admin side live in `market_data/daily/` (known-traps § Two OHLCV caches). `data_store.load_from_disk` (`:216`) re-parses the full CSV each call; `data_store.load_normalized` (`:285`) goes through a bounded process-local frame cache keyed by file identity (`:227ff`). Spot metals (`XAUUSD`/`XAGUSD`) are never cached under their own name.
- Calendar filters are store signals only (`frontend/src/app/stores/calendar.store.ts:58-78`), not in the URL; trade links go to `['/trades', plan_id ?? trade_id]` (`calendar.ts:262`).

## D1 — Fuller rows (`pnl_calendar.py`, pure)

`_row_for` gains these fields, read from the part (`expand_realized_legs` row) and its parent trade `t` — never re-derived from the plan, never a third copy of leg pricing:

| Field | Source |
|---|---|
| `entry_price` | part `entry` |
| `exit_price` | part `exit_price` (leg exit for a leg, trade exit for a whole trade) |
| `stop_price` | part `stop_loss` |
| `tp1`, `tp2` | part `take_profit`, `target2` |
| `shares` | part `shares` (already leg-scaled) |
| `held_hours` | part `opened_at` → part `closed_at` |
| `return_pct` | signed `(exit − entry) / entry × 100` by `direction` |
| `exit_reason` | whole trade: `metrics.exit_reason_bucket(t)`; leg: `metrics.exit_reason_bucket_text(t["legs"][leg_index]["reason"])`, `other` when nothing matches |

`metrics._exit_reason_bucket` is renamed `exit_reason_bucket` and its two internal callers (`metrics.py:865,887`) renamed in the same commit — no alias. Its text-matching half is split out as `exit_reason_bucket_text(text)` (exact name, alias, else `None`); `exit_reason_bucket(trade)` keeps its `resolve_outcome` fallback. The trade-level function's behaviour is unchanged (existing exit-quality tests are the guard). `held_hours` is a small pure helper in `pnl_calendar`; `api_v1/trades._held_hours` is not touched (no new admin → analytics import). Every missing input yields `null` — never `0`. `return_pct` is `null` when `entry` is missing or `0`; for `bearish` the sign flips (`(entry − exit) / entry`). `held_hours` is `null` when either stamp is missing or `closed_at < opened_at`. A whole trade has `leg_index = 0`, `leg_total = 1` (as `expand_realized_legs` already assigns).

Leg figures follow the prerequisite as-is and claim one invariant only: a trade's leg `pnl_amount`s sum to its `realized_pnl_amount` (the closing leg absorbs rounding). Leg `r_multiple`s are each leg's own R (`metrics.r_multiple(part)`), as on the Trades table; they are **not** additive to the trade's journal R, and nothing on the page sums them as if they were.

## D2 — Day context (`pnl_calendar.py`, pure)

`day_context(rows, date)` — the filtered calendar rows (all history) and the day — computed over **all history under the active filter**, the same scope the weekday stats already use:

- `percentile` — share of trading days with net P&L strictly below this day, ties counting half, × 100. A "trading day" is a date with ≥ 1 closed calendar row under the filter. `null` when fewer than **20** such days exist; `history_days` always returned so the page can say why.
- `vs_avg_day` / `vs_weekday_avg` — `{pnl_amount, r}` deltas against the all-history mean day and the mean of the same weekday (reusing the weekday aggregation that feeds `day_of_week`).

Month rank, month-to-date and the month equity line are **not** server fields: the page already fetches `/calendar/pnl?month=` (D5) and derives them in a pure, spec-tested frontend helper from its `days`, so they cannot disagree with the grid.

Definitions, fixed:

- A day's net P&L / net R is the **same rule the calendar cell already uses** (sum of non-null rows; `null` when every row is null). Plan task 1 reads that rule from `summarise`/`day_cells` and D2/D3 call the same helper — no second definition.
- Days with a null net are excluded from the percentile and the averages, never counted as 0. A null net R day is excluded from the R deltas only.
- The reference set is **the other trading days**: this day is excluded from its own percentile, the all-history mean and the weekday mean. `percentile` = (days strictly below + ½ × ties) / other days × 100. `history_days` counts the other days.
- Below 60 other days the page shows the percentile as a band (bottom / middle / top third) with "small sample"; below 20 it hides it (D7).

## D3 — Day breakdown (`pnl_calendar.py`, pure)

`day_breakdown(rows)` → `{strategy|horizon|direction|exit_reason: [{key, n, pnl_amount, r, win_rate}]}`, built from exactly the rows in the day's `trades` list. Groups are sorted by P&L descending; a null key becomes `"unknown"`. `win_rate` is `null` for a group with no decided rows, never 0. Invariant: each dimension's `n` sums to `trade_count`, and its non-null `pnl_amount` / `r` sum to the tiles' totals.

## D4 — Endpoint changes (`swingbot/admin/api_v1/calendar.py`)

- `GET /calendar/pnl/day` adds `context` (D2) and `breakdown` (D3) to its response alongside the existing fields; existing fields, their meaning and the 404-on-empty contract are unchanged, so the drawer keeps working. The inline summary code moves into a pure helper so the route stays under complexity 15.
- **New** `GET /calendar/pnl/day/sparklines?date=&strategy=&horizon=` → `{as_of, date, truncated, series: {"<trade_id>:<leg_index>": {closes: [{date, close}], entry, stop, tp1, tp2, exit, exit_date} | null}}`.
  - Reads `data_store.load_normalized(ticker, "daily")` **only** (the process-cached loader) — never a network fetch, never `backtest_cache`, never `load_from_disk`.
  - Cost, stated: one more `pc.load_rows()` (three store reads) per day-page view, plus ≤ 50 cached frame loads (cold: one CSV parse per ticker, then cache hits). Accepted for an admin page opened by hand; the route stays separate so tiles render before sparklines. If it shows in admin latency, the follow-up is a short-TTL memo of `load_rows` — not built now.
  - Bars are keyed by exchange date (the frame's tz-naive daily index). The entry bar is the first bar on or after the UTC date of `opened_at`; the exit bar is the last bar on or before the row's calendar `day` (`day_of(closed_at)`, the same UTC-date rule the calendar uses).
  - Window: 3 bars before the entry bar to 3 bars after the exit bar, never later (no "today" price on a historical card). The 3 post-exit bars are **deliberate context**: the response marks `exit_bar` and the page draws bars after it dimmed. The exit bar's close is the session close, not the intraday fill — the exit dot is drawn at the recorded `exit` price, not the bar's close.
  - Level ticks are the **recorded** trade prices (`entry`, the final recorded `stop_loss` — labelled "final stop", since a trailed or break-even runner's stop moved — `take_profit`, `target2`, exit). When `entry` lies outside the window's `[min Low, max High]` (a split or adjustment since entry), all ticks are returned `null` and only the close line is drawn.
  - Per series: `last_bar` (date of the frame's last bar) and `stale: true` when `last_bar` is before the exit bar's date (the market_data cache never self-heals; the line then stops early and says so).
  - Caps, deterministic: rows are taken in `closed_at` order, first 50; a series over 400 bars keeps the **last** 400 (the end nearest the exit). Either cut sets `truncated: true`.
  - Each frame is sliced to its window immediately and only the slice is serialised; the full-history copy `load_normalized` returns is not retained.
  - A ticker with no cached file, a spot-metal symbol (decided by the existing `marketdata/spot_metals` helper, never a hand-written list), or a window with no bars → `null` for that row.
  - Same `_reject_unknown_params` and date validation as the day route (invalid `YYYY-MM-DD` → 400).

## D5 — Day page (`frontend/src/app/workspaces/calendar/day/`)

Route `calendar/:date` inside `calendar.routes.ts`, query params `strategy`, `horizon`. A `CalendarDayStore` loads, in parallel, the day response and `/calendar/pnl?month=<the date's month>`; after the day response, the sparklines (the page renders before sparklines arrive). A 404 from the day route is the empty state, not an error. The month response feeds prev/next, month rank, MTD and the month equity line through a pure helper `month-context.ts`.

Layout, top to bottom (single column below the existing mobile breakpoint):

1. Header: `← Calendar · <Month YYYY>` (back link carries the filters), the long date, `‹ prev day` / `next day ›` — previous/next **trading day under the filter**, from the month response's `days` (`trade_count > 0`) plus one lookup of the adjacent month at the month's edge.
2. The seven existing tiles (same `sb-stat-tile` use as the drawer), under the page caption from D7.
3. Two panels side by side: **How this day compares** (percentile with `of N trading days`, month rank, vs-avg-day, vs-avg-weekday; below 20 days: "Only N trading days so far — percentile hidden") and **Month so far** (equity line from the month's `days`, this day marked, MTD figures, "3rd best of 14 days").
4. **What drove it**: one panel, tabs Strategy / Horizon / Direction / Exit; each row `key · n · P&L · R · win% · bar` (pos/neg tokens) — P&L and R before win%, and win% greyed and replaced by `—` when `n < 5`.
5. **Trades (n)** with sort (P&L, R, close time, ticker). Each card: ticker, direction, strategy, horizon, leg label, exit-reason chip, P&L, R, % return; prices line; held time, shares, MFE/MAE; sparkline (120×32, entry/stop/target ticks, exit dot; click → `/trades/<id>` Chart tab); **Open →** button to `/trades/<plan_id ?? trade_id>`; lesson and tags as today. `null` figures render `—`.

Empty day or a date with no rows: "No closed trades on <date> under this filter", prev/next still work. Malformed `:date` → the same empty state, no request.

## D6 — Drawer and calendar URL

- Drawer gains an **Open full day →** button linking to `/calendar/<date>?strategy=&horizon=`.
- The calendar page reads/writes `month`, `strategy`, `horizon` as query params (store initialises from the URL, writes back with `replaceUrl`), so the day page's back link returns to the same filtered month.

## D7 — Presentation honesty (financial-advisor seat)

- **Persistent caption** at the top of the day page and in the drawer's summary: "Paper trades · P&L before commissions, fees and tax". Verified 2026-10-15: `realized_pnl_amount` deducts no frictions (`swingbot/core/tracking/performance.py` has no friction step; `edge/frictions.py` is a backtest-side model).
- **N is always next to a comparison**: "87th percentile of 212 other trading days", "3rd best of 14 days in October". Below 60 other days: band + "small sample"; below 20: hidden with "Only N trading days so far".
- **No celebratory styling**: comparison figures use neutral text colour regardless of rank; only P&L/R signs use the pos/neg tokens. The context panel carries a fixed line: "One day is not evidence of edge."
- **R explained**: every R figure's header has a tooltip "R = the trade's initial risk (entry to stop). +1R made what was risked."
- **Legs counted as trades, said once**: when the day has any `leg_total > 1` row, the tiles' sample line reads "N rows · scale-out legs count separately".

## Testing

- **Python** (`tests/analytics/test_pnl_calendar.py`, `tests/admin/test_api_v1_calendar.py`; no new test directory, suites unchanged): every D1 field for whole trade, leg and remainder part; null inputs; leg exit-reason bucketing; percentile ties and the < 20 days null; vs-average deltas; renamed `exit_reason_bucket` keeps exit-quality output identical; day net equals that day's `/calendar/pnl` cell for the same filter; breakdown sums equal tiles; sparkline cache hit / miss / spot metal / truncation / clip after exit / bad date / unknown param.
- **Python, panel additions**: percentile excludes the day itself; null-net days excluded; band thresholds are page-side; leg `pnl_amount`s sum to the trade's `realized_pnl_amount`; `return_pct` null on zero entry and sign-flipped for shorts; `held_hours` null when reversed; sparkline exit/entry bar selection across a UTC/exchange date mismatch, post-exit bars marked, ticks nulled when entry is outside the window range, `stale` when the cache ends early, deterministic truncation order.
- **Frontend specs**: D7 caption present on page and drawer; win% suppressed below n 5; percentile band below 60 and hidden below 20; `month-context` (rank, MTD on the last day equals month `totals`, curve); route parsing and filter round trip; a day 404 renders the empty state with prev/next; prev/next skipping empty days and crossing a month; percentile hidden below 20 days; breakdown tab switch; card Open link target and sort; sparkline null state; drawer "Open full day" link carries filters; calendar filters restored from the URL.
- Every new or changed function < complexity 15 (`radon cc -s -n C`).

## Out of scope

- Intraday (hourly) sparklines; any network fetch from the admin API.
- Changing how a day's P&L is computed (that is the per-leg split's job).
- Breakdowns on the month view.

## What follows

Badge tier on day cards (financial-advisor finding 5) — needs a per-row registry lookup; a candidate follow-up. If the breakdown proves useful, the same `day_breakdown` could feed a month-level "what drove it" panel.

## Panel review

Run 2026-10-15 on the committed spec (02ec711d) and its first revision; serial, staff-engineer → financial-advisor → quant-engineer.

- staff-engineer 1: prerequisite described from an older shape (`leg_closed_at`/`_leg_parts`); it is now `expand_realized_legs` -- applied (Facts and D1 rewritten; plan task 1 re-verifies)
- staff-engineer 2: the prerequisite's Dashboard blast radius and bump are unnamed -- applied (named as the other session's, consumed only)
- staff-engineer 3: day route 404s on an empty day, so prev/next cannot come from its body -- applied (404 kept; page reads `/calendar/pnl?month=`; `month_curve`/rank/MTD moved client-side)
- staff-engineer 4: `load_from_disk` re-parses full CSVs -- applied (`load_normalized`, cost stated)
- staff-engineer 5: sparklines re-run `load_rows` -- applied (cost stated and accepted; memo named as the follow-up)
- staff-engineer 6: third copy of leg share/price maths; new admin → analytics import for `_held_hours` -- applied (D1 reads part fields; `trades._held_hours` untouched)
- staff-engineer 7: alias without an owner -- applied (callers renamed, no alias)
- staff-engineer 8: hindsight check belongs to quant-engineer -- applied (covered by quant-engineer 1-2)
- financial-advisor 1 [BLOCKING]: figures shown without saying paper / pre-cost -- applied (D7 caption; frictions verified not deducted)
- financial-advisor 2: coarse percentile at small N -- applied (band below 60, hidden below 20, N always shown)
- financial-advisor 3: "best day" framing invites chasing -- applied (neutral styling, fixed caption)
- financial-advisor 4: R unexplained; % of account; drawdown/losing streak -- applied in part (R tooltip); rejected: % of account (the calendar carries no account size) and losing streak (the calendar page already shows the day streak)
- financial-advisor 5: badge tier chip on cards -- rejected: needs a per-row registry lookup outside this spec's seam; recorded in What follows
- financial-advisor 6: tiny-N win% in breakdown -- applied (P&L/R first, win% suppressed below n 5)
- financial-advisor 7: legs counted as trades -- applied (D7 sample line)
- quant-engineer 1: post-exit bars are hindsight -- applied (kept as marked, dimmed context; exit dot at the fill price)
- quant-engineer 2: UTC day vs exchange-date bars; entry lookup rule -- applied (D4 bar rules)
- quant-engineer 3: stale cache undetected -- applied (`last_bar`, `stale`)
- quant-engineer 4: recorded ticks vs adjusted closes; final vs planned stop -- applied (final stop labelled; ticks nulled outside range)
- quant-engineer 5: whole-trade key -- applied (`leg_index` 0, `leg_total` 1)
- quant-engineer 6: truncation not deterministic -- applied (closed_at order, last 400 bars)
- quant-engineer 7: day in its own reference set -- applied (other days only)
- quant-engineer 8: partial-null day net and win_rate n=0 -- applied (reuse the cell rule; null win rate)
- quant-engineer 9: leg R vs P&L invariants -- applied (P&L-sum test; leg R stated non-additive)
- quant-engineer 10: `return_pct` / `held_hours` null rules -- applied
- quant-engineer 11: deep copies -- applied (slice, do not retain)
- quant-engineer 12: spot-metal list could drift -- applied (existing `spot_metals` helper)
