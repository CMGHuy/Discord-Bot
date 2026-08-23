import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { callSites } from './testing/call-sites';

describe('no call site hand-rolls a button', () => {
  for (const { name, source } of callSites()) {
    it(`${name} routes every button through sb-button`, () => {
      const raw = [...source.matchAll(/<button\b[^>]*>/gs)]
        .map(([tag]) => tag)
        .filter((tag) => !tag.includes('sb-button'));
      expect(raw).toEqual([]);
    });
  }
});
