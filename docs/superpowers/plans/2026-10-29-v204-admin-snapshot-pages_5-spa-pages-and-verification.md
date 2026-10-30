# v204 Admin snapshot pages, part 5: SPA pages and verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin snapshot pages](../specs/2026-10-29-v204-admin-snapshot-pages.md) (precedence: "Brief corrections", then "Panel amendments", then the earlier text)
**Index:** [`_0-index.md`](2026-10-29-v204-admin-snapshot-pages_0-index.md). The Goal, Global Constraints, Review Focus, Parallelisation, the task ledger and every cross-task contract ("SPA contract", "Risk body additions") live there and bind every task below.

Part scope: V204-16 … V204-19. The Risk page shows its two clocks, its
snapshot age on every risk panel, lower bounds for partial books,
"unavailable" with a reason for a null correlation or beta, heat and drawdown
against the account, the P&L basis and a Refresh control. Analytics, Calendar
and the dashboard sparkline show their snapshot (or request) as-of, the
incomplete note and the P&L basis. Then the one full-suite run, and the
post-deploy production probe.

`<wt>` is the implementation worktree's absolute path; `<R>` is the main tree
`E:/Documents/Private/Projects/Discord-Bot`.

**Consumed from earlier work (exact names; do not redefine).**
- v201 (merged first): `LiveValuesStore` (`status`, `requestRefresh`), `sb-market-value` (`MarketValue`, `ui/market-value.ts`), `sb-incomplete-note` (`IncompleteNote`, `ui/incomplete-note.ts`, copy `incomplete: N positions unpriced`), `sb-market-refresh` (`MarketRefresh`, `ui/market-refresh.ts`), `MarketMeta`, `MarketStatus`. V201-17's `dashboard.store.ts` (`market` refetch through the debounced `refresh` subject, first run skipped) and V201-20's `frontend/scripts/admin-page-timing.mjs`.
- V204-15 (part 4): `SnapshotUpdate`, `RiskBarsMeta`, `RiskFxMeta`, `RiskAccount`; `Risk.market_meta?/computed_at?/bars_meta?/fx_meta?/lower_bound?/account?`; `Correlation.values: … | null` with `reason?`; `RiskAvailability.beta_spy?: DomainAvailability | 'zero_variance'`; `market_meta?` on `EquitySeries`, `AnalyticsPerformance`, `AnalyticsEquityCurve`, `PnlCalendar`. `LiveValuesStore.snapshot(key)`, `requestRefresh(symbols, snapshots = [])`. `sb-market-value` inputs `kind`, `staleInputs`, `computedAt` (for `kind: 'snapshot'` the age comes from `computedAt`, never `asOf`). `sb-market-refresh [snapshots]`. `followSnapshot(key, loadedAt, reload)` and `snapshotMeta(meta, live)` in `stores/snapshot-follow.ts`. `lowerBoundLabel(value, missing)`, `unavailableLabel(reason)`, `availabilityReason(a)` in `ui/lower-bound.ts`. `PNL_BASIS_LABEL` and `sb-pnl-basis` (`PnlBasis`) in `ui/pnl-basis.ts`. The one-line correlation guard already in `workspaces/risk/risk.ts`.

**Rules every SPA task here follows.**
- **Snapshot age and tone come from `computed_at`, never from `market_meta.as_of`.** Every snapshot cell binds `kind="snapshot"` and `[computedAt]`. `as_of` is shown only as an input clock in words (Risk's FX clock, the request-view FX clause).
- **A missing input is never zero.** A null correlation (`{"values": null, "reason": "insufficient_overlap"}`) and `availability.beta_spy === "zero_variance"` render `unavailableLabel(reason)` ("unavailable: …"), never `0` or a bare dash.
- **P&L basis copy is exactly `pre-tax, before modelled frictions`**, rendered only through `sb-pnl-basis`.
- **No extra load at creation.** Each `followSnapshot` reload is guarded so it fires only once the page's data has loaded (`store.data() !== null`, or the panel's payload is non-null). A live snapshot already cached when a page mounts must not add a second request to the route's own load.
- **Specs provide a fake `LiveValuesStore`.** The real one syncs `/market/updates` at construction. Each spec file touched here defines a local `fakeLive()`:

```ts
function fakeLive(snaps = signal<Record<string, SnapshotUpdate>>({})) {
  const live = {
    snaps,
    status: signal<MarketStatus | null>({ session: 'regular', last_close_at: '2026-10-28T20:00:00Z',
      stale_price_s: 120, stale_snapshot_s: 600, heartbeat: { beat_at: null, cadence_s: 30, stalled: false } }),
    snapshot: (k: string) => computed(() => snaps()[k] ?? null),
    quote: () => signal(null),
    requestRefresh: vi.fn(),
  };
  return { live, provider: { provide: LiveValuesStore, useValue: live } };
}
```

# Phase 5a: SPA pages (V204-16, V204-17)

### Task V204-16: SPA Risk: two clocks, panel warnings, heat vs account, lower bounds, pre-tax label, Refresh

**Model:** sonnet — template and store wiring on one workspace over fixed V204-15 primitives; every copy string and warning rule is fixed here and pinned by specs written first.

**Files:**
- Modify: `frontend/src/app/stores/risk.store.ts`, `frontend/src/app/stores/risk.store.spec.ts`
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (inline template, styles and class), `frontend/src/app/workspaces/risk/risk.spec.ts`
- (The component has no separate `.html`/`.scss`; nothing else is touched. `api/models.ts` is V204-15's and is not edited here.)

**Interfaces:**
- Consumes: the header's V204-15 list; v201 `IncompleteNote`, `MarketRefresh`, `MarketValue`; the V204-12 Risk body (`market_meta`, `computed_at`, `bars_meta {per_symbol, oldest, newest, stale_inputs, missing: [{symbol, reason}]}`, `fx_meta {as_of, missing}`, `lower_bound` ⊆ `["metrics.closed", "metrics.distribution", "correlation", "clusters"]`, `account {balance, currency}`). `fx_meta.as_of` is a **date** (`"2026-10-29"`, the FX pair file's last bar) or `null`.
- Produces: nothing another task consumes.

**Behaviour fixed here:**
- **`RiskStore`** gains a second `withComputed((store, live = inject(LiveValuesStore)) => ({...}))` after the existing one:
  - `meta = computed(() => snapshotMeta(store.data()?.market_meta, live.snapshot('risk')()))`
  - `computedAt = computed(() => store.data()?.computed_at ?? null)`
  - `bars = computed<RiskBarsMeta | null>(() => store.data()?.bars_meta ?? null)`, `fx = computed<RiskFxMeta | null>(() => store.data()?.fx_meta ?? null)`
  - `missingCount = computed(() => meta()?.missing_count ?? 0)`
  - `lowerBound = computed(() => new Set(store.data()?.lower_bound ?? []))`
  - `positionTickers = computed(() => [...new Set((store.data()?.positions ?? []).map((p) => p.ticker.toUpperCase()))])`
  - `accountBalance = computed(() => finiteOrNull(store.data()?.account?.balance) ?? store.balance())`. The Risk body's own balance wins, and the existing `/dashboard` read stays as the fallback for an older server.
  - `correlationNote = computed(() => { const c = store.data()?.correlation; return c && c.values === null ? unavailableLabel(c.reason) : null; })`
  - `betaNote = computed(() => { const r = availabilityReason(store.data()?.availability?.beta_spy); return r === null ? null : unavailableLabel(r); })`
  - Plus `withHooks({ onInit(store) { followSnapshot(() => 'risk', () => store.computedAt(), () => { if (store.data() !== null) store.load(); }); } })`. `load()` is the existing quiet reload: the route's `sb-async` keeps the data on screen.
- **Two clocks** in `page-actions`, ahead of `.kill-actions`, rendered only when `store.data()?.market_meta` is present (an older server shows today's header):

```html
<div class="clocks" role="group" aria-label="Risk data clocks">
  <sb-market-value kind="snapshot" [asOf]="null" [computedAt]="store.computedAt()"
    [staleInputs]="store.bars()?.stale_inputs ?? false" [refreshing]="store.meta()?.refreshing ?? false"
    [error]="store.meta()?.error ?? null">Risk snapshot</sb-market-value>
  <span class="clock" data-clock="fx">FX rates as of {{ fxClock() }}</span>
  <span class="clock" data-clock="bars" [class.stale]="store.bars()?.stale_inputs">daily bars through {{ barsClock() }} close</span>
  @if (barsSpread(); as spread) { <sb-hint [text]="spread" label="Daily bars per symbol" /> }
  @if (missingBars(); as list) { <span class="clock stale" data-clock="missing-bars">no daily bars: {{ list }}</span> }
  @if (missingFx(); as list) { <span class="clock stale" data-clock="missing-fx">no FX rate: {{ list }}</span> }
  <sb-incomplete-note [missing]="store.missingCount()" />
  <sb-market-refresh [symbols]="store.positionTickers()" [snapshots]="riskKey" />
</div>
```

  - `riskKey = ['risk']` (a readonly class field, so the input keeps one array identity).
  - `fxClock()`: from `store.fx()?.as_of`. A date-only value (`/^\d{4}-\d{2}-\d{2}$/`) → `Mmm D` (`Intl.DateTimeFormat('en-US', {month: 'short', day: 'numeric', timeZone: 'UTC'})`, so a date never shifts a day). A value with a time → local `HH:MM` (`{hour: '2-digit', minute: '2-digit', hourCycle: 'h23'}`). `null` → `—`. The FX input on Risk is a daily rate file, so in practice the clock reads `FX rates as of Oct 29`; the `HH:MM` branch keeps the index copy for a timed value.
  - `barsClock()`: `store.bars()?.oldest` as `Mmm D` (same UTC formatter), `—` when null.
  - `barsSpread()`: `null` unless `per_symbol` holds more than one distinct date; then `AAPL Oct 28 · SAP.DE Oct 27` (symbols sorted). This is the spec's "each symbol's own last-bar date".
  - `missingBars()`: the `bars_meta.missing` symbols, sorted, joined with `, ` (`null` when empty). `missingFx()`: `fx_meta.missing` the same way.
- **Risk figures are warned like prices.** The `Portfolio heat` panel (first child), the `Risk metrics` panel and the `Underlying-asset correlation` panel each carry one snapshot cell with the same bindings as the header's (`kind="snapshot"`, `[asOf]="null"`, `[computedAt]`, `[staleInputs]`, `[refreshing]`, `[error]`) and no projected text. Both `sb-freshness [at]="store.metrics()?.as_of ?? null"` elements are **replaced** by it: the bar date now lives in the header's bars clock, which is named. Each replaced comment is reworded to: `v204: this panel's age is the risk snapshot's (computed_at); the bar date is the header's "daily bars through" clock.` Drop `Freshness` from `imports` if nothing else uses it.
- **Lower bounds.** `metricTiles()` marks a tile whose family is in `store.lowerBound()`: the distribution family (`VaR 95%`, `Expected shortfall`, `Annualised vol`, `Beta vs …`) under `metrics.distribution`, the closed family (`RISK_SHARPE_LABEL`, `RISK_DRAWDOWN_LABEL`) under `metrics.closed`. A marked tile's `secondary` becomes `lowerBoundLabel(tile.secondary ?? tile.value ?? '—', store.missingCount())` (with `missingCount` 0 the label is `null` and the tile keeps its own secondary). The `Underlying-asset correlation` panel (under `correlation`) and the `Correlated clusters` panel (under `clusters`) each render `<sb-incomplete-note [missing]="store.missingCount()" />` under their heading when marked. Heat is trade-based and never marked.
- **Unavailable, never zero.** The beta tile's `value` is `store.betaNote() ?? this.fmtRatio(m.beta_spy.value)`. In the correlation panel's two "unavailable" branches the copy becomes `Correlation {{ store.correlationNote() ?? 'data unavailable.' }}`, so a null matrix reads `Correlation unavailable: fewer than 2 overlapping bars`.
- **Heat and drawdown against the account.** `riskUnits(...)` reads `this.store.accountBalance()` instead of `this.store.balance()` (every KPI keeps money · %). `fmtDrawdownMoney(value)` appends ` · <pct>% of account` (two decimals, `value / accountBalance * 100`) when the balance is a positive number; otherwise today's text.
- **P&L basis.** In the `Risk metrics` panel, directly after the existing `section-help` line: `<p class="section-help">Money drawdown: <sb-pnl-basis /></p>`.
- **Styles.** `.clocks {display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-4) var(--space-8); min-width: 0}`, `.clock {font-size: var(--text-micro); color: var(--text-faint); font-variant-numeric: tabular-nums; overflow-wrap: anywhere}`, `.clock.stale {color: var(--warn)}`. Below `BREAKPOINTS.sm` (640px): `.clocks {flex-basis: 100%; flex-direction: column; align-items: flex-start}`, so each clock takes its own line and the killswitch buttons keep their `sb-hit` size.
- Add `IncompleteNote`, `MarketRefresh`, `MarketValue` and `PnlBasis` to the component's `imports`.

- [ ] **Step 1: Write the failing specs**

`stores/risk.store.spec.ts`: lift the file's existing `beforeEach` body into `configure(extra: Provider[] = [])`, which the old `beforeEach` calls as `configure([fakeLive().provider])` (the header's helper). A `risk(body)` helper flushes `/api/v1/risk` with `{...RESPONSE, ...body}` and answers `/api/v1/dashboard` with `{account_balance: 10_000}`. `META` is a full `MarketMeta` literal: `{as_of: '2026-10-29', refreshing: false, stale_count: 0, missing_count: 1, incomplete: true, computed_at: '2026-10-29T14:00:00Z', stale_inputs: false, source: 'snapshot', error: null}`. New `describe('RiskStore snapshot (v204)')` (each test calls `TestBed.resetTestingModule()` before its own `configure`):

```ts
const upd = (computed_at: string | null, refreshing = false): SnapshotUpdate =>
  ({ key: 'risk', computed_at, stale_inputs: false, refreshing, error: null });

it('refetches once when the risk snapshot lands newer', () => {
  const { live, provider } = fakeLive();
  configure([provider]);
  const store = TestBed.inject(RiskStore);
  store.load(); tick(); risk({ computed_at: '2026-10-29T14:00:00Z' });
  live.snaps.set({ risk: upd('2026-10-29T14:00:00Z') }); tick();
  backend.expectNone('/api/v1/risk');
  live.snaps.set({ risk: upd('2026-10-29T14:05:00Z') }); tick();
  backend.expectOne('/api/v1/risk');
});

it('adds no load at creation when a snapshot is already cached', () => {
  const { live, provider } = fakeLive();
  live.snaps.set({ risk: upd('2026-10-29T14:05:00Z') });
  configure([provider]);
  const store = TestBed.inject(RiskStore);
  tick();
  backend.expectNone('/api/v1/risk');          // only the route's own load() may fetch
  expect(store.data()).toBeNull();
});

it('meta takes refreshing from the live snapshot', () => {
  const { live, provider } = fakeLive();
  configure([provider]);
  const store = TestBed.inject(RiskStore);
  store.load(); tick(); risk({ market_meta: META, computed_at: '2026-10-29T14:00:00Z' });
  live.snaps.set({ risk: upd(null, true) });
  expect(store.meta()?.refreshing).toBe(true);
});
```

Also add, each as real code:
- `positionTickers are the unique upper-case position tickers` (`AAPL`, `aapl`, `MSFT` → `['AAPL', 'MSFT']`).
- `accountBalance prefers the risk body's account balance` (`account: {balance: 12_500, currency: 'USD'}` with dashboard `10_000` → `12_500`; without `account` → `10_000`).
- `correlationNote names the reason for a null matrix` (`correlation: {labels: ['AAPL'], values: null, reason: 'insufficient_overlap'}` → `'unavailable: fewer than 2 overlapping bars'`; a normal matrix → `null`).
- `betaNote reads zero_variance` (`availability: {...AVAILABILITY, beta_spy: 'zero_variance'}` → `'unavailable: benchmark did not move'`; an `ok` availability → `null`).

`workspaces/risk/risk.spec.ts`: `seed()` puts `fakeLive().provider` ahead of `extra` in its providers, so a test's own fake wins. A `SNAP` fixture spreads into `payload()`:

```ts
const SNAP: Partial<RiskData> = {
  market_meta: { as_of: '2026-10-29', refreshing: false, stale_count: 0, missing_count: 0, incomplete: false,
    computed_at: '2026-10-29T14:00:00Z', stale_inputs: false, source: 'snapshot', error: null },
  computed_at: '2026-10-29T14:00:00Z',
  bars_meta: { per_symbol: { AAPL: '2026-10-28' }, oldest: '2026-10-28', newest: '2026-10-28', stale_inputs: false, missing: [] },
  fx_meta: { as_of: '2026-10-29', missing: [] },
  lower_bound: [],
  account: { balance: 10_000, currency: 'USD' },
};
```

New `describe('Risk snapshot clocks and warnings (v204)')`, each case written as real code over `render({...SNAP, ...overrides})`:
- `labels its two clocks`: the `.clocks` text contains `FX rates as of Oct 29` and `daily bars through Oct 28 close`.
- `the FX clock reads HH:MM for a timed as-of`: `fx_meta.as_of = '2026-10-29T14:32:00'` (local) → `FX rates as of 14:32`.
- `stale bars take the stale tone`: `bars_meta.stale_inputs: true` → `[data-clock="bars"]` has class `stale`, and the header `sb-market-value .mv` has `data-tone="stale"`.
- `per-symbol bar dates show when they differ`: `per_symbol {AAPL: '2026-10-28', 'SAP.DE': '2026-10-27'}` → an `sb-hint` in `.clocks` whose text is `AAPL Oct 28 · SAP.DE Oct 27`.
- `lists symbols with no daily bars and no FX rate`: `bars_meta.missing: [{symbol: 'XAUUSD', reason: 'spot_metal'}]`, `fx_meta.missing: ['SAP.DE']` → `no daily bars: XAUUSD` and `no FX rate: SAP.DE`.
- `risk panels carry the snapshot age`: one `sb-market-value` inside each of the `Portfolio heat`, `Risk metrics` and `Underlying-asset correlation` panels, and `el.querySelectorAll('sb-freshness').length === 0`.
- `lower-bound note renders for a partial book`: `lower_bound: ['metrics.distribution']`, `market_meta.missing_count: 1` → the `VaR 95%` tile's text contains `≥ ${shown}, 1 position unpriced`, where `shown` is that tile's own value text read from the same render, and the `Sharpe` tile's text contains no `≥`.
- `marked correlation and clusters panels show the incomplete note`: `lower_bound: ['correlation', 'clusters']`, `missing_count: 2` → two `incomplete: 2 positions unpriced` notes outside `.clocks`.
- `null correlation reads unavailable with its reason, never 0`: `correlation: {labels: ['AAPL', 'MSFT'], values: null, reason: 'insufficient_overlap'}` → text `Correlation unavailable: fewer than 2 overlapping bars`, no `sb-matrix`.
- `zero-variance beta reads unavailable, never 0`: `availability.beta_spy = 'zero_variance'`, `beta_spy: {value: null, n: 118}` → the beta tile's value is `unavailable: benchmark did not move`.
- `drawdown is shown against the account`: `max_drawdown_amount: {value: 1_200, n: 782, fx_missing_count: 0}`, `account.balance: 10_000` → the drawdown tile's secondary contains `12.00% of account`.
- `money drawdown carries the P&L basis`: `.metrics sb-pnl-basis` text is `pre-tax, before modelled frictions`.
- `Refresh asks for the position tickers and the risk snapshot`: positions `MSFT`, `NVDA`, a test-owned `fakeLive()` passed as `extra`; click the `sb-market-refresh` button → `live.requestRefresh` called with `(['MSFT', 'NVDA'], ['risk'])`.
- `an older server without meta renders no clock`: `render()` without `SNAP` → no `.clocks`, no thrown error.

Replace the three cases in `describe('Risk freshness and chrome')` that assert `sb-freshness` (`marks the metrics panel with the bar date…`, `shows the metrics panel marker as a real date…`, `dates each metrics panel by its own bar…`) with one case, `the bar date moved to the header clock`: `render({...SNAP})` has no `sb-freshness`, and the `.clocks` text contains `daily bars through Oct 28 close` and no `00:00`.

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix <wt>/frontend exec -- ng test --watch=false --include src/app/stores/risk.store.spec.ts --include src/app/workspaces/risk/risk.spec.ts`
Expected: FAIL (`store.meta is not a function`, no `.clocks`, `sb-freshness` still present).

- [ ] **Step 3: Implement** as fixed above. `fxClock`, `barsClock`, `barsSpread`, `missingBars` and `missingFx` are `protected` computeds of `Risk` over two module-level formatters (`DAY_FMT`, `HHMM_FMT`). Put the lower-bound marking in a private `markLowerBound(tile: MetricTile, family: 'metrics.distribution' | 'metrics.closed'): MetricTile`, so `metricTiles` stays below complexity 15. Keep every existing comment that still describes the code.

- [ ] **Step 4: Run them and the neighbouring specs**

Run: the Step 2 command plus `--include src/app/ui/market-value.spec.ts --include src/app/stores/snapshot-follow.spec.ts --include src/app/ui/lower-bound.spec.ts`
Expected: PASS.
Run: `npm --prefix <wt>/frontend exec -- ng build`
Expected: green.

- [ ] **Step 5: Check three widths**

With `ng serve` and a local admin backed by the `swing-db` replica (`/replicate-prod-db` first; log in with `.env`'s admin credentials loaded inside the script, never printed), run `node <wt>/frontend/scripts/browse.mjs shots --base http://localhost:4200 --path /app/risk --widths 1440,768,390`. Confirm in each `.txt` that `page-scroll-x: 0`. In the PNGs: at 390 px each clock sits on its own line, the killswitch buttons keep their touch size, and each panel's snapshot age wraps under its heading without widening the exposure table.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add frontend/src/app/stores/risk.store.ts frontend/src/app/stores/risk.store.spec.ts frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts
git -C <wt> commit -m "feat(v204): Risk two clocks, snapshot age per panel, lower bounds, unavailable reasons, heat vs account, Refresh"
```

### Task V204-17: SPA Analytics, Calendar and the dashboard sparkline: snapshot labels, filtered as-of labels, pre-tax label

**Model:** sonnet — store and template wiring on three workspaces over fixed V204-15 primitives; the default-view rule, the request-view copy and the reload guard are fixed here and pinned by specs.

> **The only v204 editor of `dashboard.store.ts` and the sparkline** (index § Parallelisation). It builds on V201-17's merged `dashboard.store.ts`, `dashboard.ts` and `panels/trading-performance.ts`. Before Step 1, `git -C <wt> grep -n "MARKET_DATA_MIN_INTERVAL_MS" frontend/src/app/stores/dashboard.store.ts` must hit (V201-17's `market` refetch). If it misses, stop and report `BLOCKED: V201-17 not on main`.
>
> **Where the sparkline is.** `equity_30d` reaches the screen through `DashboardStore.equityPoints`/`equityChangePct` → `sb-trading-performance` → `sb-portfolio-value` (`panels/portfolio-value.ts`), which renders the `… today` change line from `change_pct`. The label goes there; `portfolio-value.ts` is in `workspaces/dashboard/**`, which this task owns.

**Files:**
- Modify: `frontend/src/app/stores/analytics.store.ts`, `frontend/src/app/stores/analytics.store.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts`, `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts`
- Modify: `frontend/src/app/stores/calendar.store.ts`, `frontend/src/app/stores/calendar.store.spec.ts`
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts`, `frontend/src/app/workspaces/calendar/calendar.spec.ts`
- Modify: `frontend/src/app/stores/dashboard.store.ts`, `frontend/src/app/stores/dashboard.store.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (one binding), `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` (+`trading-performance.spec.ts`), `frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts` (+`portfolio-value.spec.ts`)

**Interfaces:**
- Consumes: the header's V204-15 list; v201 `IncompleteNote`, `MarketValue`, `MarketMeta`. Backend (V204-13, V204-14): `equity_30d.market_meta` (`source: "snapshot"`, or `null` on the swallowed-error branch); `market_meta` on `/analytics/performance`, `/analytics/equity-curve` and `/calendar/pnl`, with `source: "snapshot"` (default view served from a row: `computed_at` set) or `source: "request"` (`computed_at: null`, `as_of` = oldest FX date or `null`, `refreshing: true` while a first row is pending). Server default-view rules: Analytics is default when no `from`, `to`, `strategy`, `horizon` or `direction` is set (any ledger); Calendar is default when neither `strategy` nor `horizon` is set and the month is the current or previous one.
- Produces: `requestAsOfText(meta: MarketMeta | null | undefined): string | null`, exported from `stores/analytics.store.ts` and used by `calendar.ts`. Nothing outside this task consumes it.

**Behaviour fixed here:**
- **`requestAsOfText(meta)`** returns `null` when `meta` is null/undefined or `meta.source === 'snapshot'`. Otherwise `as of this request`, followed by ` · FX rates as of Mmm D` when `meta.as_of` is set (same UTC `Mmm D` formatter as V204-16; a timed value prints its date). A request view is computed for the request that asked, so that is its clock; FX is its one cached input.
- **`AnalyticsStore`** gains `withComputed((store, live = inject(LiveValuesStore)) => ({...}))` after the existing ones:
  - `defaultView = computed(() => (['from', 'to', 'strategy', 'horizon', 'direction'] as const).every((k) => !store.scope()[k]))`
  - `performanceKey = computed(() => defaultView() ? `analytics.performance:${store.scope().ledger}` : null)`, `equityCurveKey` the same with `analytics.equity_curve:`.
  - (`defaultView`, `performanceKey` and `equityCurveKey` are declared as local `const`s inside the factory and returned, because computeds in one `withComputed` object cannot read each other through `store`. The same holds for `snapshotKey` in `CalendarStore` below.)
  - `performanceMeta = computed(() => { const k = performanceKey(); return snapshotMeta(store.performance()?.market_meta, k ? live.snapshot(k)() : null); })`, `equityCurveMeta` the same over `equityCurve()`.
  - `withHooks({ onInit(store) {...} })` calls `followSnapshot(store.performanceKey, () => store.performance()?.market_meta?.computed_at ?? null, () => { if (store.performance() !== null) store.reload('performance'); })` and the same for `equityCurveKey` / `equityCurve()` / `reload('equityCurve')`. A key whose route V204-2 left `request` never gets a row, so it never reloads.
- **Overview tab** (`overview.ts`). Under the `Equity` panel's `sb-panel-header` and under the `Outcome` panel's, one `<div class="as-of">` holding, for that panel's meta (`store.equityCurveMeta()` / `store.performanceMeta()`):
  - `meta.source === 'snapshot'`: `<sb-market-value kind="snapshot" [asOf]="null" [computedAt]="meta.computed_at" [staleInputs]="meta.stale_inputs" [refreshing]="meta.refreshing" [error]="meta.error" />`;
  - otherwise: `<span class="req-as-of">{{ requestAsOfText(meta) }}</span>`, plus an `sb-spinner` while `meta.refreshing`;
  - then `<sb-incomplete-note [missing]="meta.missing_count" />`.
  - Nothing renders for a null meta. Under the Equity panel's header, after `.as-of`, `<sb-pnl-basis />` (the Analytics money totals are realised P&L). `.as-of {display: flex; flex-wrap: wrap; gap: var(--space-4) var(--space-8); align-items: baseline; font-size: var(--text-micro); color: var(--text-faint); min-width: 0}`.
- **`CalendarStore`** gains `withComputed((store, live = inject(LiveValuesStore)) => ({ snapshotKey: computed(() => !store.strategy() && !store.horizon() ? `calendar.pnl:${store.month()}` : null), meta: computed(() => { const k = snapshotKey(); return snapshotMeta(store.data()?.market_meta, k ? live.snapshot(k)() : null); }) }))`. In the existing `onInit`, after the metric effect: `followSnapshot(store.snapshotKey, () => store.data()?.market_meta?.computed_at ?? null, () => { if (store.data() !== null) store.load(); })`. A key for an older month never gets a row, so it never reloads.
- **Calendar page** (`calendar.ts`). In `head-status`, after the error span: the same three-way block as the overview over `store.meta()` (`sb-market-value kind="snapshot"` for a snapshot meta, `.req-as-of` text with `requestAsOfText` otherwise, then `sb-incomplete-note`). Inside the totals panel, directly under the `sb-stat-strip class="totals"`, `<p class="pnl-basis-line"><sb-pnl-basis /></p>`. `head-status` keeps `display: contents`. The new block is wrapped in a `<span class="as-of">` with the overview's styles, so it wraps under the title on a phone.
- **`DashboardStore`** gains `equityMeta = computed(() => snapshotMeta(data()?.equity_30d?.market_meta, live.snapshot('analytics.snapshot')()))` (inject `LiveValuesStore` in a new `withComputed` factory). In `onInit`, after V201-17's effects: `followSnapshot(() => 'analytics.snapshot', () => store.data()?.equity_30d?.market_meta?.computed_at ?? null, () => { if (store.data() !== null) refresh.next(); })`, reusing the debounced `refresh` subject so a snapshot landing beside a `market` event costs one request.
- **Sparkline label.** `TradingPerformance` gains `readonly equityMeta = input<MarketMeta | null>(null)` and passes `[meta]="equityMeta()"` to `sb-portfolio-value`. `PortfolioValue` gains `readonly meta = input<MarketMeta | null>(null)` and renders, after the `.change` block and outside its `@if` (so an empty series still shows the spinner, which was the bug the spec names): `@if (meta(); as m) { <p class="as-of"><sb-market-value kind="snapshot" [asOf]="null" [computedAt]="m.computed_at" [staleInputs]="m.stale_inputs" [refreshing]="m.refreshing" [error]="m.error" /> <sb-pnl-basis /></p> }`. `dashboard.ts` binds `[equityMeta]="store.equityMeta()"` on `sb-trading-performance`. The `.as-of` style is the overview's, with `margin: 0 0 var(--space-10)`.

- [ ] **Step 1: Write the failing specs**

Every spec file below that creates `AnalyticsStore`, `CalendarStore`, `DashboardStore`, `Calendar` or `OverviewTab` adds `fakeLive().provider` (the header's helper) to each of its `TestBed.configureTestingModule` provider lists. A test that drives snapshots keeps its own `fakeLive()` handle. `upd(key, computed_at)` builds a `SnapshotUpdate` with `stale_inputs: false, refreshing: false, error: null`. `SNAP_META` and `REQ_META` are full `MarketMeta` literals: `SNAP_META = {as_of: '2026-10-29', refreshing: false, stale_count: 0, missing_count: 0, incomplete: false, computed_at: '2026-10-29T14:00:00Z', stale_inputs: false, source: 'snapshot', error: null}`; `REQ_META = {...SNAP_META, computed_at: null, source: 'request', as_of: '2026-10-28', missing_count: 1, incomplete: true}`.

`stores/analytics.store.spec.ts`, new `describe('AnalyticsStore snapshots (v204)')`:

```ts
it('requestAsOfText names the request and its FX date', () => {
  expect(requestAsOfText(REQ_META)).toBe('as of this request · FX rates as of Oct 28');
  expect(requestAsOfText({ ...REQ_META, as_of: null })).toBe('as of this request');
  expect(requestAsOfText(SNAP_META)).toBeNull();
  expect(requestAsOfText(undefined)).toBeNull();
});

it('follows the performance and equity snapshots on the default view only', () => {
  // overview loaded with performance.market_meta = SNAP_META (computed_at 14:00)
  live.snaps.set({ 'analytics.performance:main': upd('analytics.performance:main', '2026-10-29T14:05:00Z') });
  tick();
  expect(backend.match((r) => r.url === '/api/v1/analytics/performance')).toHaveLength(1);
  store.setScope({ strategy: 'VWAP' });
  // flush the scope's own reloads, then a newer snapshot lands
  live.snaps.set({ 'analytics.performance:main': upd('analytics.performance:main', '2026-10-29T14:10:00Z') });
  tick();
  expect(backend.match((r) => r.url === '/api/v1/analytics/performance')).toHaveLength(0);
});
```

Write the comments out as real code with the file's existing `load`/flush helpers. Also add, as real code: `the key follows the ledger` (`setScope({ledger: 'weak'})` → `performanceKey()` is `'analytics.performance:weak'`); `performanceMeta ORs refreshing from the live snapshot`; `no reload before the first payload` (a snapshot cached before `load()` is answered → no extra performance request).

`workspaces/analytics/tabs/overview.spec.ts`: `storeStub` gains `performanceMeta: signal(null)` and `equityCurveMeta: signal(null)`. New cases, each as real code:
- `equity and outcome panels show the snapshot age`: both metas `SNAP_META` → two `sb-market-value` in `.as-of`, no `.req-as-of`.
- `a filtered view shows the request as-of`: both `REQ_META` → `.req-as-of` text `as of this request · FX rates as of Oct 28`, and `incomplete: 1 position unpriced`.
- `the equity panel carries the P&L basis`: `sb-pnl-basis` text `pre-tax, before modelled frictions` inside the Equity panel.
- `no meta renders no as-of`: both `null` → no `.as-of`.

`stores/calendar.store.spec.ts`, as real code: `follows the shown month's snapshot key` (`setMonth('2026-10')` → `snapshotKey()` is `'calendar.pnl:2026-10'`; a newer `upd` for that key after data loaded → one more `/calendar/pnl` request); `a filtered month follows nothing` (`setStrategy('VWAP')` → `snapshotKey()` is `null`); `no reload before data loads`.

`workspaces/calendar/calendar.spec.ts`: `seed()` gains `fakeLive().provider`. New `describe('Calendar as-of and basis (v204)')`, as real code: `head shows the snapshot age` (`seed({...RESPONSE, market_meta: SNAP_META})` → one `sb-market-value` in `.head-status`); `a filtered month shows the request as-of and the incomplete note` (`REQ_META` → `.req-as-of` text and `incomplete: 1 position unpriced`); `the totals carry the P&L basis` (`.pnl-basis-line sb-pnl-basis` text exact).

`stores/dashboard.store.spec.ts`, as real code: `equityMeta merges the live analytics snapshot` (a body with `equity_30d.market_meta = SNAP_META`, live `refreshing: true` → `equityMeta()?.refreshing` true); `a newer analytics snapshot refetches the dashboard once` (after the debounce, `api.dashboard` called twice in all; the same update again adds none); `still loads once at creation with a cached snapshot` (snapshot set before creation → 1 call).

`panels/portfolio-value.spec.ts`, as real code: `the sparkline figure carries the snapshot age and the P&L basis` (`render({balance: 1, changePct: 0.5, currency: '€', meta: SNAP_META})` → `.as-of sb-market-value` present, `sb-pnl-basis` text exact); `an empty series still shows the refreshing spinner` (`changePct: null, meta: {...SNAP_META, computed_at: null, refreshing: true}` → `sb-spinner` inside `.as-of`); `no meta renders no label`. The `TestBed` here provides `fakeLive().provider` beside the `EquityCandlesStore` stub. `panels/trading-performance.spec.ts`: `passes equityMeta to the portfolio value` (setting `equityMeta` → `sb-portfolio-value .as-of` present).

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix <wt>/frontend exec -- ng test --watch=false --include src/app/stores/analytics.store.spec.ts --include src/app/workspaces/analytics/tabs/overview.spec.ts --include src/app/stores/calendar.store.spec.ts --include src/app/workspaces/calendar/calendar.spec.ts --include src/app/stores/dashboard.store.spec.ts --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts`
Expected: FAIL (`requestAsOfText` not exported, `performanceKey`/`snapshotKey`/`equityMeta` missing, no `.as-of`).

- [ ] **Step 3: Implement** as fixed above. In `overview.ts` and `calendar.ts`, write the three-way block once per file as an `<ng-template #asOf let-meta>` used through `ngTemplateOutlet`, so the two panels share it. Add `IncompleteNote`, `MarketValue`, `PnlBasis`, `Spinner` and `NgTemplateOutlet` to the touched components' `imports` as needed. Keep each store's new computeds in their own `withComputed` block, and every existing comment.

- [ ] **Step 4: Run them and the neighbouring specs**

Run: the Step 2 command plus `--include src/app/workspaces/analytics/analytics.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/stores/snapshot-follow.spec.ts`
Expected: PASS.
Run: `npm --prefix <wt>/frontend exec -- ng build`
Expected: green.

- [ ] **Step 5: Check three widths**

As V204-16 Step 5 (`/replicate-prod-db` first; `.env` admin credentials loaded inside the script, never printed), for `/app/analytics`, `/app/calendar` and `/app/dashboard` at 1440, 768 and 390 px. Also capture `/app/analytics` with one filter applied (the request as-of). Expect `page-scroll-x: 0` everywhere. At 390 px the as-of line and the P&L basis wrap under their figure, and no table column widens.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts frontend/src/app/workspaces/analytics/tabs/overview.ts frontend/src/app/workspaces/analytics/tabs/overview.spec.ts frontend/src/app/stores/calendar.store.ts frontend/src/app/stores/calendar.store.spec.ts frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/calendar.spec.ts frontend/src/app/stores/dashboard.store.ts frontend/src/app/stores/dashboard.store.spec.ts frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/dashboard/panels/trading-performance.ts frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts
git -C <wt> commit -m "feat(v204): Analytics, Calendar and sparkline snapshot labels, request as-of on filtered views, P&L basis"
```

# Phase 5b: verification (V204-18, V204-19)

### Task V204-18: Full suite

**Model:** sonnet — a gate run: run, read, and fix only what it names in the owning task's files.

**Files:**
- No new files. A fix touches only the files of the task that owns the failing code (index § Task ledger), committed as `fix(v204): <what> (V204-<n>)`.

**Interfaces:**
- Consumes: every task V204-1 … V204-17 committed on the worktree branch.
- Produces: the plan's one green full-suite run. Its numbers go into the hand-back report and are quoted at `/close-out`.

- [ ] **Step 1: Sync the database replica**

Run `/replicate-prod-db` into the shared `swing-db` container (never a per-task container). The full suite includes the `storage`, `admin-snapshots` and `admin` suites, which read it. A default DB port skips those tests silently, so check that the run's summary shows `tests/db/test_v204_admin_snapshots.py` as passed, not skipped.

- [ ] **Step 2: Check the suite registration and the migration head**

Run: `python <wt>/scripts/dev/testrun.py suites`
Expected: lists `admin-snapshots` (V204-1), and no suite is over its `max_tests`.
Run: `python -m alembic -c <wt>/alembic.ini heads`
Expected: exactly one head, `v204_001`.

- [ ] **Step 3: Run the backend full suite through the `test-runner` subagent**

Dispatch `test-runner` with: `python <wt>/scripts/dev/testrun.py full`.
Expected: `0 failed`, `0 xfailed`. A changed pass count alone is not a failure (`testing-cost.md`). Then run `python <wt>/scripts/dev/testrun.py suite admin-snapshots` on its own and expect PASS. This catches a test that only passes beside another suite's fixture.

- [ ] **Step 4: Confirm the kill-switch path as a whole suite**

Run: `python <wt>/scripts/dev/testrun.py suite admin`
Expected: PASS with `tests/admin/conftest.py` pinning `ADMIN_REFRESHER="off"`. This is the spec's "`ADMIN_REFRESHER=off` keeps today's request-time compute path for Risk, Analytics, Calendar and the sparkline", run as a suite. The golden payloads under `tests/admin_snapshots/golden/` are unchanged: `git -C <wt> diff main --stat -- tests/admin_snapshots/golden/` lists only V204-1's additions.

- [ ] **Step 5: Run the complexity gate**

Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean. Never run `--update` to pass it. It only shrinks the baseline after a real reduction.

- [ ] **Step 6: Run the whole SPA suite, the production build and the lint**

Run: `npm --prefix <wt>/frontend exec -- ng test --watch=false`
Expected: every spec passes. `git -C <wt> grep -n "\.only(\|\.skip(" -- frontend/src` adds no hit compared with `main`.
Run: `npm --prefix <wt>/frontend exec -- ng build`
Expected: build succeeds with no new budget warning.
Run: `npm --prefix <wt>/frontend run lint`
Expected: no errors.

- [ ] **Step 7: Fix any failure narrowly**

For each failure: read the assertion, find the task that owns the file (the index's ledger), fix the code in that task's files, and re-run **only that test** (`python <wt>/scripts/dev/testrun.py file <test>` or `ng test --watch=false --include <spec>`). Never re-run the whole suite for one fix. A failure in a test this plan did not touch that also fails on `main` (`python <R>/scripts/dev/testrun.py file <test>` on the main tree) is reported to the controller, not fixed here. A failing parity test is fixed in the code, never by editing a golden file (Global Constraints).

- [ ] **Step 8: Commit fixes, if any; report**

```bash
git -C <wt> status --short          # only the fixed files
git -C <wt> add <each fixed path>
git -C <wt> commit -m "fix(v204): <what> (V204-<n>)"
```

Report: the backend passed/failed/xfailed counts and wall time, the `admin-snapshots` and `admin` suite results, the SPA spec count, the `ng build` and lint results, the gate result, and each fix with its owning task id. After this the controller merges the branch to `main` (no second full suite after the merge), and the partner deploys. V204-19 waits for that deploy.

### Task V204-19: Post-deploy production timing and label check

**Model:** sonnet — extends a bounded read-only browser probe that already exists, plus a results document; every new page, phrase, pass rule and recorded input is fixed here.

**Runs when:** after V204-18 is green, the branch is merged to `main`, and the partner has deployed it. It runs on `main` in the main tree `<R>`, not in the worktree. It is the only v204 task that touches production, and only read-only (index Global Constraints).

> **Extend, do not rewrite.** v201's V201-20 created `frontend/scripts/admin-page-timing.mjs` and its `node:test` file, with the bounds (`ACTION_TIMEOUT_MS`, `PAGE_WAIT_MS`, `SETTLE_MS`, `GLOBAL_DEADLINE_MS`), the one-login rule, the `page.route` abort of every non-GET but the login, `labelOk`, `visitVerdict`, `renderTable`, the cold/warm/scan passes and the JSONL. Every one of those stays as it is. This task adds pages, a required-text check, a v204 preflight and an inputs record. Before Step 1, `git -C <R> ls-files frontend/scripts/admin-page-timing.mjs` must print the path. If it does not, stop and report `BLOCKED: V201-20 probe missing`.

**Files:**
- Modify (created by v201 V201-20, on `main` before this task): `frontend/scripts/admin-page-timing.mjs`, `frontend/scripts/admin-page-timing.test.mjs`
- Create: `docs/superpowers/results/2026-10-29-v204-page-timing.md`

**Interfaces:**
- Consumes: production `GET /api/v1/system/health` (versions, `refresher.status`), `GET /api/v1/market/updates` (V204-11b: `snapshots`, `status.stale_snapshot_s`), `GET /api/v1/risk` (V204-12: `computed_at`, `bars_meta`), `GET /api/v1/system/scan` (`running`). DOM from V204-16/17: `.clocks` on Risk, `sb-pnl-basis`, `sb-portfolio-value sb-market-value` on the Dashboard, and v201's `sb-market-value` / `.mv-age` / `.mv-value[hidden]`. The rail links `a.rail-link[aria-label="Risk"|"Analytics"|"Calendar"]`.
- Produces: `<out>/page-timing.jsonl` (now also one `kind: "inputs"` line per pass) and the results document.

**Behaviour fixed here:**
- **Pages.** `PAGES` keeps v201's four entries in order and appends three. The Dashboard entry gains a required selector:

```js
export const PNL_BASIS = 'pre-tax, before modelled frictions';
export const PAGES = [
  { name: 'Dashboard', rail: 'Dashboard', selectors: ['sb-portfolio-value sb-market-value'] },
  { name: 'Trades', rail: 'Trades' }, { name: 'Trade detail', path: 'TRADE' }, { name: 'Watchlist', rail: 'Watchlist' },
  { name: 'Risk', rail: 'Risk', phrases: ['FX rates as of', 'daily bars through', PNL_BASIS] },
  { name: 'Analytics', rail: 'Analytics', phrases: [PNL_BASIS] },
  { name: 'Calendar', rail: 'Calendar', phrases: [PNL_BASIS] },
];
```

- **Required text.** A new exported pure function `missingRequirements(text, present, spec)` returns `[...]` of the `spec.phrases` not found in `text` (case-sensitive substring) followed by the `spec.selectors` whose entry in `present` (a `{[selector]: boolean}` map) is not `true`. The label scan (v201's step 5) also returns `text: main.workspace.innerText` and `present`, one `document.querySelector(sel) !== null` per selector. The visit line gains `missing: string[]`.
- **Verdict.** `visitVerdict` gains one rule, after v201's: `if ((v.missing ?? []).length) reasons.push('missing label: ' + v.missing.join(', '))`. v201's visits, which have no `missing`, keep their verdict.
- **Preflight.** After v201's checks, the `/market/updates` body must have an array `snapshots` and a `status` that has the key `stale_snapshot_s`. Otherwise print `v204 not deployed: /market/updates has no snapshots` and exit 2.
- **Inputs per pass.** After each pass's visits, `recordInputs(page, passName)` reads, through `page.evaluate(fetch)` (GET only), `/api/v1/system/health` (the deployed `ui` and `bot` versions), `/api/v1/system/scan` (`running`), `/api/v1/risk` (`computed_at`, `bars_meta.oldest`, `bars_meta.newest`, `bars_meta.stale_inputs`) and `/api/v1/market/updates` (`snapshots[]` as `{key, computed_at, stale_inputs, refreshing, error}`). It appends one line `{pass, kind: 'inputs', at: <ISO now>, versions, scanRunning, risk: {...}, snapshots: [...]}`. These reads come after the pass's visits, so they never count in a visit's timings. No body other than those fields is written.
- **Scope of the verdict.** Every page is timed and label-checked. The v204 verdict is read from the Risk, Analytics, Calendar and Dashboard rows (the Dashboard row now covers the sparkline). Trades, Trade detail and Watchlist rows are recorded as a regression check of v201.

- [ ] **Step 1: Write the failing unit tests** (append to `frontend/scripts/admin-page-timing.test.mjs`; v201's four tests stay unchanged)

```js
import { missingRequirements, PAGES, PNL_BASIS } from './admin-page-timing.mjs';

test('Risk requires both clocks and the P&L basis', () => {
  const risk = PAGES.find((p) => p.name === 'Risk');
  assert.deepEqual(missingRequirements('FX rates as of Oct 29 daily bars through Oct 28 close ' + PNL_BASIS, {}, risk), []);
  assert.deepEqual(missingRequirements('FX rates as of Oct 29', {}, risk), ['daily bars through', PNL_BASIS]);
});
test('the dashboard requires the sparkline snapshot cell', () => {
  const dash = PAGES.find((p) => p.name === 'Dashboard');
  assert.deepEqual(missingRequirements('', { 'sb-portfolio-value sb-market-value': true }, dash), []);
  assert.deepEqual(missingRequirements('', {}, dash), ['sb-portfolio-value sb-market-value']);
});
test('a page with no requirements misses nothing', () => {
  assert.deepEqual(missingRequirements('', {}, { name: 'Trades', rail: 'Trades' }), []);
});
test('a missing label fails the visit; a v201 visit without the field keeps its verdict', () => {
  const ok = { firstDataMs: 900, calls: [], scanMs: [80], cells: 3, unlabelled: 0, timedOut: false };
  assert.equal(visitVerdict(ok).pass, true);
  const bad = visitVerdict({ ...ok, missing: ['daily bars through'] });
  assert.equal(bad.pass, false);
  assert.deepEqual(bad.reasons, ['missing label: daily bars through']);
});
test('PAGES keeps v201 order and appends the three snapshot pages', () => {
  assert.deepEqual(PAGES.map((p) => p.name),
    ['Dashboard', 'Trades', 'Trade detail', 'Watchlist', 'Risk', 'Analytics', 'Calendar']);
});
```

(`visitVerdict` is already imported at the top of the file by v201's tests.)

Run: `node --test <R>/frontend/scripts/admin-page-timing.test.mjs`
Expected: FAIL (`missingRequirements` is not exported; `PAGES` has four entries).

- [ ] **Step 2: Extend the probe** as fixed above. `missingRequirements` and `recordInputs` are each a helper under 40 lines. The preflight extension is one function, `preflightSnapshots(body)`, returning `null` or the message. Nothing on stdout or in the JSONL carries a credential, cookie, `.env` value or a full API body.

- [ ] **Step 3: Run the unit tests**

Run: `node --test <R>/frontend/scripts/admin-page-timing.test.mjs`
Expected: PASS (9 tests: v201's four plus these five).

- [ ] **Step 4: Run the probe against production in US regular hours**

Run during a weekday 15:30–22:00 Berlin, when auto-scans run (compute Berlin time from `date -u`; Git Bash has no zone data), with a Bash `timeout` of 2 400 000 ms:
`node <R>/frontend/scripts/admin-page-timing.mjs --out <scratchpad>/v204-timing`
Expected: exit 0. The preflight passes, and `page-timing.jsonl` has 24 lines (7 pages × 3 passes plus 3 `inputs` lines), or 16 lines plus a `scan skipped` line. If the scan pass was skipped, re-run with `--passes scan` later in the session. The plan is not done without a during-scan row. Exit 2 or 3 is reported to the controller as it is (never retried in a loop: the login limiter counts failures).

- [ ] **Step 5: Review the screenshots for the label check**

Open each `<pass>-<slug>.png` from the cold pass for Risk, Analytics, Calendar and the Dashboard. Confirm:
- Risk shows `FX rates as of …` and `daily bars through … close`, and each of the Portfolio heat, Risk metrics and correlation panels carries an age.
- Every displayed total, P&L and risk figure carries an age, `last close` or `as of` label. A filtered Analytics view (capture one by hand with `browse.mjs` on `/app/analytics?strategy=<any>`; read-only) shows `as of this request`.
- The P&L basis reads `pre-tax, before modelled frictions` beside Calendar P&L, the Analytics equity total and Risk's money drawdown.
- Heat shows money and percent of account.
- No null correlation or beta is drawn as `0`.
Note any figure drawn outside `sb-market-value` with no label as a finding, naming page and figure.

- [ ] **Step 6: Write the results document** `docs/superpowers/results/2026-10-29-v204-page-timing.md`

Sections:
- **Before.** The Risk, Analytics and Calendar rows (and the equity-curve row) of the "Before" table in `docs/superpowers/results/2026-10-29-v201-page-timing.md`, copied verbatim.
- **Deployed.** `git -C <R> rev-parse --short HEAD`, the `ui`/`bot` versions from the `inputs` lines, and the date.
- **After.** The `renderTable` output for all three passes.
- **Inputs per pass.** From each `inputs` line: scan running or not, Risk `computed_at`, `bars_meta.oldest`/`newest`/`stale_inputs`, and each snapshot key's `computed_at`, `stale_inputs` and `error`.
- **`/system/scan`.** The largest value seen in any pass.
- **Label check.** Per page: cells, unlabelled, missing requirements, and the Step 5 review's findings.
- **Excluded calls.** The out-of-scope chart calls with their times, for the record.
- **Verdict.**

Pass requires every Risk, Analytics, Calendar and Dashboard visit `PASS` in cold, warm and during-scan: first data ≤ 2 s, every in-scope page-load call ≤ 2 s, `/system/scan` ≤ 0.5 s, zero unlabelled figures and no missing label. A `FAIL` row (including a Trades, Trade detail or Watchlist regression) is listed with its reasons and reported to the controller, rather than claiming success. No credential, cookie or `.env` value appears in the document.

- [ ] **Step 7: Commit on `main`**

```bash
git -C <R> add frontend/scripts/admin-page-timing.mjs frontend/scripts/admin-page-timing.test.mjs docs/superpowers/results/2026-10-29-v204-page-timing.md
git -C <R> commit -m "docs(v204): post-deploy page timing and label check for Risk, Analytics, Calendar and the sparkline"
```
