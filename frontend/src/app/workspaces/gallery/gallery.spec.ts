import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ConnectionStore } from '../../stores/connection.store';
import { beforeEach, describe, expect, it } from 'vitest';

import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { compactKeys, drawerKeys, openRowDrawer } from '../../ui/data-table/testing/reachability';
import { Gallery } from './gallery';

// The gallery renders a real sb-trade-chart, and lightweight-charts asks for
// matchMedia the moment a chart exists. See the polyfill for why.
installMatchMediaPolyfill();

const UI = join(process.cwd(), 'src/app/ui');
const GALLERY = readFileSync(
  join(process.cwd(), 'src/app/workspaces/gallery/gallery.ts'),
  'utf8',
);

/** Every `selector: 'sb-…'` declared under ui/, read off disk so a new
 *  primitive is caught the day it is added rather than the day someone
 *  remembers this file exists. `attr` marks the `button[sb-foo]` shape --
 *  used as `<button sb-foo>`, never `<sb-foo>`, so it needs a different
 *  check than every element-selector primitive. */
function selectors(): { name: string; attr: boolean }[] {
  const found = new Map<string, boolean>();
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) { walk(full); continue; }
      if (!entry.name.endsWith('.ts') || entry.name.endsWith('.spec.ts')) continue;
      for (const [, prefix, sel] of readFileSync(full, 'utf8')
        .matchAll(/selector:\s*'((?:button\[)?)(sb-[\w-]+)\]?'/g)) {
        found.set(sel, prefix === 'button[');
      }
    }
  };
  walk(UI);
  return [...found.entries()].map(([name, attr]) => ({ name, attr })).sort((a, b) =>
    a.name.localeCompare(b.name),
  );
}

describe('the gallery shows every primitive', () => {
  for (const { name, attr } of selectors()) {
    it(`renders ${name}`, () => {
      if (attr) {
        // `<button sb-foo` (or any host element) rather than `<sb-foo`,
        // matching how an attribute-selector primitive is actually used.
        expect(GALLERY).toMatch(new RegExp(`<\\w+[^>]*\\b${name}\\b`));
      } else {
        expect(GALLERY).toContain(`<${name}`);
      }
    });
  }
});

/** Not part of the plan's given test -- there is no interactive browser in
 *  this environment to do Step 5's manual "npm start, open /ui" check, so
 *  this is the closest automated substitute: mount the real component and
 *  confirm it renders without throwing. */
describe('the gallery renders', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([]),
        { provide: ConnectionStore, useValue: { marketActive: () => true } }],
    });
  });

  it('mounts without throwing', () => {
    const fixture = TestBed.createComponent(Gallery);
    expect(() => fixture.detectChanges()).not.toThrow();
  });

  it('exhibits every v85 primitive and representative edge states', () => {
    const fixture = TestBed.createComponent(Gallery);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    for (const selector of ['sb-stat-tile', 'sb-control-bar', 'sb-gauge', 'sb-matrix',
      'sb-timeline', 'sb-freshness', 'sb-date-range']) {
      expect(element.querySelector(selector)).not.toBeNull();
    }
    expect(element.querySelectorAll('sb-stat-tile .thin').length).toBeGreaterThan(0);
    expect(element.querySelectorAll('sb-gauge .over').length).toBeGreaterThan(0);
    expect(element.querySelectorAll('sb-freshness .stale').length).toBeGreaterThan(0);
    expect(element.querySelectorAll('sb-matrix .missing').length).toBeGreaterThan(0);
  });

  it('renders one row per cell-contract case, with minutes in every Held value', () => {
    const fixture = TestBed.createComponent(Gallery);
    fixture.detectChanges();
    const table = (fixture.nativeElement as HTMLElement).querySelector('.cell-contracts')!;
    const rows = [...table.querySelectorAll('tbody tr.row')];
    const cell = (row: Element, selector: string) =>
      row.querySelector(selector)!.textContent!.replace(/\s+/g, ' ').trim();

    expect(rows).toHaveLength(4);
    expect(rows.map((r) => r.querySelector('td:last-child')!.textContent!.trim()))
      .toEqual(['4d 2h 15m', '4d 0h 5m', '3h 0m', '45m']);
    expect(cell(rows[0], 'sb-direction-arrow')).toBe('▲');
    expect(cell(rows[1], 'sb-direction-arrow')).toBe('▼');
    expect(cell(rows[0], 'sb-pnl-cell')).toBe('+4.20% (+9.80 €)');
    expect(cell(rows[2], 'sb-pnl-cell')).toBe('+0.40%');
    expect(cell(rows[3], 'sb-pnl-cell')).toBe('—');
    expect(cell(rows[0], 'sb-confidence-cell')).toBe('Lv4 · 78');
    expect(cell(rows[2], 'sb-confidence-cell')).toBe('Lv5');
    expect(cell(rows[0], 'sb-plan-cell')).toContain('→');
  });
});

describe('the gallery is the v80 D6 reference', () => {
  it("shows every button variant, including v77's danger-icon", () => {
    for (const variant of ['primary', 'secondary', 'danger', 'ghost', 'icon', 'danger-icon', 'link', 'chip', 'segment']) {
      expect(GALLERY).toContain(`'${variant}'`);
    }
  });

  it('shows all nine chip tones', () => {
    for (const tone of ['neutral', 'good', 'warn', 'info', 'q1', 'q2', 'q3', 'q4', 'q5']) {
      expect(GALLERY).toContain(`'${tone}'`);
    }
  });

  it('shows every status shape and both panel-grid tracks', () => {
    for (const needle of ["'PENDING'", "'ACTIVE'", "'PARTIAL'", "'CLOSED'", 'track="narrow"', 'track="wide"']) {
      expect(GALLERY).toContain(needle);
    }
  });

  it('scrolls the numerics table in its own box and keeps the plain and reasoned empty states in separate grids (v179 layout audit)', () => {
    // 6 columns plus sb-magnitude are wider than a 356px panel at 390: the table scrolls inside its panel.
    expect(GALLERY).toMatch(/<div class="numerics-scroll">\s*<table class="numerics-demo">/);
    expect(GALLERY).toMatch(/\.numerics-scroll \{[^}]*overflow-x: auto/);
    // Cards side by side start on one baseline only when they share a structure: a card that opens with the
    // 11px reason tag beside one that opens with the 14px title put two first lines 4px apart.
    const grids = [...GALLERY.matchAll(/<sb-panel-grid track="narrow"[^>]*>((?:(?!<\/sb-panel-grid>)[\s\S])*?<sb-empty-state[\s\S]*?)<\/sb-panel-grid>/g)]
      .map((m) => m[1]).filter((body) => !body.includes('sb-panel '));
    const emptyGrids = grids.filter((body) => (body.match(/<sb-empty-state/g) ?? []).length > 0);
    expect(emptyGrids.length).toBeGreaterThanOrEqual(2);
    for (const body of emptyGrids) {
      const states = body.match(/<sb-empty-state[^>]*>/g)!;
      const reasoned = states.filter((tag) => tag.includes('reason='));
      expect(reasoned.length === 0 || reasoned.length === states.length).toBe(true);
    }
  });

  it('shows both empty-state reasons', () => {
    expect(GALLERY).toContain('reason="measured-zero"');
    expect(GALLERY).toContain('reason="no-data-yet"');
  });

  it('renders the new components in both registers', () => {
    expect(GALLERY).toContain("'register-presentation'");
    expect(GALLERY).toContain("'register-instrument'");
  });
});

describe('the gallery covers the v95 content-priority primitives', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([]),
        { provide: ConnectionStore, useValue: { marketActive: () => true } }],
    });
  });

  it.each([
    ['toolbar sheet', '.toolbar-sheet-button'],
    ['collapsed panel digest', '.panel-digest'],
    ['force-expanded panel', '.panel-problem'],
    ['row detail', 'button.detail-toggle'],
  ])('demonstrates the %s', (_name, selector) => {
    const fixture = TestBed.createComponent(Gallery);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector(selector)).not.toBeNull();
  });
});

describe('the gallery shows the one stat tile (v179 §3.3)', () => {
  it('lays the tiles in an auto-fit grid and shows the full stack once', () => {
    expect(GALLERY).toMatch(/\.stat-grid \{[^}]*repeat\(auto-fit, minmax\(10rem, 1fr\)\)/);
    const from = GALLERY.slice(GALLERY.indexOf('<div class="stat-grid">'));
    const block = from.slice(0, from.indexOf('</div>'));
    expect(block.match(/<sb-stat-tile/g)).toHaveLength(4);
    expect(block).toMatch(/secondary="[^"]+"[^>]*hint="[^"]+"/);
  });
});

describe('the gallery shows compact rows (v179 §3.1)', () => {
  it('renders a compact-row table whose tap opens the row drawer', () => {
    installDialogPolyfill();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] });
    const fixture = TestBed.createComponent(Gallery);
    fixture.detectChanges();
    const table = (fixture.nativeElement as HTMLElement).querySelector('.compact-demo sb-data-table') as HTMLElement;
    expect(table.querySelectorAll('li.compact-row')).toHaveLength(2);
    openRowDrawer(table);
    fixture.detectChanges();
    expect([...compactKeys(table), ...drawerKeys(table)].sort()).toEqual(['note', 'outcome', 'pnl', 'ticker']);
  });
});
