import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
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
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
  });

  it('mounts without throwing', () => {
    const fixture = TestBed.createComponent(Gallery);
    expect(() => fixture.detectChanges()).not.toThrow();
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

  it('shows both empty-state reasons', () => {
    expect(GALLERY).toContain('reason="measured-zero"');
    expect(GALLERY).toContain('reason="no-data-yet"');
  });

  it('renders the new components in both registers', () => {
    expect(GALLERY).toContain("'register-presentation'");
    expect(GALLERY).toContain("'register-instrument'");
  });
});
