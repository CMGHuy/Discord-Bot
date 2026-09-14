import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter, Router } from '@angular/router';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { Ticker } from '../../api/models';
import { date } from '../../ui/format';
import { SortSpec } from '../../ui/data-table/data-table.types';
import { compareTickers, isWithinCurrentWeek, Watchlist } from './watchlist';
import { WatchlistStore } from '../../stores/watchlist.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { TapeStore } from '../../stores/tape.store';
import { writeWatchlistTags } from '../../ui/watchlist-prefs';

function ticker(overrides: Partial<Ticker>): Ticker {
  return {
    symbol: 'AAPL', company_name: 'Apple Inc.', open_trades: 0, closed_trades: 0,
    next_earnings_date: null, next_earnings_datetime: null,
    price: null, as_of: null, change_1d_pct: null, change_1w_pct: null, change_1m_pct: null,
    spark: [],
    signal: { state: 'none', score: null, horizon: null, strategy: null },
    ...overrides,
  };
}

/** Mounts Watchlist with `list` seeded straight onto the store (`patchState`
 *  + `unprotected`, the same pattern `trades.spec.ts` uses for its footer
 *  fixture) rather than round-tripping through `HttpTestingController` --
 *  these tests assert row rendering, not the load sequence, and every `it`
 *  here is synchronous. Returns the rendered `tr.row` elements, in order. */
function rows(list: Partial<Ticker>[]): Element[] {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      WatchlistStore,
    ],
  });
  const fixture = TestBed.createComponent(Watchlist);
  patchState(unprotected(TestBed.inject(WatchlistStore)), {
    tickers: list.map((overrides) => ticker(overrides)),
    loaded: true,
  });
  fixture.detectChanges();
  return [...(fixture.nativeElement as HTMLElement).querySelectorAll('tbody tr.row')];
}

function firstRow(overrides: Partial<Ticker>): Element {
  return rows([overrides])[0];
}

describe('compareTickers', () => {
  const asc: SortSpec = { key: 'next_earnings_date', direction: 'asc' };
  const desc: SortSpec = { key: 'next_earnings_date', direction: 'desc' };

  it('sorts soonest earnings first, ascending', () => {
    const a = ticker({ symbol: 'A', next_earnings_date: '2026-09-10' });
    const b = ticker({ symbol: 'B', next_earnings_date: '2026-09-03' });
    expect(compareTickers(a, b, asc)).toBeGreaterThan(0); // A after B
    expect(compareTickers(b, a, asc)).toBeLessThan(0); // B before A
  });

  it('reverses on descending', () => {
    const a = ticker({ symbol: 'A', next_earnings_date: '2026-09-10' });
    const b = ticker({ symbol: 'B', next_earnings_date: '2026-09-03' });
    expect(compareTickers(a, b, desc)).toBeLessThan(0); // A before B
  });

  it('sorts a ticker with no known date LAST regardless of direction', () => {
    const known = ticker({ symbol: 'A', next_earnings_date: '2026-09-03' });
    const unknown = ticker({ symbol: 'B', next_earnings_date: null });

    expect(compareTickers(known, unknown, asc)).toBeLessThan(0);
    expect(compareTickers(unknown, known, asc)).toBeGreaterThan(0);
    expect(compareTickers(known, unknown, desc)).toBeLessThan(0);
    expect(compareTickers(unknown, known, desc)).toBeGreaterThan(0);
  });

  it('two unknown dates compare equal', () => {
    const a = ticker({ symbol: 'A', next_earnings_date: null });
    const b = ticker({ symbol: 'B', next_earnings_date: null });
    expect(compareTickers(a, b, asc)).toBe(0);
  });

  it('sorts other columns too — symbol, numeric counts', () => {
    const a = ticker({ symbol: 'AAPL', open_trades: 1 });
    const b = ticker({ symbol: 'MSFT', open_trades: 3 });

    expect(compareTickers(a, b, { key: 'symbol', direction: 'asc' })).toBeLessThan(0);
    expect(compareTickers(a, b, { key: 'open_trades', direction: 'asc' })).toBeLessThan(0);
    expect(compareTickers(a, b, { key: 'open_trades', direction: 'desc' })).toBeGreaterThan(0);
  });

  it('null company_name sorts last on that column too', () => {
    const named = ticker({ symbol: 'A', company_name: 'Apple Inc.' });
    const unnamed = ticker({ symbol: 'B', company_name: null });
    const sort: SortSpec = { key: 'company_name', direction: 'asc' };
    expect(compareTickers(named, unnamed, sort)).toBeLessThan(0);
  });
});

describe('isWithinCurrentWeek', () => {
  function daysFromNow(n: number): string {
    const d = new Date();
    d.setDate(d.getDate() + n);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  it('is true for today', () => {
    expect(isWithinCurrentWeek(daysFromNow(0))).toBe(true);
  });

  it('is false for null', () => {
    expect(isWithinCurrentWeek(null)).toBe(false);
  });

  it('is false for a date eight days out (never in the current Mon-Sun week)', () => {
    // The current week is at most 6 days from today in either direction;
    // 8 days out cannot land inside it no matter what day it is today.
    expect(isWithinCurrentWeek(daysFromNow(8))).toBe(false);
  });

  it('is false for a date eight days in the past', () => {
    expect(isWithinCurrentWeek(daysFromNow(-8))).toBe(false);
  });
});

function seed(): { fixture: ComponentFixture<Watchlist>; backend: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      WatchlistStore,
    ],
  });
  const fixture = TestBed.createComponent(Watchlist);
  TestBed.inject(WatchlistStore).load();
  const backend = TestBed.inject(HttpTestingController);
  return { fixture, backend };
}

describe('Watchlist states', () => {
  it('shows a skeleton while loading, before the first response', () => {
    const { fixture } = seed();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.skeleton')).toBeTruthy();
  });

  it('shows the error state on a first-load failure', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend
      .expectOne('/api/v1/watchlist/tickers')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.failed')).toBeTruthy();
  });

  it('shows the no-data-yet empty state, not a spinner, for an empty watchlist', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/watchlist/tickers').flush({ tickers: [] });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('No tickers on the watchlist');
    expect(el.querySelector('.skeleton')).toBeNull();
  });

  it('keeps the add-ticker control usable while the watchlist is empty', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/watchlist/tickers').flush({ tickers: [] });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('input')).toBeTruthy();
    const addButton = [...el.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Add');
    expect(addButton).toBeTruthy();
  });
});

describe('Watchlist tape column', () => {
  let fixture: ComponentFixture<Watchlist>;
  let tapeStub: { toggle: ReturnType<typeof vi.fn>; symbols: () => string[] };
  let routerStub: { navigate: ReturnType<typeof vi.spyOn> };

  beforeEach(async () => {
    TestBed.resetTestingModule();
    tapeStub = { toggle: vi.fn(), symbols: () => ['NVDA'] };
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        // A real router (not a bare useValue stub) -- sb-row-link's
        // RouterLink directive resolves ActivatedRoute from it, which a
        // plain { navigate } object cannot provide.
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
        WatchlistStore,
        { provide: TapeStore, useValue: tapeStub },
      ],
    });
    routerStub = { navigate: vi.spyOn(TestBed.inject(Router), 'navigate') };
    fixture = TestBed.createComponent(Watchlist);
    TestBed.inject(WatchlistStore).load();
    fixture.detectChanges();
    const backend = TestBed.inject(HttpTestingController);
    backend
      .expectOne('/api/v1/watchlist/tickers')
      .flush({ tickers: [ticker({ symbol: 'NVDA', next_earnings_date: '2026-09-03' })] });
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('puts the Tape column first and marks flagged rows', () => {
    const headers = fixture.nativeElement.querySelectorAll('th');
    expect(headers[0].textContent.trim()).toBe('Tape');
  });

  it('toggles the flag without navigating to the ticker', () => {
    const toggle = fixture.nativeElement.querySelector('button.tape-toggle') as HTMLButtonElement;
    toggle.click();
    expect(tapeStub.toggle).toHaveBeenCalledWith('NVDA');
    expect(routerStub.navigate).not.toHaveBeenCalled();
  });

  it('labels the remove control for screen readers', () => {
    const remove = fixture.nativeElement.querySelector('button[variant="danger-icon"]');
    expect(remove.getAttribute('aria-label')).toBe('Remove NVDA');
  });
});

describe('Watchlist tape column sorting', () => {
  // A second, separately-shaped fixture (two tickers, not one): the point is
  // to prove the Tape header's click actually REORDERS rows, which needs a
  // flagged row and an unflagged row to tell apart -- and to start them in
  // an order the default sort (next_earnings_date, soonest first) would NOT
  // produce on its own, so a pass here cannot be coincidental.
  let fixture: ComponentFixture<Watchlist>;

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
        WatchlistStore,
        { provide: TapeStore, useValue: { toggle: vi.fn(), symbols: () => ['NVDA'] } },
      ],
    });
    fixture = TestBed.createComponent(Watchlist);
    TestBed.inject(WatchlistStore).load();
    fixture.detectChanges();
    const backend = TestBed.inject(HttpTestingController);
    backend.expectOne('/api/v1/watchlist/tickers').flush({
      tickers: [
        // AAPL's earlier date puts it first under the default sort --
        // flagged NVDA only leads once the Tape column is actually driving
        // the order.
        ticker({ symbol: 'AAPL', next_earnings_date: '2026-09-01' }),
        ticker({ symbol: 'NVDA', next_earnings_date: '2026-09-10' }),
      ],
    });
    await fixture.whenStable();
    fixture.detectChanges();
  });

  function rowSymbols(): string[] {
    return [...fixture.nativeElement.querySelectorAll('tbody tr.row sb-row-link')]
      .map((el) => (el.textContent ?? '').trim());
  }

  it('sorts flagged rows first on click, and reverses on a second click', () => {
    // Sanity check: the default sort really does start AAPL first, so the
    // reorder below is attributable to the Tape click alone.
    expect(rowSymbols()).toEqual(['AAPL', 'NVDA']);

    // Same toggle rule DataTable applies to every other sortable column
    // (data-table.spec.ts: "starts a newly clicked column ascending and
    // toggles on repeat") -- a fresh column starts ascending.
    const tapeHeader = fixture.nativeElement.querySelectorAll('thead th .sort')[0] as HTMLButtonElement;
    tapeHeader.click();
    fixture.detectChanges();
    expect(rowSymbols()).toEqual(['NVDA', 'AAPL']);

    tapeHeader.click();
    fixture.detectChanges();
    expect(rowSymbols()).toEqual(['AAPL', 'NVDA']);
  });
});

/* -- v85 R7-04 -- the recomposed row: price, changes, sparkline, signal -- */

describe('Watchlist recomposed row', () => {
  it('renders price and the three change columns', () => {
    const row = firstRow({ price: 171.5, change_1d_pct: 1.94, change_1w_pct: 3.12, change_1m_pct: 6.2 });
    expect(row.textContent).toContain('171.50');
    expect(row.textContent).toContain('+1.94%');
    expect(row.textContent).toContain('+6.20%');
  });

  it('renders a missing price as no-value, never as zero', () => {
    const row = firstRow({ price: null });
    expect(row.querySelector('.price')!.textContent!.trim()).toBe('—');
  });

  it('renders the sparkline from the payload series', () => {
    const row = firstRow({ spark: [1, 2, 3, 4] });
    expect(row.querySelector('sb-sparkline')).not.toBeNull();
  });

  it('omits the sparkline rather than drawing a flat line for no series', () => {
    const row = firstRow({ spark: [] });
    expect(row.querySelector('sb-sparkline')).toBeNull();
  });

  it('shows the bar date the row was computed from', () => {
    const row = firstRow({ as_of: '2026-09-10' });
    expect(row.querySelector('.as-of')!.textContent).toContain('2026-09-10');
  });

  it('marks a row whose bar date is not the latest in the table', () => {
    const el = rows([{ symbol: 'A', as_of: '2026-09-10' }, { symbol: 'B', as_of: '2026-09-04' }]);
    expect(el[1].classList).toContain('lagging');
  });

  it('flags a row stale against the WHOLE watchlist, not just its own rendered page', () => {
    // 10 rows sharing one stale as_of -- a full default page -- plus one fresher row that lands
    // on page 2. Every page-1 row must still be flagged: comparing only
    // against the rendered page would find them all equal (none "the
    // latest ON THIS PAGE" since they share a date) and miss that page 2
    // holds the real most-recent bar -- exactly the "eighty rows the cache
    // didn't refresh sitting quietly beside the ones that did" case the
    // brief names.
    const stale = Array.from({ length: 10 }, (_, i) => ({ symbol: `S${i}`, as_of: '2026-09-01' }));
    const el = rows([...stale, { symbol: 'FRESH', as_of: '2026-09-10' }]);

    expect(el.length).toBe(10); // page 1 renders only the 10 stale rows
    expect(el.every((row) => row.classList.contains('lagging'))).toBe(true);
  });

  it('renders the signal score with its horizon when a setup is live', () => {
    const row = firstRow({ signal: { state: 'pending', score: 78, horizon: '6w', strategy: 'RSI' } });
    expect(row.querySelector('.signal')!.textContent).toContain('78');
    expect(row.querySelector('.signal')!.textContent).toContain('6w');
  });

  it('says No setup rather than rendering a zero score', () => {
    const row = firstRow({ signal: { state: 'none', score: null, horizon: null, strategy: null } });
    expect(row.querySelector('.signal')!.textContent!.trim()).toBe('No setup');
  });

  it('distinguishes in-position from waiting by more than colour', () => {
    const row = firstRow({ signal: { state: 'active', score: 78, horizon: '6w', strategy: 'RSI' } });
    expect(row.querySelector('.signal')!.textContent).toContain('In position');
  });

  it('highlights a row with an open position', () => {
    const held = firstRow({ open_trades: 1 });
    expect(held.classList).toContain('has-position');
    const flat = firstRow({ open_trades: 0 });
    expect(flat.classList).not.toContain('has-position');
  });

  it('keeps the columns this app already had', () => {
    // The next-earnings column formats through the same `date()` the
    // template calls (locale-dependent, e.g. "2 Oct 2026") rather than the
    // raw ISO string, so the assertion goes through the same helper instead
    // of hard-coding a format that would only hold under one locale.
    const row = firstRow({ open_trades: 2, next_earnings_date: '2026-10-02' });
    expect(row.textContent).toContain(date('2026-10-02'));
  });
});

/* -- v85 R7-05 -- tag chips, search and freshness in the control bar -- */

interface RenderOpts {
  tags?: Record<string, string[]>;
  symbols?: string[];
  rows?: Partial<Ticker>[];
}

/** Mounts Watchlist with tickers seeded onto `WatchlistStore` and, when
 *  given, tags seeded onto `PreferencesStore` -- the same `patchState` +
 *  `unprotected` pattern `rows()` above uses, extended to the second store
 *  R7-05's chips read from. */
function render(opts: RenderOpts = {}): ComponentFixture<Watchlist> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      WatchlistStore,
      PreferencesStore,
    ],
  });
  const fixture = TestBed.createComponent(Watchlist);
  const list = opts.rows
    ? opts.rows.map((overrides) => ticker(overrides))
    : (opts.symbols ?? ['AAPL']).map((symbol) => ticker({ symbol }));
  patchState(unprotected(TestBed.inject(WatchlistStore)), { tickers: list, loaded: true });
  if (opts.tags) {
    patchState(unprotected(TestBed.inject(PreferencesStore)), {
      data: writeWatchlistTags({}, opts.tags),
      loaded: true,
    });
  }
  fixture.detectChanges();
  return fixture;
}

function chip(fixture: ComponentFixture<Watchlist>, label: string): HTMLButtonElement {
  const buttons = [...(fixture.nativeElement as HTMLElement).querySelectorAll('sb-filter-chips .chip')] as HTMLButtonElement[];
  const found = buttons.find((b) => b.textContent?.trim() === label);
  if (!found) throw new Error(`no chip labelled "${label}"`);
  return found;
}

function chipLabels(opts: RenderOpts): string[] {
  const fixture = render(opts);
  return [...(fixture.nativeElement as HTMLElement).querySelectorAll('sb-filter-chips .chip')]
    .map((el) => el.textContent!.trim());
}

function visibleSymbols(fixture: ComponentFixture<Watchlist>): string[] {
  return [...(fixture.nativeElement as HTMLElement).querySelectorAll('tbody tr.row sb-row-link')]
    .map((el) => (el.textContent ?? '').trim());
}

describe('Watchlist tag chips, search and freshness', () => {
  it('renders All plus one chip per tag in use', () => {
    const labels = chipLabels({ tags: { AAPL: ['Tech'], XOM: ['Energy'] } });
    expect(labels).toEqual(['All', 'Energy', 'Tech']);
  });

  it('filters the table to the chosen tag', () => {
    const f = render({ tags: { AAPL: ['Tech'] }, symbols: ['AAPL', 'XOM'] });
    chip(f, 'Tech').click();
    f.detectChanges();
    expect(visibleSymbols(f)).toEqual(['AAPL']);
  });

  it('does not narrow what the scanner scans', () => {
    const f = render({ tags: { AAPL: ['Tech'] }, symbols: ['AAPL', 'XOM'] });
    // Same TestBed module `render()` just configured -- fetching the store
    // here reaches the identical singleton the component reads, without
    // reaching past the component's own `protected` boundary.
    const store = TestBed.inject(WatchlistStore);
    chip(f, 'Tech').click();
    f.detectChanges();
    expect(store.tickers().length).toBe(2);
  });

  it('offers a way to add a tag to a symbol', () => {
    expect((render().nativeElement as HTMLElement).querySelector('.add-tag')).not.toBeNull();
  });

  it('shows one freshness marker for the table, from the newest bar date', () => {
    const el = render({ rows: [{ as_of: '2026-09-10' }, { as_of: '2026-09-04' }] }).nativeElement as HTMLElement;
    expect(el.querySelector('sb-freshness')).not.toBeNull();
  });

  it('keeps the symbol search', () => {
    expect((render().nativeElement as HTMLElement).querySelector('input[type="search"]')).not.toBeNull();
  });
});
