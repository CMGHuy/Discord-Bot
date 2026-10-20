import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, beforeEach } from 'vitest';

import { EquityCandlesResponse } from '../../../api/models';
import { EquityCandlesStore } from '../../../stores/equity-candles.store';
import { equityCandlesStoreStub } from '../../../testing/equity-candles-store.stub';
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';
import { PortfolioValue } from './portfolio-value';

// sb-equity-candles creates a real lightweight-charts chart.
installMatchMediaPolyfill();

const CANDLES: EquityCandlesResponse = {
  tf: '1D', basis: 'mtm', currency_symbol: '€', recording_since: '2026-10-20T13:35:00Z',
  as_of: '2026-10-21T14:35:00Z',
  candles: [{ t: '2026-10-20', o: 100, h: 120, l: 90, c: 110, change: 10, change_pct: 10,
              samples: 4, skipped: 0, approx: false }],
};

describe('portfolio value panel', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: EquityCandlesStore, useValue: equityCandlesStoreStub(CANDLES) },
      ],
    });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(PortfolioValue);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('shows the balance as the hero figure with its currency', () => {
    const el = render({ balance: 997480.01, changePct: 0.36, currency: '€' });
    expect(el.querySelector('.figure')?.textContent).toContain('997,480.01');
    expect(el.querySelector('.figure')?.textContent).toContain('€');
  });

  it('tones the day change by sign', () => {
    expect(render({ balance: 1, changePct: 0.36, currency: '€' })
      .querySelector('.change')?.classList.contains('pos')).toBe(true);
    expect(render({ balance: 1, changePct: -0.36, currency: '€' })
      .querySelector('.change')?.classList.contains('neg')).toBe(true);
  });

  it('renders no value rather than a zero when the balance is missing', () => {
    const el = render({ balance: null, changePct: null, currency: '€' });
    expect(el.querySelector('.figure')?.textContent).not.toContain('0.00');
    expect(el.querySelector('.change')).toBeNull();
  });

  it('draws the equity candles where the sparkline was', () => {
    const el = render({ balance: 1, changePct: 0, points: [1, 2, 3], currency: '€' });
    expect(el.querySelector('sb-equity-candles')).not.toBeNull();
    expect(el.querySelector('sb-sparkline')).toBeNull();
  });

  it('offers the four candle timeframes', () => {
    const el = render({ balance: 1, changePct: 0, currency: '€' });
    const labels = [...el.querySelectorAll('button')].map((b) => b.textContent!.trim());
    expect(labels).toEqual(expect.arrayContaining(['1H', '4H', '1D', '1W']));
    expect(labels).not.toContain('1M');
    expect(labels).not.toContain('ALL');
  });

  it('passes its currency to the candles', () => {
    const el = render({ balance: 1, changePct: 0, currency: '£' });
    expect(el.querySelector('sb-equity-candles .readout')?.textContent).toContain('£');
  });
});
