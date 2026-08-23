import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { Ticker } from '../../api/models';
import { SortSpec } from '../../ui/data-table/data-table.types';
import { compareTickers, isWithinCurrentWeek, Watchlist } from './watchlist';

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
    ],
  });
  const fixture = TestBed.createComponent(Watchlist);
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
