import { describe, expect, it } from 'vitest';

import { callSites } from './testing/call-sites';

/**
 * Numerics are mono and tabular via `.num`, right-aligned, and formatted
 * through `ui/format.ts`. This gate catches the two ways that slips:
 * interpolating a raw number into a template, and using toFixed at a call
 * site instead of the shared formatter.
 */
describe('the numeric law', () => {
  for (const { name, source } of callSites()) {
    it(`${name} formats numbers through ui/format.ts`, () => {
      const offenders = [...source.matchAll(/\{\{[^}]*\.toFixed\(/g)].map(([m]) => m.trim());
      expect(offenders).toEqual([]);
    });

    it(`${name} uses toLocaleString nowhere`, () => {
      // format.ts owns locale decisions; a second one drifts from the first.
      expect(source).not.toContain('toLocaleString');
    });
  }
});
