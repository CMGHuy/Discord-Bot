import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { OverrideFidelity } from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { OverrideFidelityPanel } from './override-fidelity-panel';
import { APPROX_LABEL, CAPTION } from './override-fidelity.model';
import {
  OVERRIDE_FIDELITY_FIXTURE, VERDICT_FLOORS_MET, VERDICT_RECORDED_COST, VERDICT_WAITING_ON,
  overrideFixture,
} from './override-fidelity.fixture';

function render(payload: OverrideFidelity | null, error: string | null = null) {
  const reloads: string[] = [];
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: AnalyticsStore, useValue: { overrideFidelity: signal(payload),
        overrideFidelityError: signal(error), reload: (k: string) => reloads.push(k) } },
      { provide: PreferencesStore, useValue: { values: () => ({}), update: () => {} } },
    ],
  });
  const fixture = TestBed.createComponent(OverrideFidelityPanel);
  fixture.detectChanges();
  return { el: fixture.nativeElement as HTMLElement, reloads };
}

const text = (el: Element | null): string => (el?.textContent ?? '').replace(/\s+/g, ' ').trim();
const tone = (el: HTMLElement, selector: string): string | null =>
  el.querySelector(selector)?.getAttribute('data-tone') ?? null;

describe('OverrideFidelityPanel', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('leads with net dollars and R, then counted, helped/hurt/neutral, the badge', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    const tiles = [...el.querySelectorAll('.tiles > div')].map((t) => text(t.querySelector('dt')));
    expect(tiles).toEqual(['Net effect vs engine', 'Overrides counted', 'Helped / hurt / neutral', 'Verdict']);
    expect(text(el.querySelector('.tiles > .net dd'))).toBe('+$59.35 · +1.19 R');
    expect(text(el.querySelector('.tiles'))).toContain('counts ignore size');
    expect(text(el.querySelector('.badge-text'))).toBe('1 of 30 needed. No conclusion yet.');
    expect(text(el.querySelector('h2'))).toBe('Overrides vs engine');
  });

  it('keeps the net-effect tile neutral while WAITING and shows no recorded figures', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);           // live sum is positive
    expect(tone(el, '.tiles > .net')).toBe('neutral');
    expect(tone(el, '.badge')).toBe('neutral');
    expect(el.querySelectorAll('.live').length).toBe(0);
    expect(el.querySelector('.recorded')).toBeNull();
    expect(el.querySelector('.waiting-on')).toBeNull();
  });

  it('says what it is waiting on once the count is met', () => {
    const { el } = render(overrideFixture({ verdict: VERDICT_WAITING_ON }));
    expect(text(el.querySelector('.badge-text')))
      .toBe('34 of 30 counted. Waiting on other conditions. No conclusion yet.');
    expect(text(el.querySelector('.waiting-on'))).toBe('Waiting on: at least 10 distinct weeks '
      + '(now 8); no open rows (now 2 open); left-out rows at most 20% (now 25%)');
  });

  it('says the floors are met without claiming a result', () => {
    const { el } = render(overrideFixture({ verdict: VERDICT_FLOORS_MET }));
    expect(text(el.querySelector('.badge-text')))
      .toBe('Floors met (34 of 30). Awaiting the one recorded evaluation. No conclusion yet.');
    expect(el.querySelector('.waiting-on')).toBeNull();
    expect(tone(el, '.tiles > .net')).toBe('neutral');
  });

  it('shows a recorded verdict from the record and labels the live tiles', () => {
    const { el } = render(overrideFixture({ verdict: VERDICT_RECORDED_COST }));
    expect(text(el.querySelector('.badge-text')))
      .toBe('Your overrides cost $1,364.00 (6.82 R) vs the engine');
    expect(tone(el, '.badge')).toBe('neg');
    expect(tone(el, '.tiles > .net')).toBe('pos');              // the live sum, labelled live
    expect([...el.querySelectorAll('.tiles .live')].map(text)).toEqual([
      'live, may have moved since recorded on 2026-12-04',
      'live, may have moved since recorded on 2026-12-04',
    ]);
    expect(text(el.querySelector('.recorded'))).toContain('Recorded on 2026-12-04 from 31 overrides over 12 weeks');
    expect(text(el.querySelector('.recorded'))).toContain('2 overrides priced from a bar close, not a quote.');
  });

  it('prints the fixed caption legibly and one note per exclusion, singular for one', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    expect(text(el.querySelector('p.caption'))).toBe(CAPTION);
    expect([...el.querySelectorAll('.note')].map(text)).toEqual([
      '1 close from one bulk clear on 2026-09-30 is not a decision, so it is left out',
      '1 estimated row is shown but not counted',
      '1 stale data row is left out',
    ]);
  });

  it('labels the estimated row beside its delta, in the table and the card', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    const rows = el.querySelectorAll('table.rows tbody tr');
    expect(rows.length).toBe(4);
    expect(text(rows[1].querySelector('td.delta'))).toContain(APPROX_LABEL);
    expect(text(rows[0].querySelector('td.delta'))).not.toContain(APPROX_LABEL);
    expect(rows[1].classList.contains('excluded')).toBe(true);
    expect([...el.querySelectorAll('table.rows th')].map(text)).toEqual(
      ['Close date', 'Ticker', 'Horizon', 'State at close', 'Actual', 'Engine', 'Δ', 'Engine exit', 'Status']);
  });

  it('builds one card per row, leading with ticker, close date and delta in $ and R', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    const cards = el.querySelectorAll('ul.cards > li.card');
    expect(cards.length).toBe(4);
    const lead = text(cards[0].querySelector('.lead'));
    expect(lead.indexOf('AAA')).toBeLessThan(lead.indexOf('2026-10-07'));
    expect(lead).toContain('+$59.35 · +1.19 R');
    expect([...cards[1].querySelectorAll('.sub')].map(text)).toContain(APPROX_LABEL);
    expect(text(cards[2])).toContain('bulk clear');
  });

  it('pages only past five rows', () => {
    expect(render(OVERRIDE_FIDELITY_FIXTURE).el.querySelector('sb-pagination')).toBeNull();
    TestBed.resetTestingModule();
    const six = Array.from({ length: 6 }, (_, i) => ({ ...OVERRIDE_FIDELITY_FIXTURE.rows[0], plan_id: `r${i}` }));
    expect(render(overrideFixture({ rows: six })).el.querySelector('sb-pagination')).not.toBeNull();
  });

  it('says so plainly when there are no overrides', () => {
    const { el } = render(overrideFixture({ rows: [] }));
    expect(text(el)).toContain('No manual overrides in scope.');
    expect(el.querySelector('.tiles')).toBeNull();
  });

  it('keeps its own error and retries only itself', () => {
    const { el, reloads } = render(null, 'boom');
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
    (el.querySelector('sb-panel-error button') as HTMLButtonElement | null)?.click();
    expect(reloads).toEqual(['overrideFidelity']);
  });
});

describe('override-fidelity-panel.ts styles', () => {
  const src = readFileSync(
    join(process.cwd(), 'src/app/workspaces/analytics/tabs/override-fidelity-panel.ts'), 'utf8');

  it('uses only declared breakpoint values in width queries', () => {
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });

  it('swaps the nine-column table for cards at tablet width, so the delta never scrolls off', () => {
    // Measured at 768px: the table scrolled sideways and hid the delta column.
    const q = src.match(/@media\(max-width:1023px\)\{([^@]*?\}\})/)?.[1] ?? '';
    expect(q).toContain('.table-wrap{display:none}');
    expect(q).toContain('.cards{display:grid}');
  });

  it('sets the caption at body size in the secondary text colour, never clipped', () => {
    const rule = src.match(/\.caption\{([^}]*)\}/)?.[1] ?? '';
    expect(rule).toContain('font-size:var(--text-body)');
    expect(rule).toContain('color:var(--text-secondary)');
    expect(rule).not.toMatch(/text-overflow|line-clamp|max-height|white-space:nowrap/);
  });

  it('never truncates the badge text', () => {
    expect(src).not.toMatch(/text-overflow:\s*ellipsis/);
  });
});
