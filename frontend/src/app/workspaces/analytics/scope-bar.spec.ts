import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { DEFAULT_SCOPE } from '../../stores/analytics.store';
import { ScopeBar } from './scope-bar';

const create = (inputs: Record<string, unknown> = {}) => {
  const fixture = TestBed.createComponent(ScopeBar);
  fixture.componentRef.setInput('scope', DEFAULT_SCOPE);
  fixture.componentRef.setInput('unit', 'r');
  fixture.componentRef.setInput('n', 312);
  fixture.componentRef.setInput('allTimePanels', 0);
  fixture.componentRef.setInput('strategies', ['MACD']);
  fixture.componentRef.setInput('horizons', ['2w', '1m']);
  for (const [k, v] of Object.entries(inputs)) fixture.componentRef.setInput(k, v);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
};

describe('ScopeBar', () => {
  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('reports the population the scope produced', () => {
    const { el } = create();
    expect(el.textContent).toContain('N=312');
    expect(el.textContent).not.toContain('all-time');
  });

  it('says how many panels ignore it', () => {
    const { el } = create({ allTimePanels: 3 });
    expect(el.textContent).toContain('3 panels all-time');
  });

  it('collapses to the unit toggle on Tuning', () => {
    const { el } = create({ tuning: true });
    expect(el.querySelector('sb-date-range')).toBeNull();
    // Every filter goes, not just the range: a grid search has no scoped
    // population for a ledger or strategy filter to narrow.
    expect(el.querySelector('sb-select')).toBeNull();
    expect(el.textContent).not.toContain('N=');
    expect(el.querySelector('sb-segmented')).not.toBeNull();
  });

  it('counts every non-default filter so Clear says how much it clears', () => {
    const { el } = create({ scope: { ...DEFAULT_SCOPE, ledger: 'both', strategy: 'MACD' } });
    expect(el.querySelector('.clear')!.textContent).toContain('2');
  });

  it('says "no closed trades" for an empty sample, never "N=—" (v179 §3.4)', () => {
    for (const n of [null, 0]) {
      const { el } = create({ n });
      const line = el.querySelector('.population')!;
      expect(line.textContent!.trim()).toBe('no closed trades');
      expect(line.classList).not.toContain('num');
      expect(el.textContent).not.toContain('N=—');
    }
    const { el } = create({ n: 972 });
    expect(el.querySelector('.population')!.textContent!.trim()).toBe('N=972 closed');
    expect(el.querySelector('.population')!.classList).toContain('num');
  });

  it('sets the unit toggle, population and freshness on one baseline', () => {
    const { el } = create();
    const line = el.querySelector('sb-control-bar .scope .scope-line')!;
    expect(line.querySelector('sb-segmented')).not.toBeNull();
    expect(line.querySelector('.population')).not.toBeNull();
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/scope-bar.ts'), 'utf8');
    expect(src).toMatch(/\.scope-line \{[^}]*align-items: baseline/);
  });
});
