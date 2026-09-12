import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it, beforeEach } from 'vitest';

import { TapeRow } from '../../../api/models';
import { WatchlistPanel } from './watchlist-panel';

function tape(over: Partial<TapeRow> = {}): TapeRow {
  return { symbol: 'GS', price: 1022.63, change_pct: -0.06,
           context_kind: null, context_label: null, sort_rank: 2, ...over };
}

describe('watchlist panel', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(WatchlistPanel);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('lists symbol, price and day change', () => {
    const el = render({ rows: [tape()] });
    expect(el.textContent).toContain('GS');
    expect(el.textContent).toContain('1,022.63');
    expect(el.textContent).toContain('-0.06');
  });

  it('tones the change by sign', () => {
    const el = render({ rows: [tape({ change_pct: 1.24 }), tape({ symbol: 'X', change_pct: -1.24 })] });
    const cells = el.querySelectorAll('.change');
    expect(cells[0].classList.contains('pos')).toBe(true);
    expect(cells[1].classList.contains('neg')).toBe(true);
  });

  it('shows a dash, not a zero, for a symbol with no price yet', () => {
    const el = render({ rows: [tape({ price: null, change_pct: null })] });
    expect(el.querySelector('.price')?.textContent?.trim()).toBe('—');
  });

  it('caps the list at the limit', () => {
    const rows = Array.from({ length: 12 }, (_, i) => tape({ symbol: `S${i}` }));
    expect(render({ rows, limit: 5 }).querySelectorAll('tbody tr')).toHaveLength(5);
  });
});
