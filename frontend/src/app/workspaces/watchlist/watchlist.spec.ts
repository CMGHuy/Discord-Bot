import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter, Router } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { Ticker } from '../../api/models';
import { SortSpec } from '../../ui/data-table/data-table.types';
import { compareTickers, isWithinCurrentWeek, Watchlist } from './watchlist';
import { WatchlistStore } from '../../stores/watchlist.store';
import { TapeStore } from '../../stores/tape.store';

function ticker(overrides: Partial<Ticker>): Ticker {
  return {
    symbol: 'AAPL', company_name: 'Apple Inc.', open_trades: 0, closed_trades: 0,
    next_earnings_date: null, next_earnings_datetime: null,
    ...overrides,
  };
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
