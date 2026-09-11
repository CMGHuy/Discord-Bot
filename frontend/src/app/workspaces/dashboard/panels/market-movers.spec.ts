import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { describe, expect, it, beforeEach } from 'vitest';

import { TapeRow } from '../../../api/models';
import { MarketMovers } from './market-movers';

function tape(over: Partial<TapeRow> = {}): TapeRow {
  return { symbol: 'GS', price: 1022.63, change_pct: -0.06,
           context_kind: null, context_label: null, sort_rank: 2, ...over };
}

function mount(inputs: Record<string, unknown>): ComponentFixture<MarketMovers> {
  const f = TestBed.createComponent(MarketMovers);
  for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
  f.detectChanges();
  return f;
}

function symbols(f: ComponentFixture<MarketMovers>): (string | null | undefined)[] {
  return [...(f.nativeElement as HTMLElement).querySelectorAll('.symbol')]
    .map((n) => n.textContent?.trim());
}

/** Tabs carry no data-id of their own -- TabBar just renders them in the
 *  order this component's own `tabs` array declares (gainers, then losers). */
function click(f: ComponentFixture<MarketMovers>, tabId: 'gainers' | 'losers'): void {
  const index = tabId === 'losers' ? 1 : 0;
  (f.nativeElement as HTMLElement)
    .querySelectorAll<HTMLButtonElement>('[role="tab"]')[index].click();
  f.detectChanges();
}

describe('market movers panel', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('ranks gainers highest-first and losers lowest-first', () => {
    const rows = [
      tape({ symbol: 'A', change_pct: 2.69 }),
      tape({ symbol: 'B', change_pct: -1.10 }),
      tape({ symbol: 'C', change_pct: 1.24 }),
      tape({ symbol: 'D', change_pct: -3.40 }),
    ];
    const f = mount({ rows });
    expect(symbols(f)).toEqual(['A', 'C']);          // gainers tab is default

    click(f, 'losers');
    expect(symbols(f)).toEqual(['D', 'B']);
  });

  it('offers exactly two tabs, because there is no volume to rank activity by', () => {
    const f = mount({ rows: [] });
    const labels = [...(f.nativeElement as HTMLElement).querySelectorAll('[role="tab"]')]
      .map((t) => t.textContent?.trim());
    expect(labels).toEqual(['Top gainers', 'Top losers']);
  });

  it('excludes unpriced symbols from both tabs rather than ranking them as zero', () => {
    const f = mount({ rows: [tape({ symbol: 'A', change_pct: null }), tape({ symbol: 'B', change_pct: 1 })] });
    expect(symbols(f)).toEqual(['B']);
  });
});
