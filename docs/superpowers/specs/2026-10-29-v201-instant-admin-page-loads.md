# v201 — Instant admin page loads: DB data first, market data from a background refresher

**Version:** ui 1.37.2 · bot 2.15.7
**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer, financial-advisor

## Why

Opening the dashboard shows a blank page or spinner for several seconds before
any trade appears, even though every trade is already in Postgres. The partner
wants data the database already holds on screen almost at once on every page.
Only values that need the market API (live prices and the P&L, FX and
risk/analytics figures built from them) may arrive later, and those show a
loading indicator.

### Measured on production, 2026-10-29

Measured with a read-only Playwright run against bomeo-capital.com: navigation
by clicking the rail, logged in with the `.env` admin account. The script lives
in the session scratchpad and is reproduced in the verification task of the
plan.

| Page | First data visible | Slowest call |
|---|---|---|
| Dashboard (after login) | never inside 30 s budget on one pass; 8–22 s per `/dashboard` call | `GET /dashboard?mode=today` 8.3 s, 19.2 s, 22.6 s (fired **three** times) |
| Dashboard (rail click) | shell at 0.2 s, data after `/dashboard` 10–14 s | same |
| Trades | 20.5 s | `GET /trades?page=1&per_page=200` 19.3 s |
| Watchlist | 2.7 s | `GET /watchlist/tickers` 2.1 s (already lazy, see below) |
| Risk | timed out (30 s) | `GET /risk` failed at 30 s |
| Analytics | timed out (30 s) | `/analytics/equity-curve` 47.5 s, `/analytics/performance` failed at 30 s |
| Calendar | timed out (30 s) | `/calendar/pnl` failed at 30 s |

`GET /system/scan` (shell status poll, about once a second) took 0.1 s on a
quiet server and **56–75 s** once the slow calls above piled up. The run ended
with every request failing. The probe's own concurrent page loads contributed
to the pile-up, but the mechanism below is real and a single user triggers it
on login (dashboard ×3 + trades ×2 + tape ×3 in parallel).

### Root causes (code map, 2026-10-29)

1. **Request threads fetch market data.** The DB reads are fast. The time goes
   to market calls made synchronously inside the request:
   - `dashboard()` (`swingbot/admin/api_v1/dashboard.py:331`) → `_open_figures`
     → `build_open_trade_views` → `_open_trade_prices`
     (`swingbot/admin/dashboard.py:348-358`). With the layer on, that is
     `page_quotes`, which fetches when the asker's window has expired.
   - FX: `convert_amount` / `to_account_currency`
     (`swingbot/admin/api_v1/money.py:93-107`) → `fx.quote_currency_code`
     (`swingbot/core/marketdata/fx.py:75`) makes one network call per uncached
     ticker. Unknown answers are never cached, so they are retried on every
     request. `_pair_frame` refreshes the FX daily file synchronously every
     15 min (`fx.py:127-148`).
   - `_equity_30d` (`dashboard.py:49`) runs `load_snapshot(3600) or
     refresh_snapshot()`, a synchronous rebuild. `refresh_snapshot` returns
     `None` (`swingbot/core/analytics/snapshots.py:108`), so the request that
     rebuilds gets an empty sparkline.
   - `list_trades` (`swingbot/admin/api_v1/trades.py:1039`):
     `_attach_current_prices` (`trades.py:1302`) prices the page's live rows.
     Sorting by pnl/progress/R prices **every** row (`trades.py:1081-1085`).
     `follow_score` runs for every plan (`trades.py:724`).
   - `get_risk` (`swingbot/admin/api_v1/risk.py:404`) runs
     `collect_portfolio_state`: 4.1 s quiet, up to 52 s under a scan, plus
     daily bars for metrics/correlation. It sits behind a 15 s single-flight
     cache (`risk.py:188-209`).
2. **The server serialises those calls.** Gunicorn runs one worker with 16
   gthreads (`deploy/gunicorn.conf.py`). Every yfinance download takes one
   process-wide `_DOWNLOAD_LOCK` (`swingbot/core/marketdata/yf_safe.py:32,71`).
   A few slow requests hold threads and the lock, so cheap requests queue
   behind them. That is the `/system/scan` 75 s.
3. **Every route blocks on its data.** `resolveRoute`
   (`frontend/src/app/routing/route-resolver.ts:9-40`) is used by the
   dashboard, trades, watchlist and risk routes. The page component is not
   created until the resolver's call returns, so the shaped `sb-async`
   skeletons each page already has never show on navigation. The user sees
   the "Loading X" veil (`route-loading.service.ts`, 1 s delay).
4. **A reload forces live fetches.** For 10 s after a full load every GET
   carries `X-Swingbot-Fresh: 1` (`frontend/src/app/api/fresh-request.service.ts:14,40`,
   `interceptors.ts:103`). The server maps that to `ADMIN_FRESH`, a 0 s window
   (`swingbot/core/marketdata/shared/kinds.py:53,158`), so a reload is the
   slowest possible load.
5. **Duplicate requests.** The dashboard store's `onInit` effect calls `load()`
   as well as the resolver (`frontend/src/app/stores/dashboard.store.ts:446-451`),
   and `/market/tape` is requested by both the tape store and the market-index
   store. Measured: `/dashboard` three times on login.

Production runs `MARKETDATA_LAYER=on` (checked 2026-10-29), so the shared
Postgres quote cache and its per-asker windows (`swingbot/config.py:848-851`)
are live and are the natural home for refreshed prices.

### Already done right: the watchlist

`/watchlist/tickers` reads daily bars from the disk cache, reads prices with
`cached_quotes` (never fetches), and warms them in a background thread with
`warm_quotes_background` (`swingbot/admin/freshness.py:84-104`,
`watchlist_rows.py:190-201`). It loads in about 2 s while the rest time out.
This spec extends that pattern to every page and moves the warming from
per-request threads to one scheduled refresher.

## What the partner decided

- **DB data renders immediately** on every page. No page waits on the market
  before showing trades, positions, plans, stats or anything else read from
  Postgres.
- **Market-derived values show the last known value immediately**, with its
  age (e.g. "12s ago"). A **small spinner sits beside the value while a
  refresh of it is in flight, including a refresh the background job started
  on its own**, not only one the page asked for. The value updates in place
  when the fresh one lands. An empty cell with a spinner appears only when no
  value has ever been stored for it.
- **A background job keeps prices fresh every ~30 s while the US market is
  open**, slower outside regular hours.
- **Heavy computed pages (Risk, Analytics, the dashboard equity sparkline,
  Calendar P&L) follow the same pattern.** The background job recomputes and
  stores a snapshot. The page shows the last snapshot instantly, with its age
  and the same spinner while a recompute runs.
- **Success target: data visible in under 2 s** on every main page.

## Goals

1. Every API endpoint the admin SPA calls on page load answers from Postgres
   and stored caches/snapshots only. **No request thread makes a market-data
   or FX network call**, apart from the one explicit exception below.
2. One **background market refresher** owns all market fetching the admin site
   needs: quotes for open trades, pending/active plans, the watchlist and the
   tape symbols; FX pairs and quote-currency codes; and the heavy snapshots.
3. Every market-derived value the API returns carries **when it was observed**
   and **whether a refresh of it is in flight**, so the UI can draw the age and
   the spinner.
4. Pages render without a blocking resolver. The skeleton/`sb-async` states
   already in each page cover first-ever-empty data.
5. The SPA learns about new values **without refetching whole endpoints**.
6. Production, measured with the same Playwright timing script: on Dashboard,
   Trades, Trade detail, Watchlist, Risk, Analytics and Calendar, **first data
   visible ≤ 2 s** after the click, cold and warm, **including while a scan
   is running**. Every page-load API call ≤ 2 s. `/system/scan` stays ≤ 0.5 s
   throughout.

## Non-goals

- Discord alerts, the scan pipeline, plan building, backtests: untouched. The
  refresher must not write into the OHLCV/daily-bar caches the scan and
  backtests read.
- **The shared quote cache stays shared, as v171 designed it.** The Postgres
  quote cache already serves every asker (`STOP_MONITOR`, `REQUOTE`, `SCAN`,
  `BACKGROUND`, admin), each within its own freshness window
  (`swingbot/core/marketdata/shared/kinds.py:37-73`). Today the admin pages'
  request-time fetches already land there and can satisfy a stop-monitor read.
  The refresher writes as the existing `BACKGROUND` asker. The stop monitor
  and scan keep their own windows and fetch themselves whenever the cached
  quote is older than that window. Their behaviour is unchanged, so no
  separate admin namespace is needed. A regression test pins that a
  stop-monitor read still fetches when the cached quote is older than its
  window.
- No new market data provider and no paid tier.
- No redesign of any page's layout. Only loading states, age labels and
  spinners change.
- Not a WebSocket/SSE push channel unless the builder finds polling cannot meet
  goal 5 cheaply (see "Left to the builder").

## Anti-goals (it fails even if it "works")

- **A price shown without its age.** A stale number that looks live is worse
  than a spinner.
- **A spinner that never stops.** When the provider fails, the cell shows the
  last value with its (growing) age and an error state per the existing
  `sb-async` convention, not an endless spinner.
- **Totals mixing fresh and stale prices silently.** Equity/P&L totals carry
  the age of their **oldest** input.
- **Moving the jam instead of removing it.** A refresher that runs inside the
  gunicorn worker and holds `_DOWNLOAD_LOCK` for long batches would still stall
  request threads. The refresher must not share the request process's yfinance
  lock or thread pool.
- **Rate-limit regressions.** One batched quote call per cycle for all
  symbols, not one per symbol. Yahoo stays the fallback for symbols Alpaca
  misses, and serial fallbacks are capped per cycle.

## Design

### 1. Background market refresher (server)

A single long-running loop, **outside the gunicorn worker**. My call: a third
process in the existing image, either a small `refresher` compose service or
the bot container's scheduler. The builder picks after checking memory and
compose constraints, but it is never the admin worker. Only one instance runs
(Postgres advisory lock or equivalent).

Each cycle:

- **Symbol set:** open trades, active/pending plans, watchlist, tape/index
  symbols. Recomputed every cycle from Postgres.
- **Quotes:** one batched provider call (Alpaca first, yfinance fallback for
  the misses, the fallback capped per cycle). Results are written to the
  shared Postgres quote cache (`MARKETDATA_LAYER=on` layer) with their
  observed-at time.
- **Cadence:** ~30 s during US regular hours. My call: 5 min in pre/after-hours
  and 30 min when closed. All three are config fields in `swingbot/config.py`,
  hot-reloadable.
- **FX:** quote-currency codes resolved in the background for every symbol in
  the set and persisted, **including "unknown"** answers with a retry backoff,
  so a request never resolves a code over the network. FX pair frames are
  refreshed here, not in `_pair_frame` on a request.
- **Snapshots:** after each quote cycle, and after each scan completes, it
  recomputes and stores:
  - the risk payload (`collect_portfolio_state` and its metrics/correlation);
  - analytics performance and the equity curve per ledger;
  - the dashboard equity sparkline;
  - calendar P&L for the current and previous month.

  My call: heavy snapshots at most every 5 min during market hours unless a
  trade opened or closed.
- **In-flight marks:** before fetching a symbol batch or recomputing a
  snapshot, it marks those keys "refreshing" (with a started-at time, expiring
  automatically after a timeout so a crash never leaves a permanent spinner).
  It clears the marks when done.

Snapshots live in Postgres, so they survive restarts and are readable by every
worker. A new table follows `schema-evolution.md` (Alembic revision).

### 2. Request path (server)

- All page-load endpoints read quotes with the never-fetch read
  (`cached_quotes`-style). Snapshots come from the snapshot store, and
  FX/quote-currency codes from the persisted table. The "fetch if older than
  window" paths (`page_quotes`, `prefetch_prices` +
  `get_current_price` loops, `fx.quote_currency_code` network path,
  `refresh_snapshot` on request, `collect_portfolio_state` on request) are no
  longer called from request handlers.
- **Every market-derived field gets two siblings:** an `as_of` timestamp and a
  `refreshing` boolean. Totals get the oldest `as_of` of their inputs and
  `refreshing` if any input is refreshing.
- **Never-seen symbols** (e.g. a ticker added a moment ago): the value is
  `null`, `refreshing: true`, and the request **asks the refresher** for an
  out-of-cycle fetch of that symbol (a queue row or notify). It does not fetch
  itself.
- **Trades sorting by pnl/progress/R** sorts on the cached prices, so it no
  longer prices every row on request.
- **The only exception to "no fetch on request"** is an explicit user action
  that asks for a refresh (e.g. a Refresh button, if one exists or is added).
  It enqueues a priority refresh and returns immediately; it never blocks.
- `X-Swingbot-Fresh` / `ADMIN_FRESH` no longer forces a request-time fetch. A
  reload shows cached values and the spinner covers the refresh. My call: the
  header becomes a hint that bumps the page's symbols to the front of the
  refresher's queue.
- A small **delta endpoint** (e.g. `GET /market/updates?since=<cursor>`)
  returns the quotes and snapshot keys whose value or refreshing state changed
  since the cursor. It is cheap (indexed by updated-at) and never fetches.

### 3. SPA

- Remove `resolveRoute` blocking from the dashboard, trades, watchlist and
  risk routes (and any other route using it). Each page component renders at
  once. Its store kicks off its own load, and the existing `sb-async` shaped
  skeletons cover first-load emptiness. The `RouteLoadingService` veil no
  longer appears for these routes.
- Fix duplicate loads: the dashboard store loads once per navigation, and
  `/market/tape` is fetched once per poll and shared between the tape and
  market-index stores.
- A shared **live-values service** polls the delta endpoint while a page is
  visible. My call: every 5 s while the market is open, every 60 s otherwise,
  and paused when the tab is hidden. It patches values in the existing stores.
  Market-derived cells render through one small component: value, age label,
  and an `sb-spinner` beside it while `refreshing` is true. Ages tick
  client-side.
- When a value's age passes a staleness threshold (my call: 3 refresh cycles),
  the age label shows a warning style. When the refresher reports an error
  for it, the existing `sb-async` error style applies.
- Mobile, tablet and desktop: the age label and spinner wrap under the value
  on narrow widths and never widen table columns (per `ui-design.md`).

### Pages in scope

Dashboard (KPIs, open positions, recent trades, equity sparkline), Trades list
and Trade detail, Watchlist, Risk, Analytics, Calendar, and the shell tape and
index strip. The builder must also sweep every other route and endpoint the
SPA calls for request-time market calls (e.g. charts, research) and either
bring it into this pattern or list it in the plan as out of scope with a
reason.

## Constraints

- Postgres only for stores; any new table is an Alembic revision
  (`schema-evolution.md`).
- Every function under complexity 15 (`code-complexity.md`).
- Tests ship with every change, backend and frontend. Notably:
  - a test that **fails if a page-load handler calls any market/FX network
    function** (patch the provider entry points to raise);
  - refresher cycle tests with a fake provider;
  - in-flight mark expiry;
  - oldest-input `as_of` on totals;
  - SPA component tests for the value/age/spinner cell and for routes
    rendering without resolver data.
- The refresher must not write into the scan/backtest OHLCV caches
  (`known-traps.md`).
- Production changes (new compose service, `.env` keys) are mirrored into the
  repo (`working-conventions.md`).

## Calls made after the builder check

These are author's calls, not partner decisions. Flag any you disagree with.

- **Filtered and parameterised views** (Analytics filters, older Calendar
  months, the ~14 other Analytics routes): **not snapshotted.** They compute
  on request, but only from Postgres plus persisted FX/quote-currency codes,
  and never fetch. Only the **default** view of each page is snapshotted. The
  plan's first step on Analytics/Calendar **measures** whether persisted FX
  alone brings them under 2 s before building snapshot machinery for them.
  Snapshotting every filter combination is out of scope.
- **Provider rate limits:** while a scan is running, the refresher keeps its
  one batched Alpaca call per cycle and **skips the yfinance fallback**. Misses
  keep their last value, and their age grows. Outside scans the fallback is
  capped at a configurable number of symbols per cycle.
- **Trade detail** uses the same price/FX attach chain as the list
  (`get_trade`, `trades.py:939`) and gets the same treatment.
- **Charts** (`/equity/candles`, trade charts, anything that needs bars rather
  than quotes) are **not pre-warmed**. They load behind their existing
  skeleton or spinner after the page's DB data is on screen, as the partner
  described ("the ones needing market refreshing display later with a
  spinner"). They must not block the page or hold request threads in a way
  that stalls other calls. A display-bar cache is out of scope.
- **Bump:** the refresher process ships bot-side code, so the change bumps
  `bot patch` as well as `ui patch`. Nothing changes for an alert reader; the
  site just loads faster.

## Left to the builder

- Where the refresher process lives (separate compose service vs bot
  container), within the "never the admin worker" rule.
- Polling the delta endpoint vs SSE, as long as goal 5 holds and the poll is
  cheap.
- The snapshot table's exact shape and keys.
- Whether `follow_score` per plan on `/trades` needs caching to meet the 2 s
  target. Measure first.
- The order of work. Suggested: (1) refresher + quote/FX reads + delta
  endpoint + non-blocking routes for Dashboard/Trades/Watchlist/tape; then
  (2) heavy snapshots for Risk/Analytics/Calendar/sparkline.

## Verification

Re-run the Playwright timing script against production after deploy:

- per page, cold and warm;
- once during a scan;
- the same seven pages as the table above.

Pass means goal 6's numbers. Record the before/after table in
`docs/superpowers/results/`.
