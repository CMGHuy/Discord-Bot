import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { ConnectionStore } from '../../stores/connection.store';
import { beforeEach, describe, expect, it } from 'vitest';

import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { compactKeys, drawerKeys, openRowDrawer } from '../../ui/data-table/testing/reachability';
import { Gallery } from './gallery';
import { Hint } from '../../ui/hint';
import { RouteTitleService } from '../../routing/route-title.service';
import { PERFORMANCE_CAVEAT, StatTile } from '../../ui/stat-tile';

/** The text of the sb-hint whose aria label is `label` (A4 audit). */
function hintText(fixture: ComponentFixture<unknown>, label: string): string {
  const hint = fixture.debugElement
    .queryAll(By.directive(Hint))
    .map((debug) => debug.componentInstance as Hint)
    .find((h) => h.label() === label);
  if (!hint) throw new Error(`no sb-hint labelled "${label}"`);
  return hint.text();
}

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

  it('Expectancy demo hint matches the basis the book is computed on (A4 audit)', () => {
    const fixture = TestBed.createComponent(Gallery);
    fixture.detectChanges();
    const text = hintText(fixture, 'About expectancy');
    expect(text).toContain(PERFORMANCE_CAVEAT);
    expect(text).not.toContain('after costs');
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
    for (const variant of ['primary', 'secondary', 'danger', 'danger-quiet', 'ghost', 'icon', 'danger-icon', 'link', 'chip', 'segment']) {
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

/* -- v195 §5.1 -- the gallery is the reference page for sb-page ------------- */

describe('the gallery is the sb-page reference (v195 §5.1, Phase 4)', () => {
  beforeEach(() => {
    installDialogPolyfill();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([]),
        { provide: ConnectionStore, useValue: { marketActive: () => true } }],
    });
    TestBed.inject(RouteTitleService).set('UI gallery', 'Every primitive, in one place');
  });

  function mount() {
    const fixture = TestBed.createComponent(Gallery);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('renders the route title as its one h1, and writes none itself', () => {
    const { el } = mount();
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('UI gallery');
    expect(GALLERY).not.toMatch(/<h1[\s>]/);
  });

  it('fills every slot: actions, scope, KPIs, the primary reference and two secondary panels', () => {
    const { el } = mount();
    for (const slot of ['[page-actions]', '[page-scope]', '[page-kpis]', '[page-primary]']) {
      expect(el.querySelectorAll(`sb-page ${slot}`), slot).toHaveLength(1);
    }
    expect(el.querySelectorAll('sb-page [page-secondary]')).toHaveLength(2);
    expect(el.querySelector('sb-page [page-primary] sb-stat-tile .thin')).not.toBeNull();
  });

  it('demos the header action as danger-quiet, behind its confirm', () => {
    const { fixture, el } = mount();
    const button = el.querySelector<HTMLButtonElement>('sb-page [page-actions] [data-action="demo-clear"]')!;
    expect(button.classList).toContain('danger-quiet');
    expect(button.classList).not.toContain('danger');
    button.click();
    fixture.detectChanges();
    expect(el.querySelector('dialog[open]')!.textContent).toContain('Clear the demo log?');
  });

  it('shows danger for the killswitch alone and danger-quiet for housekeeping, each confirming', () => {
    const { fixture, el } = mount();
    const halt = el.querySelector<HTMLButtonElement>('[data-demo="killswitch"]')!;
    const quiet = el.querySelector<HTMLButtonElement>('[data-demo="housekeeping"]')!;
    expect(halt.classList).toContain('danger');
    expect(halt.classList).not.toContain('danger-quiet');
    expect(quiet.classList).toContain('danger-quiet');
    halt.click();
    fixture.detectChanges();
    const dialog = el.querySelector('dialog[open]')!;
    expect(dialog.textContent).toContain('Halt trading?');
    expect(dialog.querySelector('button.danger')).not.toBeNull();
  });

  it('leads the demo KPI strip with ExpR, with N and the basis, and risk in two units', () => {
    const { fixture } = mount();
    const tiles = fixture.debugElement.queryAll(By.css('[page-kpis] sb-stat-tile'))
      .map((d) => d.componentInstance as StatTile);
    expect(tiles.map((t) => t.label())).toEqual(['ExpR', 'Win rate', 'Open risk', 'Payoff ratio']);
    for (const tile of [tiles[0], tiles[1], tiles[3]]) {
      expect(tile.sample(), tile.label()).not.toBeNull();
      expect(tile.about(), tile.label()).toContain(PERFORMANCE_CAVEAT);
    }
    expect(tiles[2].value()).toMatch(/ · \d+\.\d{2}%$/);
  });

  it('demos the rail label: an anchored hint beside a link, with no trigger button', () => {
    const { el } = mount();
    const link = el.querySelector<HTMLAnchorElement>('a.rail-demo')!;
    expect(link.getAttribute('aria-label')).toBe('Dashboard');
    const hint = link.nextElementSibling!;
    expect(hint.tagName.toLowerCase()).toBe('sb-hint');
    expect(hint.querySelector('button')).toBeNull();
  });
});
