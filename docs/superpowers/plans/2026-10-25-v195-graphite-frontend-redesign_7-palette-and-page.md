# v195 — Graphite, Part 7: the command palette and the page template

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-19:" -A 400 <this file>`.

**Scope of this part (V195-19; V195-20 is in Part 7b, `2026-10-25-v195-graphite-frontend-redesign_7b-command-palette.md`, and V195-21 in Part 7c, `2026-10-25-v195-graphite-frontend-redesign_7c-page-template.md`, split for the 1500-line cap; the scope below covers all three):** spec §3.1 and Phase 4. V195-19 builds the palette's data and its ranking as pure, separately tested pieces: a root `SearchIndexStore` that reads the **existing** watchlist and trades list endpoints lazily on first open (session cache, refresh after 60s, a failure flag), and `palette-items.ts`, which turns those rows, the nav model, the workspace tabs and the density preference into one flat item list and ranks it (prefix on ticker or id, then prefix on name, then substring; ties keep the group order). V195-20 mounts the palette in the shell: Ctrl/⌘K, `/` outside a text field, the top-bar trigger, and (through V195-18's `onSearchRequested()`) the phone search icon and the More sheet's search field; a centred overlay on desktop and tablet, a full-screen sheet on a phone; navigation and preferences only. V195-21 adds `sb-page`, the five-slot template every workspace moves onto in Phase 5, and with it the page's one `<h1>` (correction 9).

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave (read before editing).** Part 6's and Part 6c's "The state earlier tasks leave" lists cover everything up to V195-17, and Part 6's rule on `title` in new templates binds the new components here too (no `title`, `[title]` or `[attr.title]` binding in any `.ts` template; an `sb-icon` sits in an `aria-hidden` span, because its host carries a native `title`). On top of that:

- `frontend/src/app/shell/nav.ts` (V195-15): `NavEntry { path; label; icon }`, `NavGroup { id; label; entries }`, `NAV_GROUPS` (Monitor: Dashboard, Watchlist, Risk · Review: Trades, Calendar, Cancels · Insights: Analytics, Research, Reports · System: System, Versions; eleven entries, paths `/dashboard` … `/versions`), `PHONE_TABS`, `navEntryFor`, `breadcrumbFor`, `detailCrumb(ticker, id)` (`'NVDA #812'`, `'NVDA'`, `'#812'` or `''`).
- `frontend/src/app/routing/route-title.service.ts` (V195-15): `title()`, `subtitle()`, `detail()`, `set(title, subtitle, path = null)`, `setDetail(detail)`.
- `frontend/src/app/ui/density.service.ts` (V195-6): `RowDensity`, `DENSITY_PREF_KEY`, `DensityStorage`, `DENSITY_STORAGE`, `readDensity`, `DensityService` (`density()`, `set(d)`, writes `<html data-density>`).
- `frontend/src/app/ui/icon.ts` (V195-14): `'search'` in `ICON_NAMES`.
- `frontend/src/app/ui/button.ts`, `confirm-dialog.ts` (V195-8): `ButtonVariant` has `'danger-quiet'`; `ConfirmDialog.dangerVariant = input<'danger' | 'danger-quiet'>('danger-quiet')`.
- The shell after V195-18 (Part 6c's **Interfaces** block): `header.topbar` > `sb-breadcrumb.topbar-lead`, `div.status-cluster` (`margin-left: auto`; `sb-killswitch-chip`, `sb-freshness-chip`, `sb-connection-status`, `span.clock`), on a phone only `button.search-trigger`, `sb-profile-menu`, `sb-scan-progress`; `@if (isPhone()) { <sb-phone-tab-bar …/> <sb-more-sheet … (searchRequested)="onSearchRequested()" /> }` directly before `<sb-toast-host />`. `shell.ts` has `isPhone`, `moreOpen`, `toggleMore()`, `closeMore()` and `onSearchRequested()` (today it only calls `closeMore()`). `shell.spec.ts` has the helpers `Blank`, `shellProviders(routes)`, `readSource(path)`, imports `ViewportService`, `WritableSignal`, `signal`, `HttpTestingController`, `afterEach`, and ends with `describe('shell above phone width (v195 Phase 3)', ...)`.
- `frontend/src/app/ui/primitives.spec.ts`: the `no call site hand-rolls a button` / `form control` gates scan every template outside `ui/` (`callSites()`), `.html` included. The palette's combobox `<input>` is the one raw control V195-20 adds; it gets a justified `RAW_CONTROL_ALLOWLIST` entry. Every button in the palette and the trigger goes through `sb-button`.

v194 and V195-1..V195-18 edited several of these files: every step below names its edit by symbol or exact string, never by line number. Re-read each file before editing it.

---

# Phase 3 — Shell (continued): the command palette

### Task V195-19: `SearchIndexStore` (root, lazy, session cache, 60s refresh, failure flag) and palette items and ranking
**Model:** sonnet — one small root store over two existing GET endpoints and a file of pure functions; the care is in the ranking's tie-break, the store never fetching before the palette opens, and a failed read keeping the earlier cache.

**Files:**
- Create: `frontend/src/app/stores/search-index.store.ts`
- Create: `frontend/src/app/stores/search-index.store.spec.ts`
- Create: `frontend/src/app/shell/palette/palette-items.ts`
- Create: `frontend/src/app/shell/palette/palette-items.spec.ts`

**Interfaces:**
- Consumes: `ApiClient.tickers(): Observable<TickerList>` (`GET /api/v1/watchlist/tickers`, `TickerList { tickers: Ticker[] }`) and `ApiClient.trades(query: TradeQuery): Observable<TradeCollection>` (`GET /api/v1/trades`, `Collection<TradeRow> { items; total; page; per_page }`; `per_page` capped at 200 server-side; `created_at` is in the server's `SORTABLE`, `swingbot/admin/api_v1/trades.py`), both in `frontend/src/app/api/api-client.ts`; `Ticker { symbol; company_name: string | null; … }`, `TradeRow { id: string; status: string; ticker: string; strategy: string | null; opened_at: string | null; created_at: string | null; … }` (`api/models.ts`); `NAV_GROUPS`, `NavGroup`, `detailCrumb` (`shell/nav.ts`, V195-15); `RowDensity` (`ui/density.service.ts`, V195-6). Store pattern: `MarketIndexStore` (`stores/market-index.store.ts`, `signalStore({ providedIn: 'root' }, withState, withMethods)`).
- Produces (V195-20 consumes all of these):
  - `search-index.store.ts`: `SEARCH_INDEX_TTL_MS = 60_000`; `SEARCH_INDEX_TRADES_QUERY = { per_page: 200, sort: '-created_at' }`; `SearchIndexStore` (root; state `tickers: Ticker[]`, `trades: TradeRow[]`, `loadedAt: number | null`, `failed: boolean`; method `ensure(now?: number): void` — fetches both lists on its first call and again once `now - loadedAt > SEARCH_INDEX_TTL_MS`; never two reads in flight; a failed list sets `failed`, keeps that list's earlier rows and leaves `loadedAt` unchanged so the next open retries).
  - `palette-items.ts`: `type PaletteGroup = 'tickers' | 'trades' | 'pages' | 'preferences'`; `interface PaletteItem { key: string; group: PaletteGroup; label: string; sub?: string; route: string | null; queryParams?: Record<string, string>; density?: RowDensity; recency?: number }`; `PALETTE_GROUP_ORDER`; `PALETTE_GROUP_LABELS: Record<PaletteGroup, string>` (`Ticker`, `Trade`, `Page`, `Preference`); `TAB_PAGES: readonly PaletteItem[]` (every non-default workspace tab); `PREFERENCE_ITEMS: readonly PaletteItem[]` (`Density: Dense`, `Density: Comfortable`); `RECENT_TRADES = 5`; `pageItems(groups: readonly NavGroup[] = NAV_GROUPS): PaletteItem[]` (the rail entries, then `TAB_PAGES`); `tickerItems(tickers: readonly Ticker[]): PaletteItem[]`; `tradeItems(rows: readonly TradeRow[]): PaletteItem[]` (`/plans/:id` for a `PENDING` plan, else `/trades/:id`); `rankPaletteItems(query: string, items: readonly PaletteItem[]): PaletteItem[]`; `emptyQueryItems(items: readonly PaletteItem[]): PaletteItem[]` (the rail pages, then the five most recent trades).

**What changes, and what is already there.** The palette needs tickers and trades from the shell, but the stores that hold them (`TradesStore`, `WatchlistStore`, `TradeDetailStore`) are route-scoped, so the shell cannot inject them (staff-engineer advisory 1). `SearchIndexStore` is a new root store that reads the same two **existing** endpoints itself: nothing on load, both on the palette's first open, cached for the session, refreshed on an open more than 60s after the last good read. The trades read asks for the 200 most recently **created** rows (`-created_at`), not the most recently opened: an unfilled plan has no `opened_at` and the server sorts valueless rows last, so `-opened_at` would push every pending plan behind 200 filled trades on a book with hundreds of closed ones. No backend change, no new endpoint. The items file is pure: it never touches Angular, so ranking, routes and the "no destructive action" guarantee are pinned without a component. The `providers` System tab is listed in `TAB_PAGES` now; until V195-22 adds it to `SYSTEM_TABS` that link falls back to Settings, and the branch merges only at V195-36.

Ranking, as the spec words it (§3.1): an exact prefix on a ticker symbol or a trade id is tier 0; a prefix on a name (a company name, a page or preference label) is tier 1; a substring of the label or its sub-line is tier 2. Ties keep the group order Tickers, Trades & plans, Pages, Preferences, then the input order. A trade has no "name": it is found by its ticker or id, or by a substring of its status and strategy line.

- [ ] **Step 1: Write the failing item and ranking tests**

Create `$WT/frontend/src/app/shell/palette/palette-items.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { Ticker, TradeRow } from '../../api/models';
import { NAV_GROUPS } from '../nav';
import {
  PALETTE_GROUP_LABELS,
  PREFERENCE_ITEMS,
  PaletteItem,
  RECENT_TRADES,
  TAB_PAGES,
  emptyQueryItems,
  pageItems,
  rankPaletteItems,
  tickerItems,
  tradeItems,
} from './palette-items';

const ticker = (symbol: string, company_name: string | null): Ticker =>
  ({ symbol, company_name, open_trades: 0, closed_trades: 0 }) as Ticker;

const trade = (id: string, symbol: string, status: string, created_at: string | null, extra: Partial<TradeRow> = {}): TradeRow =>
  ({ id, ticker: symbol, status, strategy: 'RSI', created_at, opened_at: null, ...extra }) as TradeRow;

const labels = (items: readonly PaletteItem[]) => items.map((item) => item.label);
const RAIL = NAV_GROUPS.flatMap((group) => group.entries.map((entry) => entry.label));

describe('palette items (v195 §3.1)', () => {
  it('lists every rail entry as a page, in rail order, then the workspace tabs', () => {
    const pages = pageItems();
    expect(labels(pages.slice(0, RAIL.length))).toEqual(RAIL);
    expect(pages.slice(RAIL.length)).toEqual([...TAB_PAGES]);
    expect(pages.every((item) => item.group === 'pages')).toBe(true);
    expect(pages.find((item) => item.label === 'Risk')).toMatchObject({ route: '/risk', sub: 'Monitor' });
  });

  it('opens a workspace tab through its ?tab= value, never the default tab', () => {
    expect(TAB_PAGES.find((item) => item.label === 'Logs'))
      .toMatchObject({ route: '/system', queryParams: { tab: 'logs' }, sub: 'System' });
    expect(TAB_PAGES.map((item) => `${item.route}?tab=${item.queryParams!['tab']}`)).toEqual([
      '/analytics?tab=attribution', '/analytics?tab=execution', '/analytics?tab=edge',
      '/analytics?tab=pipeline', '/analytics?tab=tuning', '/analytics?tab=partials',
      '/reports?tab=gates',
      '/system?tab=scan', '/system?tab=providers', '/system?tab=logs',
      '/watchlist?tab=earnings',
    ]);
  });

  it('makes a ticker item from the watchlist row, linking its detail page', () => {
    expect(tickerItems([ticker('NVDA', 'NVIDIA Corp'), ticker('SPY', null)])).toEqual([
      { key: 'ticker:NVDA', group: 'tickers', label: 'NVDA', sub: 'NVIDIA Corp', route: '/watchlist/NVDA' },
      { key: 'ticker:SPY', group: 'tickers', label: 'SPY', route: '/watchlist/SPY' },
    ]);
  });

  it('sends an unfilled plan to /plans/:id and everything else to /trades/:id', () => {
    const [plan, open, closed] = tradeItems([
      trade('901', 'AMD', 'PENDING', '2026-10-26T09:00:00Z'),
      trade('812', 'NVDA', 'ACTIVE', '2026-10-20T09:00:00Z'),
      trade('700', 'MSFT', 'CLOSED', null, { opened_at: '2026-09-01T14:30:00Z', strategy: null }),
    ]);
    expect(plan).toEqual({
      key: 'trade:901', group: 'trades', label: 'AMD #901', sub: 'Plan · RSI',
      route: '/plans/901', recency: Date.parse('2026-10-26T09:00:00Z'),
    });
    expect(open).toMatchObject({ label: 'NVDA #812', sub: 'Active · RSI', route: '/trades/812' });
    // No created_at: the open time stands in. No strategy: the status alone.
    expect(closed).toMatchObject({ sub: 'Closed', route: '/trades/700', recency: Date.parse('2026-09-01T14:30:00Z') });
  });

  it('gives a row with no readable time a recency of 0, so it sorts last and never throws', () => {
    expect(tradeItems([trade('1', 'X', 'ACTIVE', 'not a date')])[0].recency).toBe(0);
    expect(tradeItems([trade('2', 'Y', 'ACTIVE', null)])[0].recency).toBe(0);
  });

  it('offers the density preference both ways, applied in place', () => {
    expect(PREFERENCE_ITEMS.map((item) => [item.label, item.density, item.route])).toEqual([
      ['Density: Dense', 'dense', null],
      ['Density: Comfortable', 'comfortable', null],
    ]);
    expect(PALETTE_GROUP_LABELS).toEqual({ tickers: 'Ticker', trades: 'Trade', pages: 'Page', preferences: 'Preference' });
  });

  it('registers no destructive or money-moving action: every item navigates or sets density', () => {
    const all = [
      ...tickerItems([ticker('NVDA', 'NVIDIA Corp')]),
      ...tradeItems([trade('812', 'NVDA', 'ACTIVE', null)]),
      ...pageItems(),
      ...PREFERENCE_ITEMS,
    ];
    const allowedKeys = new Set(['key', 'group', 'label', 'sub', 'route', 'queryParams', 'density', 'recency']);
    for (const item of all) {
      // An item is data, never a callback: no field can carry an action.
      expect(Object.keys(item).filter((key) => !allowedKeys.has(key)), item.key).toEqual([]);
      expect(Object.values(item).some((value) => typeof value === 'function'), item.key).toBe(false);
      expect(item.route !== null || item.density !== undefined, item.key).toBe(true);
      expect(`${item.label} ${item.sub ?? ''} ${item.route ?? ''}`, item.key)
        .not.toMatch(/kill|halt|restart|stop bot|clear|delete|close all|discard|scan now|order/i);
    }
  });
});

describe('palette ranking (v195 §3.1)', () => {
  const items: PaletteItem[] = [
    ...tickerItems([ticker('ARIS', 'Aris Water'), ticker('RIOT', 'Riot Platforms'), ticker('AAPL', 'Apple Inc')]),
    ...tradeItems([trade('812', 'NVDA', 'ACTIVE', null), trade('8120', 'AMD', 'CLOSED', null)]),
    ...pageItems(),
    ...PREFERENCE_ITEMS,
  ];

  it('ranks a ticker prefix first, then a name prefix, then a substring', () => {
    // RIOT: ticker prefix. Risk: page-name prefix. ARIS (a ticker) and
    // Attribution (a tab) hold "ri" only inside: substrings, tickers first.
    const ranked = labels(rankPaletteItems('ri', items));
    expect(ranked.slice(0, 2)).toEqual(['RIOT', 'Risk']);
    expect(ranked.indexOf('ARIS')).toBeGreaterThan(ranked.indexOf('Risk'));
    expect(ranked.indexOf('ARIS')).toBeLessThan(ranked.indexOf('Attribution'));
  });

  it('matches a company-name prefix below every ticker prefix', () => {
    expect(labels(rankPaletteItems('apple', items))).toEqual(['AAPL']);
    // ARIS and AAPL (tickers, input order), then AMD #8120 (a trade ticker):
    // all tier 0, so group order then input order decides.
    expect(labels(rankPaletteItems('a', items)).slice(0, 3)).toEqual(['ARIS', 'AAPL', 'AMD #8120']);
  });

  it('matches a trade by ticker or by id, with or without the #', () => {
    expect(labels(rankPaletteItems('nvda', items))[0]).toBe('NVDA #812');
    expect(labels(rankPaletteItems('812', items))).toEqual(['NVDA #812', 'AMD #8120']);
    expect(labels(rankPaletteItems('#8120', items))).toEqual(['AMD #8120']);
  });

  it('keeps the group order on a tie: pages before preferences', () => {
    // Dashboard and Density: ... are both name prefixes of "d" (tier 1).
    const ranked = labels(rankPaletteItems('d', items));
    expect(ranked.indexOf('Dashboard')).toBeLessThan(ranked.indexOf('Density: Dense'));
    expect(ranked.indexOf('Density: Dense')).toBeLessThan(ranked.indexOf('Density: Comfortable'));
  });

  it('is case-insensitive and ignores surrounding spaces', () => {
    expect(labels(rankPaletteItems('  RISK ', items))[0]).toBe('Risk');
  });

  it('returns nothing for an empty query or a symbol that is not on the watchlist', () => {
    expect(rankPaletteItems('', items)).toEqual([]);
    expect(rankPaletteItems('   ', items)).toEqual([]);
    expect(rankPaletteItems('ZZZZ', items)).toEqual([]);
  });

  it('never reorders the list it is given', () => {
    const before = labels(items);
    rankPaletteItems('ri', items);
    expect(labels(items)).toEqual(before);
  });
});

describe('the empty query (v195 §3.1)', () => {
  it('shows the rail pages, then the five most recent trades, newest first', () => {
    const rows = ['01', '05', '03', '07', '02', '06', '04'].map((day, i) =>
      trade(String(100 + i), `T${day}`, 'ACTIVE', `2026-10-${day}T10:00:00Z`));
    const shown = emptyQueryItems([...tickerItems([ticker('NVDA', null)]), ...tradeItems(rows), ...pageItems(), ...PREFERENCE_ITEMS]);
    expect(labels(shown.slice(0, RAIL.length))).toEqual(RAIL);
    expect(labels(shown.slice(RAIL.length))).toEqual(['T07 #103', 'T06 #105', 'T05 #101', 'T04 #106', 'T03 #102']);
    expect(shown).toHaveLength(RAIL.length + RECENT_TRADES);
  });

  it('shows the pages alone before the trades have loaded', () => {
    const shown = emptyQueryItems(pageItems());
    expect(labels(shown)).toEqual(RAIL);
  });
});
```

- [ ] **Step 2: Write the failing store tests**

Create `$WT/frontend/src/app/stores/search-index.store.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { SEARCH_INDEX_TTL_MS, SearchIndexStore } from './search-index.store';

const TICKERS_URL = '/api/v1/watchlist/tickers';
const TRADES_URL = '/api/v1/trades';
const T0 = Date.parse('2026-10-27T12:00:00Z');

const tickersBody = (...symbols: string[]) => ({
  tickers: symbols.map((symbol) => ({ symbol, company_name: null, open_trades: 0, closed_trades: 0 })),
});
const tradesBody = (...ids: string[]) => ({
  items: ids.map((id) => ({ id, ticker: 'NVDA', status: 'ACTIVE', strategy: null, created_at: null, opened_at: null })),
  total: ids.length, page: 1, per_page: 200,
});
const FAIL_BODY = { error: { code: 'unavailable', message: 'down' } };
const FAIL_STATUS = { status: 503, statusText: 'Unavailable' };

describe('SearchIndexStore (v195 §3.1)', () => {
  let store: InstanceType<typeof SearchIndexStore>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    store = TestBed.inject(SearchIndexStore);
    http = TestBed.inject(HttpTestingController);
  });

  const answer = (symbols: string[], ids: string[]) => {
    http.expectOne((r) => r.url === TICKERS_URL).flush(tickersBody(...symbols));
    http.expectOne((r) => r.url === TRADES_URL).flush(tradesBody(...ids));
  };

  it('fetches nothing until the palette asks', () => {
    http.expectNone(() => true);
    expect(store.loadedAt()).toBeNull();
    expect(store.failed()).toBe(false);
  });

  it('reads the watchlist and the 200 most recently created trades on the first open', () => {
    store.ensure(T0);
    const trades = http.expectOne((r) => r.url === TRADES_URL);
    expect(trades.request.method).toBe('GET');
    expect(trades.request.params.get('per_page')).toBe('200');
    expect(trades.request.params.get('sort')).toBe('-created_at');
    http.expectOne((r) => r.url === TICKERS_URL).flush(tickersBody('NVDA', 'AMD'));
    trades.flush(tradesBody('812'));
    expect(store.tickers().map((t) => t.symbol)).toEqual(['NVDA', 'AMD']);
    expect(store.trades().map((t) => t.id)).toEqual(['812']);
    expect(store.loadedAt()).toBe(T0);
    expect(store.failed()).toBe(false);
  });

  it('serves the cache for 60s and refreshes on the first open after that', () => {
    store.ensure(T0);
    answer(['NVDA'], ['812']);

    store.ensure(T0 + SEARCH_INDEX_TTL_MS);
    http.expectNone(() => true);

    store.ensure(T0 + SEARCH_INDEX_TTL_MS + 1);
    answer(['NVDA', 'TSLA'], ['812', '813']);
    expect(store.tickers()).toHaveLength(2);
    expect(store.loadedAt()).toBe(T0 + SEARCH_INDEX_TTL_MS + 1);
  });

  it('never starts a second read while one is in flight', () => {
    store.ensure(T0);
    store.ensure(T0 + 1);
    expect(http.match((r) => r.url === TICKERS_URL)).toHaveLength(1);
    expect(http.match((r) => r.url === TRADES_URL)).toHaveLength(1);
  });

  it('flags a failed read, keeps the earlier rows and retries on the next open', () => {
    store.ensure(T0);
    answer(['NVDA'], ['812']);

    const later = T0 + SEARCH_INDEX_TTL_MS + 1;
    store.ensure(later);
    http.expectOne((r) => r.url === TICKERS_URL).flush(FAIL_BODY, FAIL_STATUS);
    http.expectOne((r) => r.url === TRADES_URL).flush(tradesBody('812', '813'));
    expect(store.failed()).toBe(true);
    expect(store.tickers().map((t) => t.symbol)).toEqual(['NVDA']);
    // The list that did answer is still taken.
    expect(store.trades()).toHaveLength(2);
    // Not stamped: the next open tries again rather than waiting 60s.
    expect(store.loadedAt()).toBe(T0);

    store.ensure(later + 1);
    answer(['NVDA', 'AMD'], ['812', '813']);
    expect(store.failed()).toBe(false);
    expect(store.loadedAt()).toBe(later + 1);
  });

  it('starts empty and flagged when the very first read fails, so pages still serve', () => {
    store.ensure(T0);
    http.expectOne((r) => r.url === TICKERS_URL).flush(FAIL_BODY, FAIL_STATUS);
    http.expectOne((r) => r.url === TRADES_URL).flush(FAIL_BODY, FAIL_STATUS);
    expect(store.tickers()).toEqual([]);
    expect(store.trades()).toEqual([]);
    expect(store.failed()).toBe(true);
    expect(store.loadedAt()).toBeNull();
  });

  it('treats a body without its list as empty, not as a crash', () => {
    store.ensure(T0);
    http.expectOne((r) => r.url === TICKERS_URL).flush({});
    http.expectOne((r) => r.url === TRADES_URL).flush({});
    expect(store.tickers()).toEqual([]);
    expect(store.trades()).toEqual([]);
    expect(store.failed()).toBe(false);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/palette/palette-items.spec.ts --include src/app/stores/search-index.store.spec.ts
```

Expected: FAIL. Neither spec compiles: `./palette-items` and `./search-index.store` do not exist.

- [ ] **Step 4: Create `palette-items.ts`**

Create `$WT/frontend/src/app/shell/palette/palette-items.ts`:

```ts
import { Ticker, TradeRow } from '../../api/models';
import { RowDensity } from '../../ui/density.service';
import { NAV_GROUPS, NavGroup, detailCrumb } from '../nav';

/**
 * The command palette's items and ranking -- v195 §3.1.
 *
 * Pure: no Angular, no store. The palette component feeds it the rows
 * `SearchIndexStore` holds and renders what comes back, so the ranking, the
 * routes and the one hard rule (navigation and preferences only, never an
 * action) are pinned here without a fixture.
 *
 * An item is data, never a callback: it names a route (with optional query
 * params) or a density, nothing else. Nothing in this file can make an item
 * that scans, restarts, halts, deletes or orders, and palette-items.spec.ts
 * fails if a field that could carry one ever appears.
 */

export type PaletteGroup = 'tickers' | 'trades' | 'pages' | 'preferences';

export interface PaletteItem {
  /** Unique across groups: `ticker:NVDA`, `trade:812`, `page:/risk`, ... */
  key: string;
  group: PaletteGroup;
  label: string;
  sub?: string;
  /** A path to navigate to, or null for a preference applied in place. */
  route: string | null;
  queryParams?: Record<string, string>;
  density?: RowDensity;
  /** Epoch ms; trades only, for the empty query's "most recent". */
  recency?: number;
}

/** The tie-break order: the spec's table order (§3.1). */
export const PALETTE_GROUP_ORDER: readonly PaletteGroup[] = ['tickers', 'trades', 'pages', 'preferences'];

/** The kind each result row names on its right edge. */
export const PALETTE_GROUP_LABELS: Record<PaletteGroup, string> = {
  tickers: 'Ticker',
  trades: 'Trade',
  pages: 'Page',
  preferences: 'Preference',
};

/** How many trades the empty query shows. */
export const RECENT_TRADES = 5;

const tab = (route: string, page: string, id: string, label: string): PaletteItem => ({
  key: `tab:${route}?${id}`,
  group: 'pages',
  label,
  sub: page,
  route,
  queryParams: { tab: id },
});

/**
 * Every workspace tab a `?tab=` value opens, minus each workspace's default
 * tab (the page entry already lands there). Ids and labels match the tab
 * bars in analytics.ts, reports.ts, system.ts and watchlist.ts. `providers`
 * is V195-22's; until it lands the System route falls back to Settings.
 */
export const TAB_PAGES: readonly PaletteItem[] = [
  tab('/analytics', 'Analytics', 'attribution', 'Attribution'),
  tab('/analytics', 'Analytics', 'execution', 'Execution'),
  tab('/analytics', 'Analytics', 'edge', 'Edge'),
  tab('/analytics', 'Analytics', 'pipeline', 'Pipeline'),
  tab('/analytics', 'Analytics', 'tuning', 'Tuning'),
  tab('/analytics', 'Analytics', 'partials', 'Partials'),
  tab('/reports', 'Reports', 'gates', 'Gate counterfactual'),
  tab('/system', 'System', 'scan', 'Scan'),
  tab('/system', 'System', 'providers', 'Providers'),
  tab('/system', 'System', 'logs', 'Logs'),
  tab('/watchlist', 'Watchlist', 'earnings', 'Earnings'),
];

/** Density, both ways (spec §1.4). Applied in place; no route. */
export const PREFERENCE_ITEMS: readonly PaletteItem[] = [
  { key: 'pref:density:dense', group: 'preferences', label: 'Density: Dense', sub: '28px rows on desktop', route: null, density: 'dense' },
  { key: 'pref:density:comfortable', group: 'preferences', label: 'Density: Comfortable', sub: '44px rows on desktop', route: null, density: 'comfortable' },
];

/** Every rail entry, in rail order and labelled with its group, then the tabs. */
export function pageItems(groups: readonly NavGroup[] = NAV_GROUPS): PaletteItem[] {
  const entries = groups.flatMap((group) =>
    group.entries.map((entry): PaletteItem => ({
      key: `page:${entry.path}`,
      group: 'pages',
      label: entry.label,
      sub: group.label,
      route: entry.path,
    })),
  );
  return [...entries, ...TAB_PAGES];
}

/** One item per watchlist symbol, opening its detail page. */
export function tickerItems(tickers: readonly Ticker[]): PaletteItem[] {
  return tickers.map((row): PaletteItem => ({
    key: `ticker:${row.symbol}`,
    group: 'tickers',
    label: row.symbol,
    ...(row.company_name ? { sub: row.company_name } : {}),
    route: `/watchlist/${row.symbol}`,
  }));
}

const capitalised = (word: string): string => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();

/** Epoch ms of an ISO time, or 0 when there is none or it does not parse. */
function epochOf(iso: string | null | undefined): number {
  const at = iso ? Date.parse(iso) : Number.NaN;
  return Number.isFinite(at) ? at : 0;
}

/**
 * One item per trade or plan. An unfilled plan (`PENDING`) opens the plan
 * page (`/plans/:id`, v151); anything filled opens the trade record. Labelled
 * `NVDA #812`, like the breadcrumb's detail segment.
 */
export function tradeItems(rows: readonly TradeRow[]): PaletteItem[] {
  return rows.map((row): PaletteItem => {
    const status = (row.status ?? '').toUpperCase();
    const isPlan = status === 'PENDING';
    const state = isPlan ? 'Plan' : capitalised(status);
    return {
      key: `trade:${row.id}`,
      group: 'trades',
      label: detailCrumb(row.ticker, row.id),
      sub: [state, row.strategy].filter(Boolean).join(' · '),
      route: `/${isPlan ? 'plans' : 'trades'}/${row.id}`,
      recency: epochOf(row.created_at ?? row.opened_at),
    };
  });
}

/** The query as matched: trimmed, lower-case, a leading `#` dropped. */
function normalised(query: string): string {
  return query.trim().toLowerCase().replace(/^#/, '');
}

/** Ticker symbols and trade ids: the "exact prefix" tier. */
function codesOf(item: PaletteItem): string[] {
  if (item.group === 'tickers') return [item.label];
  if (item.group === 'trades') return [item.label.split(' ')[0], item.key.slice('trade:'.length)];
  return [];
}

/** The "name" a prefix is matched on: a company name, a page or preference label. */
function nameOf(item: PaletteItem): string {
  if (item.group === 'tickers') return item.sub ?? '';
  if (item.group === 'trades') return '';
  return item.label;
}

/** 0 code prefix, 1 name prefix, 2 substring, null no match. */
function tierOf(query: string, item: PaletteItem): number | null {
  if (codesOf(item).some((code) => code.toLowerCase().replace(/^#/, '').startsWith(query))) return 0;
  if (nameOf(item).toLowerCase().startsWith(query)) return 1;
  return `${item.label} ${item.sub ?? ''}`.toLowerCase().includes(query) ? 2 : null;
}

/**
 * Rank by tier, then group order, then the order the items came in. Returns
 * a new list; an empty query matches nothing (the caller shows
 * `emptyQueryItems` instead).
 */
export function rankPaletteItems(query: string, items: readonly PaletteItem[]): PaletteItem[] {
  const q = normalised(query);
  if (!q) return [];
  const groupRank = (item: PaletteItem) => PALETTE_GROUP_ORDER.indexOf(item.group);
  return items
    .map((item, index) => ({ item, index, tier: tierOf(q, item) }))
    .filter((hit): hit is { item: PaletteItem; index: number; tier: number } => hit.tier !== null)
    .sort((a, b) => a.tier - b.tier || groupRank(a.item) - groupRank(b.item) || a.index - b.index)
    .map((hit) => hit.item);
}

/** The empty query: the rail pages (no tabs), then the five newest trades. */
export function emptyQueryItems(items: readonly PaletteItem[]): PaletteItem[] {
  const pages = items.filter((item) => item.group === 'pages' && !item.queryParams);
  const recent = items
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.group === 'trades')
    .sort((a, b) => (b.item.recency ?? 0) - (a.item.recency ?? 0) || a.index - b.index)
    .slice(0, RECENT_TRADES)
    .map(({ item }) => item);
  return [...pages, ...recent];
}
```

- [ ] **Step 5: Create `search-index.store.ts`**

Create `$WT/frontend/src/app/stores/search-index.store.ts`:

```ts
import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { Observable, catchError, forkJoin, map, of } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { Ticker, TradeRow } from '../api/models';

/** An open more than this long after the last good read refreshes it. */
export const SEARCH_INDEX_TTL_MS = 60_000;

/**
 * The trades read. Newest *created* first, not newest opened: an unfilled
 * plan has no `opened_at` and the server sorts valueless rows last, so
 * `-opened_at` would push every pending plan behind 200 filled trades. 200
 * is the server's `per_page` cap.
 */
export const SEARCH_INDEX_TRADES_QUERY = { per_page: 200, sort: '-created_at' } as const;

interface SearchIndexSlice {
  tickers: Ticker[];
  trades: TradeRow[];
  /** When the last read that fully answered arrived; null before one has. */
  loadedAt: number | null;
  /** The last read lost at least one list; the palette says so in one line. */
  failed: boolean;
}

/**
 * The command palette's tickers and trades -- v195 §3.1.
 *
 * Root-provided because the palette lives in the shell, and the stores that
 * hold these rows (`TradesStore`, `WatchlistStore`, `TradeDetailStore`) are
 * route-scoped. It reads the same two existing endpoints itself; no new
 * backend surface.
 *
 * Lazy: nothing is fetched until the palette first opens (`ensure`), so a
 * session that never opens it costs nothing. Cached for the session and
 * refreshed on an open more than `SEARCH_INDEX_TTL_MS` after the last good
 * read. A list that fails keeps its earlier rows, sets `failed`, and leaves
 * `loadedAt` alone so the next open tries again; the palette still serves
 * pages and preferences meanwhile.
 *
 * Errors are swallowed per list, with no toast: a search box that cannot
 * list tickers is not worth interrupting whatever page is open.
 */
export const SearchIndexStore = signalStore(
  { providedIn: 'root' },
  withState<SearchIndexSlice>({ tickers: [], trades: [], loadedAt: null, failed: false }),
  withMethods((store, api = inject(ApiClient)) => {
    let inFlight = false;

    const isFresh = (now: number): boolean => {
      const at = store.loadedAt();
      return at !== null && now - at <= SEARCH_INDEX_TTL_MS;
    };

    /** One list, or null when its read failed. */
    const orNull = <T>(source: Observable<T[]>): Observable<T[] | null> =>
      source.pipe(catchError(() => of(null)));

    const ensure = (now: number = Date.now()): void => {
      if (inFlight || isFresh(now)) return;
      inFlight = true;
      forkJoin({
        tickers: orNull(api.tickers().pipe(map((body) => body?.tickers ?? []))),
        trades: orNull(api.trades({ ...SEARCH_INDEX_TRADES_QUERY }).pipe(map((body) => body?.items ?? []))),
      }).subscribe(({ tickers, trades }) => {
        inFlight = false;
        const failed = tickers === null || trades === null;
        patchState(store, {
          tickers: tickers ?? store.tickers(),
          trades: trades ?? store.trades(),
          failed,
          loadedAt: failed ? store.loadedAt() : now,
        });
      });
    };

    return { ensure };
  }),
);
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/palette/palette-items.spec.ts --include src/app/stores/search-index.store.spec.ts --include src/app/ui/primitives.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `primitives.spec.ts` is in the run because it scans every source outside `ui/` for colour literals: neither new file holds one. If the `'a'` ranking case orders `AAPL` before `ARIS`, the sort lost its stability: the comparator must end with `a.index - b.index`. If the store's failure case finds `loadedAt` stamped, the `failed ? store.loadedAt() : now` branch was inverted.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 7: Close**

Close: standard (test: `frontend/src/app/shell/palette/palette-items.spec.ts`), plus `frontend/src/app/stores/search-index.store.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/stores/search-index.store.ts frontend/src/app/stores/search-index.store.spec.ts frontend/src/app/shell/palette/palette-items.ts frontend/src/app/shell/palette/palette-items.spec.ts
git -C "$WT" commit -m "feat(v195): search index store and palette items with ranking (V195-19)" -m "Spec §3.1 and staff-engineer advisory 1: a root SearchIndexStore reads the existing watchlist and trades list endpoints on the palette's first open (no new endpoint), caches them for the session, refreshes after 60s and flags a failed read while keeping the earlier rows. Trades are read newest-created first so pending plans are never pushed past the 200-row cap. palette-items.ts turns tickers, trades and plans, the rail pages, the workspace tabs and the density preference into plain data items, ranked prefix on ticker or id, then prefix on name, then substring, ties in group order; the empty query is the rail pages and the five newest trades. Items carry a route or a density and nothing else, so the palette cannot hold an action." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

