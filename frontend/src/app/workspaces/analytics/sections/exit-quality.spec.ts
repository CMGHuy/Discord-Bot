import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ExitQualitySectionComponent } from './exit-quality';

const BASE = {
  hold_by_outcome: { n_winners: 1, n_losers: 1, ratio: null },
  efficiency: { bins: [], n: 0, median: null },
  mae: { bins: [], n: 0, median: null },
  scatter: [],
  coverage: {},
  min_cell_n: 20,
};

function render(data: object) {
  const f = TestBed.createComponent(ExitQualitySectionComponent);
  f.componentRef.setInput('data', data);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('Exit quality — unmapped reasons (v89 spec §3.5)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('warns and names the strings when "other" is over a fifth of exits', () => {
    const el = render({
      ...BASE,
      exit_reasons: [{ reason: 'stop', n: 10 }, { reason: 'other', n: 90 }],
      unmapped_reasons: [{ status: 'win', text: 'take profit reached', n: 60 }, { status: 'loss', text: '', n: 30 }],
    });
    const warning = el.querySelector('.unmapped')!;
    expect(warning.textContent).toContain('90%');
    expect(warning.textContent).toContain('take profit reached');
    expect(warning.textContent).toContain('(no reason recorded)');
  });

  it('stays quiet when "other" is a small share', () => {
    const el = render({ ...BASE, exit_reasons: [{ reason: 'stop', n: 90 }, { reason: 'other', n: 10 }], unmapped_reasons: [] });
    expect(el.querySelector('.unmapped')).toBeNull();
  });

  it('stays quiet with no unmapped rows even if "other" would otherwise qualify', () => {
    const el = render({ ...BASE, exit_reasons: [{ reason: 'stop', n: 10 }, { reason: 'other', n: 90 }], unmapped_reasons: [] });
    expect(el.querySelector('.unmapped')).toBeNull();
  });
});
