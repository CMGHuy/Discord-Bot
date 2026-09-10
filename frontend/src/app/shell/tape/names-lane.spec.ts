import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { TapeStore } from '../../stores/tape.store';
import { NamesLane } from './names-lane';

describe('NamesLane', () => {
  function setup(rows: unknown[], asOf: string | null = '2026-09-09T14:35:00+00:00') {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: TapeStore, useValue: {
          rows: () => rows, asOf: () => asOf,
          visible: () => rows.length > 0, load: () => undefined,
        } },
      ],
    });
    const fixture = TestBed.createComponent(NamesLane);
    fixture.detectChanges();
    return fixture;
  }

  it('renders nothing when nothing is flagged', () => {
    const el = setup([]).nativeElement as HTMLElement;
    expect(el.querySelector('.lane')).toBeNull();
  });

  it('renders the track twice so the loop is seamless', () => {
    const el = setup([{ symbol: 'NVDA', price: 1, change_pct: 1, context_kind: null, context_label: null, sort_rank: 2 }])
      .nativeElement as HTMLElement;
    expect(el.querySelectorAll('.tile').length).toBe(2);
  });

  it('keeps the as-of badge outside the animated track', () => {
    const el = setup([{ symbol: 'NVDA', price: 1, change_pct: 1, context_kind: null, context_label: null, sort_rank: 2 }])
      .nativeElement as HTMLElement;
    const badge = el.querySelector('.as-of')!;
    expect(badge.closest('.track')).toBeNull();
  });

  it('shows a placeholder rather than dropping an unpriced symbol', () => {
    const el = setup([{ symbol: 'ZZZZ', price: null, change_pct: null, context_kind: null, context_label: null, sort_rank: 2 }])
      .nativeElement as HTMLElement;
    expect(el.textContent).toContain('ZZZZ');
  });
});
