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
  The refresher writes as a new dedicated asker, `ADMIN_REFRESH`, at **tier 5
  with the admin askers' 50 % budget reserve** (`kinds.py:58-64`,
  `budget.py:3-4`), not as tier-4 `BACKGROUND`. Admin fetching therefore
  drains the shared token bucket no deeper than it does today. The stop
  monitor and scan keep their own windows and fetch themselves whenever the
  cached quote is older than that window. Their behaviour is unchanged, so no
  separate admin namespace is needed. Regression tests pin two things:
  - a stop-monitor read still fetches when the cached quote is older than its
    window;
  - a refresher cycle at full symbol count leaves `STOP_MONITOR` and `SCAN`
    able to take budget tokens.
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

A single long-running loop in **its own process: a new `refresher` compose
service** off the same image. It is **never the admin worker and never the
bot container**, so a slow batch or a 52 s `collect_portfolio_state` can
neither stall request threads nor share `_DOWNLOAD_LOCK`
(`swingbot/core/marketdata/yf_safe.py:32`) with the scan loop and stop
monitor. Only one instance runs (Postgres advisory lock).

**Operations (the plan carries each as a task):**
- `docker-compose.yml` gives the service `cpus`/memory limits like the
  existing services, the **same daily-cache volume mounts as bot and admin**,
  and `.env` via the existing config path (SIGHUP hot reload).
- A normal deploy (`docs/deploy/DEPLOY_HETZNER.md`) starts it with no manual
  step, and that doc names it. If a manual server step turns out to be
  unavoidable, the plan re-grades `Bump:` per `working-conventions.md`
  § The three levels.
- `scripts/ops/rollback_to.sh` (`:63,87` today stops/starts only `bot admin`)
  stops the refresher before a PITR restore and starts it afterwards. New
  tables are covered by the same Alembic downgrade path.
- **Kill switch:** `ADMIN_REFRESHER=on|off` in `swingbot/config.py`. With
  `off`, request handlers fall back to today's request-time fetch paths,
  exactly as before v201, so a dead or misbehaving refresher is fixed by a
  config flip, not an image revert. The flag (and the fallback code) is
  removed by a follow-up once the refresher has run 30 days in production
  without a fallback being needed.
- **Liveness:** the refresher writes a heartbeat row each cycle. When the
  heartbeat is older than 3× the current cadence, the shell shows a
  "prices paused, refresher not running" banner and every age label takes
  the stalled style. A dead refresher can never look like a quiet market.
  `/system` health lists it beside bot and admin.

**Code placement:** the risk metrics, correlation and `_risk_bars` move out of
the Flask blueprint (`swingbot/admin/api_v1/risk.py:239-400`) into
`swingbot/core` (the analytics/portfolio package the builder picks per
`architecture.md` § Module map). The refresher and the request path call the
**same** functions; nothing is forked into a refresher copy.

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

**Daily bars for snapshots are read-only.** The risk snapshot reads bars with
`freshness.page_daily` (`swingbot/admin/freshness.py:179-189`), in a
read-only mode that never reaches the network-fetching
`data.get_daily_data_batch` branch (today taken for spot metals,
`freshness.py:184`). A symbol with no cached bars is listed as missing; it is
never fetched or written. The scan keeps the files warm, as today.

**Every snapshot records its inputs** (reproducibility, `known-traps.md`
§ The market_data cache never self-heals):
- `computed_at`;
- the oldest quote `as_of` used;
- `bars_as_of`: the newest bar date per symbol and the oldest across them;
- `missing`: symbols with no quote, no bars or no FX code;
- the ledger and trade ids it covered.

A snapshot built on bars older than the last completed session is flagged
`stale_inputs`, and the UI shows it as stale whatever its `computed_at` age.

Snapshots live in Postgres, so they survive restarts and are readable by every
worker. A new table follows `schema-evolution.md` (Alembic revision). The
file-backed `analytics_snapshot.json` (`swingbot/core/analytics/snapshots.py`)
**stays as it is**, because the Discord side reads it: the scan loop
`commands/scanning/loops.py:179-239`, `commands/stats.py`,
`commands/growth.py` and `scripts/reports/export_analytics.py`. The admin
request path stops calling `refresh_snapshot` and reads the new table
instead. Retiring the file is a later Discord-side spec, not this one
(amended after the plan brief, 2026-10-29).

**Owners and removal:** the new stores and what retires each one.

| Store | Owner | Removed when |
|---|---|---|
| snapshot table | refresher | never; it is the admin page source (`analytics_snapshot.json` stays for Discord) |
| quote-currency table | refresher (FX job) | never |
| refresh queue | request path enqueues, refresher drains | rows older than 1 h are pruned each cycle |
| in-flight marks | refresher | expire after their timeout |
| `ADMIN_REFRESHER` flag + fallback path | partner | after 30 clean days |

### 2. Request path (server)

- All page-load endpoints read quotes with the never-fetch read
  (`cached_quotes`-style). Snapshots come from the snapshot store, and
  FX/quote-currency codes from the persisted table. The "fetch if older than
  window" paths (`page_quotes`, `prefetch_prices` +
  `get_current_price` loops, `fx.quote_currency_code` network path,
  `refresh_snapshot` on request, `collect_portfolio_state` on request) are no
  longer called from request handlers.
- **Every market-derived field gets two siblings:** an `as_of` timestamp and a
  `refreshing` boolean.
- **A total also gets these:**
  - the oldest `as_of` of its inputs;
  - `refreshing` if any input is refreshing;
  - `stale_count`: inputs past the staleness threshold;
  - `missing_count`: positions with no price, no FX code or an "unknown"
    currency.

  A missing input is **never** treated as zero and never silently dropped. A
  total with `missing_count > 0` is marked incomplete, and the UI shows
  "incomplete: N positions unpriced" beside it.
- **Filtered views computed on request** (Analytics filters, older Calendar
  months) carry the same `as_of` and counts for their price/FX inputs, even
  though they have no snapshot.
- **Never-seen symbols** (e.g. a ticker added a moment ago): the value is
  `null`, `refreshing: true`, and the request **asks the refresher** for an
  out-of-cycle fetch of that symbol (a queue row or notify). It does not fetch
  itself.
- **Trades sorting by pnl/progress/R** sorts on the cached prices, so it no
  longer prices every row on request.
- **The only exception to "no fetch on request"** is an explicit user action
  that asks for a refresh. A **Refresh** control is visible on the Dashboard
  open positions, the Trades list and Trade detail, and on Risk. It enqueues a
  priority refresh for that page's symbols and snapshots and returns
  immediately, never blocking. The spinner then shows until the fresh values
  land. This replaces the "reload gives me a live price" habit before a
  decision.
- `X-Swingbot-Fresh` / `ADMIN_FRESH` no longer forces a request-time fetch. A
  reload shows cached values and the spinner covers the refresh. My call: the
  header becomes a hint that bumps the page's symbols to the front of the
  refresher's queue.
- **Live updates reuse the existing LISTEN/NOTIFY → SSE channel**
  (`notify.py`, `events.py`, `stream.py`; `architecture.md`). That channel
  carries **names only**: frames are `{seq, at}`, and `notify.CHANNELS` is a
  closed tuple. So the design follows its existing "event means refetch"
  shape:
  - one new channel name, `market` (added to `notify.CHANNELS`,
    `EventName`/`EVENT_NAMES` in the SPA, and `stream.py`), NOTIFYed once per
    refresher cycle or snapshot write that changed something;
  - on that event, the SPA calls a small **updates endpoint**
    (`GET /market/updates?since=<cursor>`). It returns only the quote and
    snapshot keys whose value or refreshing state changed since the cursor,
    is indexed by updated-at, never fetches, and also serves reconnects.

  No payload plumbing is added to the event bus, and no second push
  mechanism (amended after the plan brief, 2026-10-29).
- The refresher's heartbeat lives in its own row or table, **not**
  `bot_heartbeat`, which would raise the `bot` SSE event every cycle.
- Cadence uses `core/market/session.py` `is_regular_session` /
  `is_nyse_regular_session`, not `is_us_market_active()` (true in pre- and
  after-hours). The refresher process never sets the admin's yfinance lock
  timeout (`app.py:416`).
- `list_trades`'s existing `prices_as_of` (stamped with `datetime.now()`,
  `trades.py:1103-1107`) is replaced by the real oldest `price_as_of` of its
  rows. Rows already carry `price_age_s` and `price_as_of`.

### 3. SPA

- Remove `resolveRoute` blocking from the dashboard, trades, watchlist and
  risk routes (and any other route using it). Each page component renders at
  once. Its store kicks off its own load, and the existing `sb-async` shaped
  skeletons cover first-load emptiness. The `RouteLoadingService` veil no
  longer appears for these routes.
- Fix duplicate loads: the dashboard store loads once per navigation, and
  `/market/tape` is fetched once per poll and shared between the tape and
  market-index stores.
- A shared **live-values service** listens for the `market` event (and
  reconnects), calls the updates endpoint, and patches the returned values
  into the existing stores. Market-derived cells render through one small
  component, **extending the existing `ui/age-hint.ts`**: value, age label,
  and an `sb-spinner` beside it while `refreshing` is true. Ages tick
  client-side.
- `resolveRoute` is used by **17 routes**. All of them stop blocking.
- **Staleness thresholds are absolute times per session state**, not a count
  of cycles. These are my calls, set as config fields:

  | | Regular hours | Pre/after hours | Market closed |
  |---|---|---|---|
  | Price is stale after | 2 min | 15 min | — |
  | Risk/analytics snapshot is stale after | 10 min | 30 min | — |
  | Feed counts as stalled | heartbeat older than 3× cadence | same | same |

  Stale values take a warning style. Risk figures (heat vs account,
  drawdown, correlation) are warned at the same level as prices, never only
  prices.
- **Market closed is labelled as closed, not as stale.** A Saturday price
  reads "last close · Fri 16:00 ET", not "2 days ago" in the warning style.
  Only a stalled feed (heartbeat) or a stale value during open hours gets the
  warning. A trader can never mistake a quiet weekend for a fault, or a fault
  for a weekend.
- When the refresher reports an error for a value, the existing `sb-async`
  error style applies.
- **The Risk page labels its two clocks**: quote-based figures ("prices as of
  14:32") and bar-based ones such as beta and volatility ("daily bars through
  Oct 28 close"), so the two are never read as one timestamp.
- Stop/target proximity figures on positions carry the age of the price they
  use.
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

- The snapshot table's exact shape and keys (it must hold the recorded
  inputs above).
- Which `swingbot/core` package receives the moved risk code.
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

Pass means goal 6's numbers **and** a label check on the seven pages: every
displayed price, total, P&L and risk figure carries an as-of (or "last
close") label, and no total is shown without one. Record the before/after
table and the label check in `docs/superpowers/results/`.

Tests also pin:
- snapshot payload == the pre-v201 on-request payload for the same inputs
  (parity);
- a missing cache volume or an unreadable bar file fails the snapshot
  loudly, never as empty metrics;
- an incomplete total never sums a missing input as zero;
- `ADMIN_REFRESHER=off` restores the request-time fetch path.

## Panel review

Run 2026-10-29 on `808aa15b`, serially: staff-engineer (opus), quant-engineer
(sonnet), financial-advisor (sonnet). Every finding was applied.

**BLOCKING**
- staff-engineer: `rollback_to.sh:63,87` stops and starts only `bot admin`, so a new service would keep running through a PITR restore. -- applied (Design 1, Operations).
- staff-engineer: allowing the refresher in the bot container shares `_DOWNLOAD_LOCK` with the scan and stop monitor. -- applied (it is its own compose service only).
- quant-engineer: no source named for the risk snapshot's daily bars. -- applied (read-only `page_daily`, no network branch).
- quant-engineer: no staleness check on the bars behind snapshots. -- applied (`bars_as_of`, `stale_inputs` flag).
- financial-advisor: no "unavailable" state, so totals could silently drop unpriced or unconverted positions. -- applied (`missing_count`, incomplete label, never zero).
- financial-advisor: stale risk snapshots were not visibly different from fresh ones. -- applied (absolute snapshot thresholds, risk warned like prices).

**ADVISORY**
- staff-engineer: no kill-switch back to request-time fetches. -- applied (`ADMIN_REFRESHER` flag + heartbeat banner).
- staff-engineer: tier-4 `BACKGROUND` asker drains the shared budget deeper. -- applied (dedicated tier-5 `ADMIN_REFRESH` asker + budget test).
- staff-engineer: risk code lives in a Flask blueprint. -- applied (moves to `swingbot/core`, shared by both paths).
- staff-engineer: the delta poller duplicates the existing LISTEN/NOTIFY channel. -- applied (reuse NOTIFY; catch-up endpoint only).
- staff-engineer: the snapshot table overlaps `analytics_snapshot.json`, and new stores have no owners. -- applied (file retired; owners table).
- staff-engineer: compose limits, deploy doc, deploy auto-start. -- applied (Operations).
- staff-engineer: a manual deploy step would change the bump. -- applied (plan re-grades if so).
- quant-engineer: the refresher must mount the same daily-cache volume. -- applied (Operations + loud-failure test).
- quant-engineer: snapshot must reuse the request-path functions. -- applied (no fork; parity test).
- quant-engineer: record snapshot inputs. -- applied.
- quant-engineer: null prices in totals. -- applied (merged with financial-advisor blocking 1).
- quant-engineer: label quote vs daily-bar clocks on Risk. -- applied.
- financial-advisor: show the count of stale inputs, not only the oldest age. -- applied (`stale_count`).
- financial-advisor: distinguish market closed from a stalled feed. -- applied.
- financial-advisor: a reload no longer forces a live price. -- applied (visible Refresh control, ages on stop/target proximity).
- financial-advisor: filtered views need as-of labels too. -- applied.
- financial-advisor: thresholds counted in cycles mean different things per session. -- applied (absolute per session state).
- financial-advisor: verification only checks load time. -- applied (label check added).
