# v204 — Admin snapshot pages: Risk, Analytics, Calendar and the equity sparkline from stored snapshots

**Version:** ui 1.37.2 · bot 2.15.7
**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer, financial-advisor
**Depends on:** v201

## Why

This is the second half of v201 (`2026-10-29-v201-instant-admin-page-loads.md`).
Its plan came out at 21 tasks, over the 20-task cap, and the partner chose to
cut it into **prices first** (v201) and **snapshots later** (this spec). v204
starts once v201 is merged: it reuses v201's `refresher` service, in-flight
marks, `market` event, `/market/updates` endpoint, Refresh control,
value/age/spinner cells, heartbeat and kill switch.

The measurements and root causes are in v201 § Why ("Measured on production,
2026-10-29" and "Root causes"). The pages this spec owns were the worst of
that run: **Risk, Analytics and Calendar all timed out at 30 s**
(`/analytics/equity-curve` took 47.5 s; `GET /risk`, `/analytics/performance`
and `/calendar/pnl` failed at 30 s). Root cause 1 names the mechanisms:
`get_risk` runs `collect_portfolio_state` on request (4.1 s quiet, up to 52 s
under a scan, plus daily bars for metrics/correlation), and `_equity_30d`
rebuilds `refresh_snapshot()` synchronously and returns `None` to the request
that rebuilt it, so the sparkline comes back empty.

## What the partner decided

- **Heavy computed pages (Risk, Analytics, the dashboard equity sparkline,
  Calendar P&L) follow the same pattern as prices.** The background job
  recomputes and stores a snapshot. **The page shows the last snapshot
  instantly, with its age and the same spinner while a recompute runs.**
- **Success target: data visible in under 2 s** on every main page.

## Goals

1. Risk, Analytics, Calendar and the dashboard equity sparkline answer from
   Postgres, stored snapshots and v201's persisted quote/FX caches only. **No
   request thread makes a market-data, FX or daily-bar network call** for
   them, apart from v201's explicit Refresh action.
2. v201's refresher gains a **snapshot job** that computes and stores those
   snapshots, recording their inputs.
3. Every snapshot figure carries **when it was computed**, the age of its
   **oldest input**, whether it is **refreshing**, and whether its inputs are
   **stale** or **missing**, so the UI can draw the age, the spinner and the
   warning.
4. Production, measured with v201's Playwright timing script: on Risk,
   Analytics and Calendar (and the dashboard sparkline), **first data visible
   ≤ 2 s** after the click, cold and warm, **including while a scan is
   running**. Every page-load API call of those pages ≤ 2 s. `/system/scan`
   stays ≤ 0.5 s throughout.

## Non-goals

- Everything v201 delivers (refresher service, `ADMIN_REFRESH` asker, quote
  and FX persistence, the price request path, `market` event, non-blocking
  routes, kill switch, heartbeat, ops) is not redone here; this spec only
  extends it.
- Discord alerts, the scan pipeline, plan building, backtests: untouched. The
  snapshot job must not write into the OHLCV/daily-bar caches the scan and
  backtests read.
- **`analytics_snapshot.json` is not retired.** The Discord side reads it;
  retiring it is a later Discord-side spec.
- Snapshotting every Analytics filter combination or every Calendar month.
- No redesign of any page's layout. Only loading states, age labels, spinners
  and the clock labels below change.

## Anti-goals (it fails even if it "works")

- **A risk figure shown without its age**, or a stale snapshot that looks
  fresh. A snapshot built on old bars must look stale whatever its
  `computed_at`.
- **A snapshot that fails quietly.** A missing cache volume or an unreadable
  bar file must fail the snapshot loudly, never produce empty metrics that
  render as a calm zero.
- **A forked copy of the risk maths.** The snapshot and any remaining request
  path call the same functions; a snapshot that drifts from the on-request
  payload is a bug.
- **Moving the jam instead of removing it.** `collect_portfolio_state` runs in
  the refresher process, never in the admin worker.

## Design

### 1. Snapshot job (server)

**Code placement.** The risk metrics, correlation and `_risk_bars` move out of
the Flask blueprint (`swingbot/admin/api_v1/risk.py:239-400`) into
`swingbot/core`. Plan-brief finding: `risk_read_model.py` moves to
`swingbot/core/analytics`, with a re-export left at its admin path so existing
imports keep working. The refresher and the request path call the **same**
functions; nothing is forked into a refresher copy.

**The snapshot job in the refresher.** After each quote cycle, and after each
scan completes, it recomputes and stores:
- the risk payload (`collect_portfolio_state` and its metrics/correlation);
- analytics performance and the equity curve per ledger;
- the dashboard equity sparkline;
- calendar P&L for the current and previous month.

My call: heavy snapshots at most every 5 min during market hours unless a
trade opened or closed. Before recomputing a snapshot it sets v201's in-flight
mark for that snapshot key (same expiry rule, so a crash never leaves a
permanent spinner) and clears it when done.

**Events.** A snapshot cycle may raise up to **three `market` events**: one
when the in-flight marks are set, one when the quote values land, and one when
the snapshot lands. `/market/updates?since=<cursor>` returns snapshot keys as
well as quote keys whose value or refreshing state changed since the cursor.

**Daily bars for snapshots are read-only.** The risk snapshot reads bars with
`freshness.page_daily` (`swingbot/admin/freshness.py:179-189`), in a new
read-only mode that never reaches the network-fetching
`data.get_daily_data_batch` branch (today taken for spot metals,
`freshness.py:184`). `collect_portfolio_state` gains a read-only bars reader
for the same purpose. A symbol with no cached bars is listed as missing; it is
never fetched or written. **Spot metals are therefore listed as missing in
read-only mode.** The scan keeps the files warm, as today.

**Every snapshot records its inputs** (reproducibility, `known-traps.md`
§ The market_data cache never self-heals):
- `computed_at`;
- the oldest quote `as_of` used;
- `bars_as_of`: the newest bar date per symbol and the oldest across them;
- `missing`: symbols with no quote, no bars or no FX code;
- the ledger and trade ids it covered.

A snapshot built on bars older than the last completed session is flagged
`stale_inputs`, and the UI shows it as stale whatever its `computed_at` age.

**Snapshot table.** Snapshots live in Postgres, so they survive restarts and
are readable by every worker. A new table follows `schema-evolution.md`
(Alembic revision). The file-backed `analytics_snapshot.json`
(`swingbot/core/analytics/snapshots.py`) **stays as it is**, because the
Discord side reads it: the scan loop `commands/scanning/loops.py:179-239`,
`commands/stats.py`, `commands/growth.py` and
`scripts/reports/export_analytics.py`. The admin request path stops calling
`refresh_snapshot` and reads the new table instead.

| Store | Owner | Removed when |
|---|---|---|
| snapshot table | refresher | never; it is the admin page source (`analytics_snapshot.json` stays for Discord) |

### 2. Request path (server)

- Risk, Analytics (default view), Calendar (current and previous month) and
  the dashboard sparkline read from the snapshot table. `refresh_snapshot`
  and `collect_portfolio_state` are no longer called from request handlers.
- Every snapshot figure carries v201's siblings (`as_of`, `refreshing`) plus
  the recorded inputs above; totals carry `stale_count` and `missing_count`
  as in v201. A missing input is never treated as zero.
- **Filtered and parameterised views** (Analytics filters, older Calendar
  months, the ~14 other Analytics routes): **not snapshotted.** They compute
  on request, but only from Postgres plus persisted FX/quote-currency codes,
  and never fetch. Only the **default** view of each page is snapshotted. The
  plan's first step on Analytics/Calendar **measures** whether persisted FX
  alone brings them under 2 s before building snapshot machinery for them.
  Filtered views carry the same `as_of` and counts for their price/FX inputs,
  even though they have no snapshot.
- **The Refresh control** (v201's) is added to Risk. It enqueues a priority
  refresh for the page's symbols and its snapshot and returns immediately,
  never blocking; the spinner shows until the fresh snapshot lands.

### 3. SPA

- **Snapshot staleness thresholds** are absolute times per session state, a
  new row beside v201's price row (config fields; my calls):

  | | Regular hours | Pre/after hours | Market closed |
  |---|---|---|---|
  | Risk/analytics snapshot is stale after | 10 min | 30 min | built before the last regular close, or `stale_inputs` |

  Risk figures (heat vs account, drawdown, correlation) are warned at the same
  level as prices, never only prices. `stale_inputs` shows as stale
  regardless of age.
- **The Risk page labels its two clocks**: quote-based figures ("prices as of
  14:32") and bar-based ones such as beta and volatility ("daily bars through
  Oct 28 close"), so the two are never read as one timestamp.
- Snapshot values render through v201's value/age/spinner cell; the live-values
  service patches snapshot keys from `/market/updates` into the Risk,
  Analytics, Calendar and dashboard stores.
- Mobile, tablet and desktop: labels and spinners wrap under the value on
  narrow widths and never widen table columns (per `ui-design.md`).

### Pages in scope

Risk, Analytics, Calendar, and the dashboard equity sparkline.

## Constraints

- Postgres only for stores; the snapshot table is an Alembic revision
  (`schema-evolution.md`).
- Every function under complexity 15 (`code-complexity.md`); the risk code
  move is behaviour-preserving.
- Tests ship with every change, backend and frontend. Notably:
  - **parity:** snapshot payload == the pre-v201 on-request payload for the
    same inputs;
  - **loud failure:** a missing cache volume or an unreadable bar file fails
    the snapshot loudly, never as empty metrics;
  - read-only `page_daily` and the read-only bars reader never call the
    network branch (spot metals come back as missing);
  - `stale_inputs` set when bars are older than the last completed session;
  - snapshot in-flight marks and the three `market` events per cycle;
  - a test that fails if a Risk/Analytics/Calendar page-load handler calls
    any market/FX/bar network function;
  - SPA tests for the two-clocks labels and snapshot staleness styles.
- The snapshot job must not write into the scan/backtest OHLCV caches
  (`known-traps.md`).
- Production changes are mirrored into the repo (`working-conventions.md`).

## Left to the builder

- The snapshot table's exact shape and keys (it must hold the recorded inputs
  above).
- Whether Analytics/Calendar need snapshot machinery at all after the
  measure-first step.

## Verification

Re-run v201's Playwright timing script against production after deploy:

- Risk, Analytics, Calendar and the dashboard (sparkline), cold and warm;
- once during a scan.

Pass means goal 4's numbers **and** a label check on those pages: every
displayed total, P&L and risk figure carries an as-of (or "last close")
label, Risk shows both clocks, and filtered views carry their as-of labels.
Record the before/after table and the label check in
`docs/superpowers/results/`.

## Panel review

Inherited from v201's panel (run 2026-10-29 on `808aa15b`), whose snapshot
findings are applied above: read-only bars source, `bars_as_of` /
`stale_inputs`, absolute snapshot thresholds with risk warned like prices,
no forked risk code (parity test), loud failure on a missing volume, recorded
inputs, Risk's two clocks, filtered-view as-of labels. This spec gets its own
`/panel` run.

## Panel amendments

These resolve the staff-engineer findings below. Where they conflict with
earlier text in this spec, they win.

- **Kill switch for these pages.** `ADMIN_REFRESHER=off` keeps today's
  request-time compute path for Risk, Analytics, Calendar and the sparkline
  (`collect_portfolio_state`, `refresh_snapshot`) behind the flag, pinned by a
  test, exactly as v201 does for prices. A dead refresher is therefore fixed
  by a config flip, not an image revert. The fallback is removed together
  with v201's after 30 clean days.
- **Snapshots never stall prices.** The snapshot job runs on its own worker
  thread inside the refresher process, on its own cadence. It never runs
  inline in the quote cycle. The cycle hands it work and moves on. Each
  snapshot build has a time budget (config field). A build that overruns is
  abandoned, its mark is cleared with an error, and it retries next cadence.
- **The read-only bars reader lives in `swingbot/core`**, next to the moved
  risk code, not in `swingbot/admin/freshness.py`. No new core→admin import is
  added. `freshness.page_daily` delegates to it.
- **`analytics_snapshot.json` stays, which reverses v201's "file retired"
  outcome** because the Discord side reads it (see v201 § Panel review). A
  parity test pins that the figures both producers compute (performance
  totals and the equity curve per ledger) agree for the same trades.
- **Retention:** the snapshot table holds one row per key, upserted, so it
  never grows with time. Keys for months older than the previous month are
  not snapshotted.
- **Guard test coverage** names every request-time `refresh_snapshot` caller:
  `swingbot/admin/api_v1/analytics.py:41-43`, `swingbot/admin/dashboard.py:57`
  **and** `swingbot/admin/queries.py:209`.
- **Rollback:** the Alembic downgrade drops the snapshot table. v201's
  `rollback_to.sh` refresher stop/start already covers the process.

The quant-engineer and financial-advisor findings add the following:

- **Recorded inputs, extended.** Beyond the list in Design 1, each snapshot
  records the quote price and `as_of` per symbol, the FX rate and its `as_of`
  per currency, a bar-file fingerprint per symbol (path, mtime, last-bar
  date, row count), the staleness thresholds in force, and the code version
  (`VERSION.json` bot version). That is enough to audit a figure after the
  caches have moved on. Reproduction is exact only while those bar files are
  unchanged; that limit is stated, not hidden.
- **"Last completed session" has one source.** `stale_inputs` compares each
  symbol's newest bar date with `session.last_regular_close(now)` (v201's
  V201-1, UTC-aware, NYSE calendar from `session.NYSE_HOLIDAYS`), converted
  to its ET session date. Tests cover a Monday morning, a holiday, a
  Saturday, and the 16:00–20:00 ET window before the scan updates the daily
  file (there the previous session counts as complete, so the snapshot is
  not flagged before the file has had a chance to update). Half days use
  the same close-date rule. Non-US tickers use the same NYSE-date rule. That
  is a known simplification, so the bars clock on Risk shows each symbol's
  own last-bar date. Spot metals are excluded from `stale_inputs` and counted
  under `missing` only.
- **The bars cache is pinned.** The read-only reader reads only the
  yfinance-basis shared daily file (`daily_delta.read_daily(ticker,
  basis=BASIS_YF)`, which `freshness._read_yf` reads today). It never reads
  `data/backtest_cache/` (`backtest_cache.cache_path`). A file that fails to
  parse, is empty, or has fewer rows than the metric's window lists the
  symbol under `missing` with a reason. It never returns a short frame as if
  it were whole. Tests pin both points.
- **Parity is pinned to frozen fixtures.** Before the risk code moves, the
  first task records golden payloads (risk, performance, equity curve,
  calendar month, sparkline) from the current on-request code over a fixed
  fixture book. The parity tests compare against those files, not against
  code that moves with the change.
- **Writes are ordered.** The snapshot upsert writes only when the incoming
  `computed_at` is newer than the stored row's (compare-and-set in the
  `ON CONFLICT ... WHERE` clause). A build abandoned on budget overrun that
  finishes late can therefore never land over a newer row. A test pins this.
- **Partial books are labelled, never zeroed.** A position with no quote, no
  FX code or no bars is left out of heat, drawdown and P&L totals, and is
  counted in `missing_count`. Each affected total is marked as a lower bound
  ("≥ $X, 1 position unpriced"), not shown as a complete figure. Correlation
  with fewer than 2 overlapping bars and beta with zero variance come back as
  `null` with a reason, never `NaN` or 0. Edge-case tests cover each. An open
  spot-metal position's heat therefore shows as "unknown" in read-only mode,
  and the heat total carries the lower-bound label.
- **Market closed is not exempt.** While the market is closed, a snapshot
  built before the last regular close, or one carrying `stale_inputs`, shows
  as stale. A current one shows "as of last close · Ddd HH:MM ET" (the
  threshold table in SPA reflects this).
- **Headline figures say what they are.** Calendar P&L, the Analytics totals
  and the Risk P&L figures carry a short "pre-tax" label. They also say
  whether modelled frictions are included, worded from what the ledger
  actually stores (the plan reads this from the code; it is not assumed).
  Heat and drawdown are shown against the account (percent of account plus
  dollars) wherever the existing payload has the account value. The
  verification label check covers both.
- **No extra notification volume.** The snapshot job and its `market` events
  feed the admin SPA only. They add no Discord message, alert or push
  notification. This is a non-goal, pinned by a test that the snapshot job
  never touches the Discord send path.
- **Verification records its inputs.** The results document records, per
  pass, the commit and versions deployed, the scan state, and the snapshot's
  `bars_as_of` and `computed_at` at probe time.

## Panel review

Serial run on `21a89358`: staff-engineer (opus), then quant-engineer (sonnet)
and financial-advisor (sonnet) on `9c45125e`, 2026-10-30.

- staff-engineer [BLOCKING]: `ADMIN_REFRESHER=off` left four pages with no fallback. -- applied (Panel amendments, kill switch).
- staff-engineer [ADVISORY]: a 52 s snapshot inside the single loop stalls quotes. -- applied (own worker thread + time budget).
- staff-engineer [ADVISORY]: `page_daily` adds a core→admin import. -- applied (reader moves to core).
- staff-engineer [ADVISORY]: two producers of the same analytics with no agreement check; reverses v201's outcome. -- applied (parity test; reversal recorded).
- staff-engineer [ADVISORY]: no retention rule for the snapshot table. -- applied (upsert by key).
- staff-engineer [ADVISORY]: `queries.py:209` missing from the guard list. -- applied.
- staff-engineer [ADVISORY]: downgrade and rollback coverage not restated. -- applied.
- quant-engineer [BLOCKING]: recorded inputs omit quote prices, FX rates, bar-file identity, thresholds and code version. -- applied (recorded inputs, extended; reproduction limit stated).
- quant-engineer [BLOCKING]: "last completed session" is undefined (calendar, timezone, non-US, metals). -- applied (one source: `session.last_regular_close`, with the listed tests).
- quant-engineer [BLOCKING]: the bars reader's cache is not pinned, and truncated files are not detected. -- applied (yfinance-basis shared file only, never `backtest_cache`; short frame goes to `missing`).
- quant-engineer [ADVISORY]: parity is not pinned to frozen output. -- applied (golden payloads recorded before the move).
- quant-engineer [ADVISORY]: no write-ordering rule for the upsert. -- applied (newer `computed_at` wins, compare-and-set).
- quant-engineer [ADVISORY]: no `NaN`/`None`/zero edge tests for totals, correlation and beta. -- applied (partial books labelled; `null` with a reason).
- quant-engineer [ADVISORY]: the verification run does not record its inputs. -- applied.
- financial-advisor [BLOCKING]: snapshots never read stale while the market is closed. -- applied (market closed is not exempt; threshold table changed).
- financial-advisor [BLOCKING]: the label check omits pre-tax/frictions and heat against the account. -- applied (headline figures say what they are; the check covers it).
- financial-advisor [ADVISORY]: drawdown should be in account dollars and show the losing streak. -- applied in part: dollars beside percent where the payload already has the account value. Rejected for new metrics (the losing streak): the parity rule and the no-redesign non-goal keep the payload as it is; this belongs in a later Risk-page spec.
- financial-advisor [ADVISORY]: spot metals are always missing, so heat understates exposure. -- applied (heat "unknown", total labelled as a lower bound).
- financial-advisor [ADVISORY]: no statement that the job adds no notification volume. -- applied (non-goal plus test).
- financial-advisor [ADVISORY]: no concentration view on Risk. -- rejected: a new view is a layout change (non-goal). The existing correlation figure stays in the snapshot payload unchanged; a sector or top-name view belongs in a later Risk-page spec.

## Handoff

Paused 2026-10-29 because the account's weekly usage limit was nearly spent.
The panel is complete (2026-10-30). Resume in this order:

1. ~~Run `/panel quant-engineer,financial-advisor`~~ -- done.
2. Write the v204 plan: `plan-briefer`, then `plan-writer` `mode=index`, then
   the parts. Reuse the drafts already written for the pre-split v201 plan,
   kept in the shared tree at `.superpowers/drafts/v204/` (gitignored):
   - `old-V201-12-risk-move.md`: risk move to core, read-only bars;
   - `old-V201-13-snapshot-job.md`: snapshot job and routes, 28.6 KB, so
     split it in two;
   - `old-part4-with-V201-18.md` § V201-18: SPA Risk/Analytics/Calendar
     labels;
   - `prod-timing-probe.js`: the bounded Playwright timing probe.

   The panel amendments above override those drafts: snapshot worker thread,
   bars reader in core, kill-switch fallback, parity test, upsert.
3. Also add what v201 left for v204 (see v201 plan index, contracts):
   - the snapshot config fields and `stale_after_s("snapshot")`;
   - the snapshot key patterns;
   - the `snapshots` field on `/market/updates` and on refresh;
   - the snapshot table with its repository;
   - the sparkline label (V201-17 dropped it).
