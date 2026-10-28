import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { DEFAULT_SCOPE } from '../../stores/analytics.store';
import { ConnectionStore } from '../../stores/connection.store';
import { ScopeBar, fxMissingOf, fxMissingText } from './scope-bar';

const connection = { currency: signal('€') };

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
    connection.currency.set('€');
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: ConnectionStore, useValue: connection }],
    });
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

  it('labels the money toggle with the account currency, keeping the value key (v194 B7)', () => {
    for (const symbol of ['€', '$', '£']) {
      connection.currency.set(symbol);
      const { el } = create({ unit: 'money' });
      const labels = [...el.querySelectorAll('sb-segmented button')].map((b) => b.textContent!.trim());
      expect(labels).toEqual(['R', '%', symbol]);
      // A saved `unit: 'money'` preference still selects the money segment.
      expect(el.querySelector('sb-segmented button[aria-pressed="true"]')!.textContent!.trim()).toBe(symbol);
    }
  });

  it('names how many closes the money figures left out, and only when some were', () => {
    expect(create().el.querySelector('.fx-caveat')).toBeNull();
    const { el } = create({ fxMissing: 2 });
    const caveat = el.querySelector('.fx-caveat')!;
    expect(caveat.getAttribute('role')).toBe('note');
    expect(caveat.textContent!.trim()).toBe(fxMissingText(2));
    // Tuning shows no population and no money: no caveat either.
    expect(create({ fxMissing: 2, tuning: true }).el.querySelector('.fx-caveat')).toBeNull();
  });
});

describe('fxMissingText', () => {
  it('is empty for none and counts trades, singular and plural', () => {
    expect(fxMissingText(0)).toBe('');
    expect(fxMissingText(1)).toBe('1 closed trade left out of money figures: no exchange rate for its exit date');
    expect(fxMissingText(3)).toBe('3 closed trades left out of money figures: no exchange rate for their exit dates');
  });
});

describe('fxMissingOf', () => {
  it('reads the largest count among the payloads present, 0 for none', () => {
    expect(fxMissingOf()).toBe(0);
    expect(fxMissingOf(null, undefined, {})).toBe(0);
    expect(fxMissingOf(null, { fx_missing_count: 2 }, { fx_missing_count: 1 })).toBe(2);
  });
});
