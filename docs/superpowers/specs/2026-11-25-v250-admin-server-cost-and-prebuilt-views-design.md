# v250 — Admin server: cut per-request cost, then exact prebuilt views

**Version:** ui 1.49.0 · bot 2.19.10
**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer, senior-engineer

`Edge: none (integrity)`: no entry, exit, stop, sizing or alert rule changes,
and no figure changes meaning. `Bump: bot patch`: the admin API answers the
same bodies faster; the one visible difference is the confidence bands of
variance-band and cancel-precision being re-drawn once (see Design A3). The
SPA is untouched.

Panel: the infra default (staff-engineer, quant-engineer) plus
senior-engineer for the request-path refactors. quant-engineer covers the
resampling rewrite and reproducibility.

## Why

Brainstorm with the partner, 2026-11-25 (same session as v249). The partner's
pains: the same data on many pages, slow pages, a painful phone. v249 (client
data layer) was specified first, then the production baseline in v249 §
Baseline showed first loads are **server-bound**: `/analytics/performance`
20.8 s median, `variance-band` 17.2 s, `cancel-precision` 17.1 s,
`override-fidelity` 13.9 s, `equity-curve` 12.3 s, `by-dimension` 7.0 s,
`/equity/candles` 6.7 s, `/dashboard` 5.8 s (p90 14.6 s) and polled 5–6 times
a minute; bodies are 1–32 KB. The partner then put **this spec before
v249**.

Partner decisions (2026-11-25):

- Figures stay **exact**: a stored answer is reused only while the data it
  was built from is unchanged, and the server **rebuilds the common views
  right after a change**, so the next view is usually already fast.
- Build order: **cost fixes first, then refresher-built views**.
- Faster resampling may re-draw the confidence bands once (third-decimal
  shifts); means, ExpR and win rate must not change.

### Where the time goes (read-only code survey, 2026-11-25)

Mostly Python CPU on the single gunicorn worker's GIL
(`deploy/gunicorn.conf.py`: one worker, 16 threads), not the database:

1. **No read memo on the slow routes.** `@read_scope` is on six views only
   (`/dashboard`, `/trades`, `/live`, the three calendar views —
   `tests/admin_perf/test_read_scope_routes.py`). `store_snapshot.read`
   requires an active read memo (`core/infra/store_snapshot.py`), so every
   `TradeLog._all()` / `PlanStore` call on an analytics route re-loads and
   re-parses the whole table. v205 measured ~1 ms per trade and ~3 ms per
   plan. `performance_body` (`core/analytics/page_bodies.py`) loads the trade
   table about **8 times** per request (`_all_trades`, `weak_summary`,
   `get_stats_by_confidence` ×5, `_closed_tickers`).
2. **10,000-draw bootstraps in pure-Python loops.** `variance_band`
   (10,000 numpy paths plus 200×1,000 nested, per horizon 20 and 50, plus
   `stats.week_cluster_bootstrap`) and `cancel_precision.figure()` (two
   10,000-draw bootstraps per call, called for the headline, baseline, every
   card and every split).
3. **Quadratic plan loads.** `/analytics/by-dimension?dim=strategy` calls
   `_soak_for` per strategy row (`admin/api_v1/analytics.py`), each a full
   `PlanStore().all()`.
4. **No single-flight** on cancel-precision's memo (`api_v1/cancel_precision.py`)
   or any analytics body: concurrent misses each compute, and a page boot
   fires several at once.

### What already exists and is reused

- `admin_snapshots` builders (`core/analytics/admin_snapshots.py`) written by the
  refresher (`refresher/snapshot_job.py`): `analytics.performance:{main,weak,both}`
  and `analytics.equity_curve:*`, rebuilt on cadence, on a trades
  `(count, max(updated_at))` change, or after a scan; compare-and-set writes,
  90 s build budget; read only for the ledger-only scope
  (`admin/api_v1/analytics.py` `default_view_body`). **This is the template
  this spec generalises.**
- `conditional.py` weak ETag/304 (inputs: build, generations, versions, fx
  version, query, Berlin date, principal), used only by `GET /trades`.
- `/risk`'s per-key-lock single-flight TTL (`admin/api_v1/risk.py`): the
  shape for a generic single-flight.
- Change signals: statement-level `pg_notify` triggers (`core/db/events.py`)
  on `trades` (tables trades, plans, starred_plans, manual_close_notify),
  `account`, `journal`; `snapshot_listener` LISTENs on `trades`/`journal`
  and bumps `store_generation`. **Caveat:** the `trades` channel fires on
  every plan requote during a scan and on near-TP snapshot writes
  (`performance.py`), so a key on the generation alone would invalidate
  constantly.

v205's Non-goals ruled out "precomputed payloads in the refresher" because
numbers could drift from the live book. This spec keeps that guarantee a
different way: a stored view is served **only when its fingerprint equals
the live fingerprint**, so it is the same answer the request would compute.

## Goals

1. Each slow route loads each table at most once per request.
2. Cold (no stored view) server time on production, off-hours, median of 3:
   `/analytics/performance` and `/dashboard` under 2 s, every other
   endpoint named in § Why under 4 s. Measured before and after Phase A per
   endpoint (Server-Timing / probe), recorded in this spec. A target, not a
   gate: Phase B proceeds either way, and a miss is recorded with its
   profile.
3. With Phase B, a view whose fingerprint is unchanged is served from storage
   with server time under 200 ms; the Analytics and Dashboard cold page loads
   measured with v249's baseline script reach content in under 1 s.
4. After a change to the closed book, the refresher has rebuilt every
   prebuilt view within 2 minutes (one rebuild per change burst).
5. Means, ExpR, win rate, counts and every non-resampled figure are
   byte-identical before and after; resampled band edges stay within the
   tolerance stated in A3.

## Non-goals

- No client change (v249) and no layout or content change (project 3).
- No change to `/risk`, `/live`, `/trades` or the calendar routes beyond
  Phase A's read memo where missing.
- No new infrastructure (no Redis, no second admin worker).
- Live figures — open P&L, `market_meta`, today's FX, `/risk` — are never
  prebuilt; they are computed per request and laid over the stored part.

## Anti-goals

- **A stored answer that differs from what the request would compute.** The
  fingerprint must change whenever any input of the view changes; a view
  whose inputs the fingerprint does not cover is not prebuilt.
- **Rebuild storms.** A scan's requote churn must not trigger rebuilds; a
  burst of closes triggers one rebuild after it settles.
- **Rebuilds starving the scan.** The refresher's rebuild runs at low
  priority within its existing build budget and never blocks the bot.

## Design

# Phase A — cut the per-request cost

### A1. One load per request

Every analytics route, `/equity/candles`, `cancel-precision`,
`override-fidelity`, `variance-band` and `by-dimension` gains `@read_scope`,
and `tests/admin_perf/test_read_scope_routes.py` pins the full list. A
route-coverage test fails any new `/analytics/*` GET without it.

### A2. No per-strategy plan reload

`_soak_for` takes the plan list loaded once by the handler (or reads it
through the request memo); the by-dimension strategy view loads plans once.
Test: a counting fake `PlanStore` sees one load for N strategies.

### A3. Vectorised resampling, fixed seed

`stats.week_cluster_bootstrap`, `variance_band`'s nested paths and
`cancel_precision`'s bootstrap are rewritten with numpy (`Generator` with a
fixed seed per call site), producing reproducible results run to run.
Tolerance test on a frozen fixture book: every band edge within
`max(0.01 R, 2 % of the band width)` of the pre-change value. "Point
estimates byte-identical" means the **sample** statistics computed from the
trades (mean, median, ExpR, win rate), not bootstrap medians, which move with
the draws. If a band misses the tolerance, raise that call site's draw count
(at most 4×, still far faster than the loop); if it still misses, keep the
old loop for that call site and record why. The release note says the bands
were re-drawn once.

### A4. Single-flight

A small generic single-flight (generalised from `/risk`'s per-key lock) wraps
every analytics body build and cancel-precision's memo: concurrent requests
for the same key wait for one build.

### A5. Profile before and after

Before A1–A4 land, a per-endpoint server-time profile is taken on production
off-hours (read-only, through `scripts/ops/ssh-hetzner.sh`) and recorded
here; it is re-taken after Phase A. This closes v206's unbuilt "Plan 4:
analytics outliers, profiling first" for the endpoints in § Why.

# Phase B — exact prebuilt views

### B1. Fingerprints

A fingerprint is a short hash over exactly the inputs of a view:

- **closed book**: for trades whose status is not open, a hash of
  `(id, status, closed_at, exit fields, R, P&L, ledger fields)` computed in
  SQL (e.g. `md5(string_agg(... ORDER BY id))`), plus `count`. Scan
  requotes of open plans do not change it. `updated_at` alone is not used
  (V218-1: a commit can land under an older stamp).
- **terminal plans**: the same over the plan columns a view reads, for
  plans in a terminal state (cancelled, closed, expired) only. Scan requotes
  rewrite live plans and must not change it. A view that needs live plans is
  not prebuilt (see B2).
- **journal**: `count` plus a hash over journal entry ids and their edited
  fields, for exit-quality.
- **account & config**: a hash of `base_balance` and of each config
  threshold a view reads, for views that read them.
- **fx**: `fx_daily` version, for views converting currency.
- **daily bars**: a new signature built from the bar files' names and
  mtimes on the shared mount (`daily_delta.read_daily` has no memo key
  today), so a new bar day rebuilds cancel-precision. It replaces that
  memo's UTC-hour component.
- **scope**: the resolved `BookScope` and, for relative presets
  (30d/90d/ytd), the Berlin date.

**Clock-dependent fields.** A body field that depends on the clock rather
than the inputs (`generated_at`, an `asof`) is either moved into the live
overlay or, for `generated_at`, set to the stored row's build time, which
is the honest time the figures were computed. The B3 byte-equality test
compares bodies with `generated_at` alone excluded.

**Open-state fields.** `performance_body`'s `totals.open` and the
Dashboard's lifecycle counts (PENDING/ACTIVE/PARTIAL) are open state. They
move into the live overlay, computed per request from the request-memoised
load (cheap counts), never stored.

Each view declares which fingerprints it depends on; a test per view
asserts that mutating each declared input changes the key and that mutating
an undeclared input does not change the body (the coverage check behind the
first anti-goal). The live fingerprint is computed once per request inside
the read scope (one cheap SQL query each).

### B2. What the refresher prebuilds

Generalising `admin_snapshots.builders`:

- `analytics.performance` and `analytics.equity_curve` for ledger
  `main`/`weak`/`both` × scope `all`/`30d`/`90d`/`ytd`;
- `analytics.by-dimension` for `strategy`, `horizon`, `direction`, `dow`,
  plus `heat-grid` and `strategies`, at the default scope;
- `variance-band`, `cancel-precision`, `calibration`, `exit-quality`;
- the Dashboard's ledger blocks: stats, extended stats, realized, R
  multiples, 30-day equity (lifecycle counts are live overlay, B1).

**Not prebuilt** (inputs outside B1, or live plans): `partials` (its scope
can include live plans) and `override-fidelity` (reads `override_io` inputs,
the verdict table and an `asof`). Both keep Phase A's request path with
single-flight; if their after-Phase-A profile misses Goal 2, a follow-up
adds their fingerprints. (Author's call after the builder check.)

**Trigger: polling, no new LISTEN.** The refresher has no LISTEN connection
today (`refresher/snapshot_job.py` polls `count(*), max(updated_at)` each
cycle). It keeps polling, but polls the B1 fingerprints instead, every
cycle; a changed fingerprint rebuilds the views that depend on it. Polling
is enough for Goal 4 (rebuilt within 2 minutes) as long as the cycle is at
most ~60 s; the plan verifies the production cycle length and, if longer,
adds a fingerprint poll at that cadence. A burst of closes inside one cycle
rebuilds once. The existing cadence stays as a safety net. Each row stores
its fingerprint; writes stay compare-and-set.

### B3. How the admin reads

For a request whose scope matches a prebuilt key: compute the live
fingerprint; if it equals the stored row's, serve the stored body (plus any
live overlay); otherwise compute on request (Phase A path, single-flight)
and return that. A miss is counted in the existing probe so a view that keeps
missing is visible. The Dashboard composes its stored ledger blocks with
per-request open P&L, `market_meta` and today's FX.

### B4. 304 replies

`conditional.py` covers the prebuilt routes, with the view's fingerprint in
place of the generation inputs, so a browser re-request of an unchanged view
gets a 304. (v249's background refreshes rely on this.) Routes with a live
overlay (Dashboard) include the overlay's inputs (quote cache version, FX)
in the tag, or are excluded — builder's call, documented per route.

### B5. Equity candles

`/equity/candles` memoises its candle build keyed on
`(max(equity_samples.id), tf, basis, limit, before)`; `as_of` and
`fill_flat(now)` are applied per request after the memo. `equity_samples`
has no NOTIFY trigger; the `max(id)` read is the key.

## Ops

- Refresher builds run in the refresher container, never the admin
  process; the 90 s build budget per row stays, with a log line per build
  (`view`, `ms`, `fingerprint`).
- Rollback: the stored-view read is behind a switch
  (`ADMIN_PREBUILT_VIEWS=on|off`, default `on`, hot-reloaded via SIGHUP);
  `off` falls back to the Phase A request path. Phase A needs no switch; it
  rolls back with the image.
- New `.env` key ships in `.env.example` and `swingbot/config.py`; any change
  made on production is mirrored back per `mirror-prod`.

## Testing

- A1: route list pinned; counting fakes show one load per table per request.
- A2: one plan load for N strategies.
- A3: tolerance test on a frozen book; point estimates byte-identical;
  same seed → same output twice.
- A4: two concurrent requests, one build.
- B1: per view, each declared input changes the fingerprint; scan requote of
  an open plan does not change the closed-book fingerprint.
- B2: a close triggers one rebuild after the settle window; a requote burst
  triggers none; compare-and-set holds under two writers.
- B3: matching fingerprint → stored body byte-equal to the request-computed
  body; mismatch → computed path; Dashboard composition equals today's body
  for the same inputs.
- B4: 304 on unchanged, 200 after a change.
- B5: memo hit with a new `now` changes only `as_of`/flat fill.
- Golden bodies under `tests/admin_perf/golden/` stay byte-identical except
  the documented band edges.
- Every changed function under complexity 15 (`code-complexity.md`); new
  tests join existing suites (`testing-cost.md` § Test suites).

## Measurement

Phase A: per-endpoint server-time profile before and after (A5). Phase B:
v249's Playwright baseline script, off-hours, read-only, after deploy; its
numbers become v249's new "before" baseline (v249 § 7, Ops and ownership).

## What follows

v249 (client data layer) is re-baselined against this spec's after-numbers
and then planned; project 3 (Dashboard "right now" vs Trades history)
follows.
