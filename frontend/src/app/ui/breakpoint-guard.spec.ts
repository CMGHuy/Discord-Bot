import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { BREAKPOINTS } from './breakpoints';

/* Declared floors, and the max-width form of each (floor - 1). An @media
 * cannot read var(), so these literals are duplicated from breakpoints.ts by
 * necessity -- this test is what keeps the two in step. */
const ALLOWED = new Set(
  Object.values(BREAKPOINTS).flatMap((v) => [String(v), String(v - 1)]),
);

/** Genuinely bespoke, documented in spec v95 §6. */
const EXEMPT = ['shell/tape/tape.css', 'workspaces/watchlist/earnings-calendar.ts'];

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return walk(path);
    return /\.(ts|css)$/.test(entry) && !/\.spec\.ts$/.test(entry) ? [path] : [];
  });
}

describe('breakpoint discipline', () => {
  const root = join(process.cwd(), 'src/app');

  it('uses only declared breakpoint values in width queries', () => {
    const offenders: string[] = [];

    for (const path of walk(root)) {
      const relative = path.slice(root.length + 1).replace(/\\/g, '/');
      if (EXEMPT.some((e) => relative.endsWith(e))) continue;

      const widths = [...readFileSync(path, 'utf8')
        .matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);

      for (const width of widths) {
        if (!ALLOWED.has(width)) offenders.push(`${relative}: ${width}px`);
      }
    }

    // A value outside the declared set puts the stylesheet and
    // ViewportService on different scales -- the defect breakpoints.ts's own
    // docstring warns about, and the one v95 A2 found in shell.css.
    expect(offenders).toEqual([]);
  });
});
