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

### B6. Rules added by the panel review

These rules override B1–B5 where they differ.

**Storage and ownership**
- The fingerprint is stored **inside the existing `admin_snapshots.inputs`
  JSONB** (`core/db/schema.py`), under a `fingerprint` key. No new column,
  no Alembic revision, nothing to order on rollback. (staff-engineer 1,
  BLOCKING)
- The fingerprint functions and the view registry (key → builder, declared
  inputs) live in `swingbot/core/analytics/` beside `admin_snapshots.py`.
  Both `refresher/snapshot_job.py` and `admin/api_v1` import them from
  there; nothing in `core` imports `admin` or `refresher`.

**Fingerprint inputs**
- The **trades** fingerprint hashes the whole `doc` of every trade whose
  status is neither PENDING nor ACTIVE (closed, cancelled and PARTIAL), not
  a hand-picked field list. PARTIAL is included because the Dashboard's
  realized block counts partial exits. The plan first measures whether
  PARTIAL docs churn during a scan (near-TP snapshot writes); if they do,
  the realized block moves to the live overlay instead and PARTIAL leaves
  the hash.
- **Daily bars** (quant-engineer 1, BLOCKING): the signature covers exactly
  the files cancel-precision reads: for each ticker in its plans,
  `cache_file(ticker, basis_for(ticker))` **and** its `.meta.json` sidecar
  (`core/marketdata/daily_delta.py`), each as `(name, mtime_ns, size)`, plus
  the resolved basis per ticker, so an `ALPACA_ENABLED` flip changes it. The
  plan confirms every bar write moves `mtime_ns`.
- The **refresher computes the daily-bars signature** on its inner tick and
  writes it to a tiny `admin_snapshots` row (`sig.daily_bars`); the admin
  reads it with the other fingerprints in SQL, so no request stats files.
- `equity_samples` is keyed on `(count, max(id))`; the plan confirms the
  table is append-only.
- The poll includes the Berlin date, so 30d/90d/ytd keys rebuild right after
  midnight.

**Build correctness**
- A build reads its fingerprints **before** it starts and re-reads them
  after it finishes; if any changed, the row is discarded and the next poll
  rebuilds (quant-engineer 2, BLOCKING). Test: a bar file rewritten during
  a build leaves no row stamped with the new signature.
- Only the refresher writes stored rows; the admin's on-miss compute never
  writes one.
- On a stored-body hit the admin runs only the fingerprint SQL (no
  memoised table load); test: zero trade/plan loads on a hit.
- The fingerprint-coverage test derives each view's inputs from a
  recording fake of the stores the builder reads, so a new read in a
  builder that its declaration misses fails the test.

**Load and rollback**
- `ADMIN_PREBUILT_VIEWS=off` stops the refresher's B2 builders as well as
  the admin's stored-view reads.
- The refresher polls fingerprints on its inner `QUEUE_POLL_S` tick
  (`refresher/loop.py`) rather than its 5–60 min cycle, and rebuilds only
  the views whose fingerprint changed, one at a time on one thread, cheapest
  first, each within `ADMIN_SNAPSHOT_BUDGET_S`. The plan measures a full
  pass after Phase A; if it exceeds Goal 4's 2 minutes, the 30d/90d/ytd ×
  weak/both keys are dropped first and the miss recorded.
- Single-flight (A4) keys on route + full query string + principal. A failed
  build releases the key and raises to every waiter; failures are never
  cached. At most two cold builds run at once (a semaphore); a waiter that
  cannot start within 25 s gets a 503 with `Retry-After`, so cold builds can
  never take all 8 request threads (`deploy/gunicorn.conf.py`).

**Resampling (A3)**
- The tolerance is calibrated against the spread of five old-loop seeds on
  the frozen book; the new band must lie within that spread or within
  `max(0.01 R, 2 % of width)`, whichever is wider.
- `week_cluster_bootstrap` keeps `WEEK_BOOTSTRAP_SEED`; every call site
  creates its own `numpy.random.Generator` per call, never a shared
  module-level one, so results do not depend on thread or call order.
- An exact-equality golden pins the sample statistics on the frozen book,
  including every per-card and per-split `cancel_precision.figure()` call,
  and the summation order is unchanged.

**Tests and goldens**
- The golden-body comparison masks a named list of JSON paths (the band
  edges only); the list lives next to the golden test.
- Per route, a test pins `generated_at` = the stored row's build time on a
  hit and the compute time on a miss, and that any `asof` is live.
- `performance_body` and `default_view_body` (and any other legacy function
  over complexity 15 the diff touches) get no worse against
  `complexity_baseline.json`.

### B7. Corrections after the code brief

The plan-briefer (2026-11-25) found spec assumptions the code contradicts.
These override A1–B6 where they differ; all are author's calls within the
approved design.

1. **Trade statuses are `open|win|loss|closed`** (PENDING/ACTIVE/PARTIAL are
   *plan* statuses, `core/planning/plan_types.py`). The trades fingerprint
   hashes the whole `doc` of every trade whose status is not `open`.
   Scale-out legs of still-open trades (the Dashboard's realized partials)
   are **live overlay**, computed per request from an open-trades-only load,
   never stored.
2. **`variance_band` is already numpy-vectorised.** A3 touches only its
   `_outer_p95s` loop and `week_cluster_bootstrap`.
3. **`week_cluster_bootstrap` is not rewritten in place.** It has ~20
   research/pre-registration callers whose closed results must stay
   reproducible. A3 adds a new vectorised function beside it; only the admin
   views (variance-band's `expr_block`, cancel-precision) switch to it. A
   test pins the old function's output on a fixture so it can never drift.
4. **`equity_samples` is not append-only** (`upsert_many`,
   `replace_backfill`, `update_realized`, `update_open_notional`). The
   candle memo keys on an SQL `md5` over the samples rows the timeframe
   reads, and `basis=realized` also on the trades fingerprint.
5. **The refresher's inner tick runs no steps** (`refresher/loop.py`
   `_sleep_until_due`). The plan adds a hook there that runs the fingerprint
   poll (cheap SQL plus the bar signature) and triggers rebuilds; cycles stay
   as they are.
6. **Snapshot keys are a closed regex** (`admin_refresh._SNAPSHOT_KEY`) and
   `test_builders_order_with_every_route_snapshotted` pins the builder list;
   both are extended deliberately, not bypassed.
7. **Stored-view reads use `admin_snapshot_repo().read`**, never
   `market_values.read_snapshot`, which enqueues a refresh as a side effect.
8. **Cancel-precision's baseline reads still-ACTIVE filled plans**
   (`filled_rows`). Its plans fingerprint covers terminal plans **and filled
   plans**, over the fields `filled_rows` reads. The plan first checks that a
   scan requote of a PENDING plan does not change it; if filled plans churn,
   cancel-precision leaves the prebuilt set (Phase A only).
9. **`/analytics/calibration` and `/analytics/strategies` read the file
   analytics snapshot and registry badges**, outside B1: they leave the
   prebuilt set (Phase A only). The Dashboard's `equity_30d` already reads a
   stored row; it moves to the live overlay.
10. The complexity baseline is `scripts/dev/complexity_baseline.json`.
    `performance_body` (17) and `analytics_by_dimension` (33) get no worse;
    `default_view_body` (4) stays under 15.
11. **No goldens exist for `/analytics/*`, cancel-precision, variance-band or
    candles.** Phase A's first task records characterization goldens for
    every route it touches, on a frozen fixture book, **before** any change;
    the eight existing frozen goldens stay byte-identical.
12. A4's single-flight is built new (shared failure, semaphore, 503 on
    timeout); `/risk`'s `_cached` is the starting shape, not reused as is.
13. `test_conditional_routes.py` pins the ETag route set exactly; B4 extends
    that set in the same commit.

Prebuilt set after these corrections: `analytics.performance`,
`analytics.equity_curve` (ledger × scope keys), `by-dimension`
(strategy/horizon/direction/dow), `heat-grid`, `variance-band`,
`exit-quality`, `cancel-precision` (subject to 8), and the Dashboard's
ledger blocks (stats, extended stats, realized from closed trades,
R multiples).

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

## Panel review

Spec review, 2026-11-25, on 20b33e2b. Three BLOCKING findings, all applied;
every ADVISORY applied in B6 unless noted.

- staff-engineer 1 (BLOCKING): fingerprint storage location unstated, migration/rollback -- applied (inside `inputs` JSONB, no migration)
- staff-engineer 2: ~37 keys vs 2-min goal and refresher duties; "low priority" undefined -- applied (changed-only rebuilds, one thread, cheapest first, measured, drop order named)
- staff-engineer 3: switch doesn't stop builders -- applied
- staff-engineer 4: single-flight waiters can take all 8 threads -- applied (2-build semaphore, 25 s then 503)
- staff-engineer 5: hand-picked doc fields; PARTIAL realized -- applied (whole doc incl. PARTIAL, churn measured first)
- staff-engineer 6: package owner unnamed -- applied (`core/analytics`)
- staff-engineer 7: per-request file stats -- applied (refresher writes the signature row)
- staff-engineer 8: relative scopes at midnight -- applied
- quant-engineer 1 (BLOCKING): daily-bars file set, basis, sidecar -- applied
- quant-engineer 2 (BLOCKING): signature read vs build race -- applied (read before, re-check after, discard on change)
- quant-engineer 3: signature scope and cost -- applied (plan tickers only, refresher-computed)
- quant-engineer 4: mtime-only identity -- applied (`mtime_ns`, size; writes confirmed to move mtime)
- quant-engineer 5: tolerance vs old-loop noise; seeds -- applied
- quant-engineer 6: `generated_at` meaning on miss path -- applied (per-route test; compute time on miss)
- quant-engineer 7: exact golden incl. per-card/per-split -- applied
- senior-engineer 1: single-flight key and error path -- applied
- senior-engineer 2: hit path must not pay the memoised load -- applied
- senior-engineer 3: pin `generated_at`/`asof` per route -- applied
- senior-engineer 4: coverage test needs derived inputs -- applied (recording fake)
- senior-engineer 5: request path must not write rows -- applied
- senior-engineer 6: golden masking mechanism -- applied (named JSON paths)
- senior-engineer 7: legacy complexity functions named -- applied
- senior-engineer 8: equity_samples key ignores rewrites -- applied (`count, max(id)`, append-only confirmed)
