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
});
