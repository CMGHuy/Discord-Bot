import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Ticker } from '../../api/models';
import { EarningsCalendar, buildWeeks, toDateKey } from './earnings-calendar';

function ticker(overrides: Partial<Ticker>): Ticker {
  return {
    symbol: 'AAPL', company_name: 'Apple Inc.', open_trades: 0, closed_trades: 0,
    next_earnings_date: null, next_earnings_datetime: null,
    ...overrides,
  };
}

describe('toDateKey', () => {
  it('formats in local time, not UTC', () => {
    // A date constructed from local y/m/d must round-trip to the same
    // string regardless of the viewer's UTC offset -- toISOString() would
    // not, which is exactly why toDateKey does not use it.
    expect(toDateKey(new Date(2026, 8, 3))).toBe('2026-09-03');
    expect(toDateKey(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
});

describe('buildWeeks', () => {
  it('starts each week on Monday', () => {
    const weeks = buildWeeks(new Date(2026, 8, 1)); // September 2026
    expect(weeks[0][0].getDay()).toBe(1); // Monday
    expect(weeks[0][6].getDay()).toBe(0); // Sunday
  });

  it('covers every day of the month exactly once', () => {
    const weeks = buildWeeks(new Date(2026, 8, 1));
    const inMonth = weeks.flat().filter((d) => d.getMonth() === 8);
    expect(inMonth).toHaveLength(30); // September has 30 days
    expect(new Set(inMonth.map((d) => d.getDate())).size).toBe(30);
  });

  it('trims to as few weeks as the month needs, not a fixed six', () => {
    // February 2026 starts on a Sunday and has 28 days -- fits in 5 weeks.
    const weeks = buildWeeks(new Date(2026, 1, 1));
    expect(weeks).toHaveLength(5);
  });

  it('pads the leading and trailing weeks with adjacent-month days', () => {
    const weeks = buildWeeks(new Date(2026, 8, 1)); // Sept 1 2026 is a Tuesday
    expect(weeks[0][0].getMonth()).toBe(7); // Monday Aug 31 leads in
    expect(weeks[0][0].getDate()).toBe(31);
  });
});

describe('EarningsCalendar', () => {
  let fixture: ComponentFixture<EarningsCalendar>;

  function mount(tickers: Ticker[]) {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(EarningsCalendar);
    fixture.componentRef.setInput('tickers', tickers);
    fixture.detectChanges();
    return fixture.componentInstance;
  }

  const el = () => fixture.nativeElement as HTMLElement;

  it('places a ticker in the cell matching its next_earnings_date', () => {
    const cmp = mount([ticker({ symbol: 'AAPL', next_earnings_date: toDateKey(new Date()) })]);
    fixture.detectChanges();
    void cmp;
    expect(el().textContent).toContain('AAPL');
  });

  it('groups more than one ticker into the same day cell', () => {
    const today = toDateKey(new Date());
    mount([
      ticker({ symbol: 'AAPL', next_earnings_date: today }),
      ticker({ symbol: 'MSFT', next_earnings_date: today }),
    ]);
    expect(el().textContent).toContain('AAPL');
    expect(el().textContent).toContain('MSFT');
  });

  it('ignores a ticker with no known earnings date', () => {
    mount([ticker({ symbol: 'ZZZZ', next_earnings_date: null })]);
    expect(el().textContent).not.toContain('ZZZZ');
  });

  it('marks every shown time as an estimate', () => {
    mount([ticker({
      symbol: 'AAPL', next_earnings_date: toDateKey(new Date()),
      next_earnings_datetime: new Date().toISOString(),
    })]);
    expect(el().textContent).toContain('est.');
  });

  it('shows the empty note only when the watchlist itself is empty', () => {
    mount([]);
    expect(el().textContent).toContain('Nothing on the watchlist');
  });

  it('does not show the empty note when there are tickers with no earnings data', () => {
    mount([ticker({ symbol: 'ZZZZ', next_earnings_date: null })]);
    expect(el().textContent).not.toContain('Nothing on the watchlist');
  });
});
