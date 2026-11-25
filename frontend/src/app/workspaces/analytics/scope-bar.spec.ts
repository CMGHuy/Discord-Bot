import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { DEFAULT_SCOPE } from '../../stores/analytics.store';
import { ConnectionStore } from '../../stores/connection.store';
import { ACCOUNT_WIDE_NOTE, ScopeBar, fxMissingOf, fxMissingText } from './scope-bar';

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

  it('collapses to the date range plus the account-wide note in benchmark mode', () => {
    const { fixture, el } = create({ benchmark: true,
      scope: { ...DEFAULT_SCOPE, from: '2026-09-01', ledger: 'weak', strategy: 'MACD' } });
    expect(el.querySelector('sb-date-range')).not.toBeNull();
    expect(el.querySelector('sb-select')).toBeNull();
    expect(el.querySelector('sb-segmented')).toBeNull();
    expect(el.textContent).not.toContain('N=312');
    expect(el.querySelector('[role="note"].account-wide')!.textContent!.trim()).toBe(ACCOUNT_WIDE_NOTE);
    expect(ACCOUNT_WIDE_NOTE).toBe('Equity is account-wide: ledger, strategy, horizon and direction filters do not apply.');
    // Only the date counts as an active filter: ledger and strategy do not apply on this tab.
    expect((fixture.componentInstance as unknown as { activeCount(): number }).activeCount()).toBe(1);
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

  it('sets the unit toggle, population and freshness on one text line: the buttons\' (v179 §3.4, v246 §A2)', () => {
    const { el } = create();
    const line = el.querySelector('sb-control-bar .scope .scope-line')!;
    expect(line.querySelector('sb-field sb-segmented')).not.toBeNull();
    expect(line.querySelector('.population')).not.toBeNull();
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/scope-bar.ts'), 'utf8');
    // The Units field's first line is its caption; its last is the buttons'.
    expect(src).toMatch(/\.scope-line \{[^}]*align-items: last baseline/);
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

/* -- v246 §A2 -- every scope-bar control in one sb-field ------------------ */

describe('ScopeBar fields (v246 §A2)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/scope-bar.ts'), 'utf8');
  const PHONE = SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';
  /** Bounds no preset produces, so the preset select reads "Custom…". */
  const CUSTOM = { ...DEFAULT_SCOPE, from: '2026-01-05', to: '2026-02-01' };

  beforeEach(() => {
    TestBed.resetTestingModule();
    connection.currency.set('€');
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: ConnectionStore, useValue: connection }],
    });
  });

  const filterFields = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>('sb-control-bar .filters > sb-field')];
  const caption = (field: HTMLElement) => field.querySelector('.field-label')!.textContent!.trim();

  it('puts Range, Ledger, Strategy, Horizon and Direction each in one sb-field, in reading order', () => {
    const fields = filterFields(create().el);
    expect(fields.map(caption)).toEqual(['Range', 'Ledger', 'Strategy', 'Horizon', 'Direction']);
    expect(fields.map((f) => f.getAttribute('data-size'))).toEqual(['m', 'm', 'm', 's', 's']);
    for (const field of fields) expect(field.querySelector('sb-select')).not.toBeNull();
  });

  it('draws one caption per field and names every select from it', () => {
    const fields = filterFields(create().el);
    for (const field of fields) expect(field.querySelectorAll('.sb-label'), caption(field)).toHaveLength(1);
    expect(fields.map((f) => f.querySelector('select')!.getAttribute('aria-label')))
      .toEqual(['Range', 'Ledger', 'Strategy', 'Horizon', 'Direction']);
  });

  it('adds the custom dates as an uncaptioned field right after Range, a whole row wherever the bar is a grid', () => {
    const fields = filterFields(create({ scope: CUSTOM }).el);
    expect(fields).toHaveLength(6);
    const dates = fields[1];
    expect(dates.querySelector('sb-date-range')).not.toBeNull();
    expect(caption(dates)).toBe('');
    expect(dates.getAttribute('data-size')).toBe('auto');
    expect([...dates.classList]).toEqual(expect.arrayContaining(['no-label', 'full-row', 'range-field']));
    expect(dates.querySelector('input.from')!.getAttribute('aria-label')).toBe('From date');
    expect(dates.querySelector('input.to')!.getAttribute('aria-label')).toBe('To date');
    expect(caption(fields[0])).toBe('Range');
  });

  it('hides the custom dates field until the preset reads Custom', () => {
    const { el } = create();
    expect(el.querySelector('sb-date-range')).toBeNull();
    expect(filterFields(el)).toHaveLength(5);
  });

  it('captions the benchmark date range "Range" and names its inputs from it', () => {
    const fields = filterFields(create({ benchmark: true }).el);
    expect(fields).toHaveLength(1);
    expect(caption(fields[0])).toBe('Range');
    expect([...fields[0].classList]).toEqual(expect.arrayContaining(['full-row', 'range-field']));
    expect(fields[0].querySelector('input.from')!.getAttribute('aria-label')).toBe('Range from');
    expect(fields[0].querySelector('input.to')!.getAttribute('aria-label')).toBe('Range to');
  });

  it('puts the unit switch in a Units field on the scope line, a whole row on a phone', () => {
    for (const inputs of [{}, { tuning: true }]) {
      const { el } = create(inputs);
      const field = el.querySelector<HTMLElement>('sb-control-bar .scope .scope-line > sb-field')!;
      expect(caption(field)).toBe('Units');
      expect(field.getAttribute('data-size')).toBe('auto');
      expect(field.classList).toContain('full-row');
      expect(field.querySelector('[role="group"]')!.getAttribute('aria-label')).toBe('Units');
      expect(field.querySelector('sb-segmented')!.classList).toContain('many');
    }
  });

  it('spans the phone grid with the date range and the phone row with the scope line', () => {
    expect(SOURCE).toMatch(/\.range-field \{ grid-column: 1 \/ -1; \}/);
    expect(PHONE).toMatch(/\.scope-line \{ flex: 1 1 100%; \}/);
  });

  it('wraps every select, date range and segmented of the bar in a field, none captioning itself', () => {
    const bar = SOURCE.slice(SOURCE.indexOf('<sb-control-bar'), SOURCE.indexOf('</sb-control-bar>'));
    expect(bar.match(/<sb-(select|text-input|date-range|segmented)\b/g)).toHaveLength(8);
    expect(bar.match(/<sb-field\b/g)).toHaveLength(8);
    // \s before label: ariaLabel= is not a caption.
    expect(bar).not.toMatch(/<sb-(select|date-range)\b[^>]*\slabel=/);
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
