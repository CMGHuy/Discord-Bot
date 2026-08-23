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

/**
 * Raw form controls that stay raw, each with the reason it cannot be wrapped.
 * Adding a name here is a claim about the control, so it needs a reason.
 */
const RAW_CONTROL_ALLOWLIST = new Map<string, string>([
  // A file input cannot be wrapped: the picker only opens from a real click
  // on the real element, and re-dispatching one loses the user-activation
  // that browsers require.
  ['workspaces/system/settings-tab.ts', 'type="file"'],
]);

describe('no call site hand-rolls a form control', () => {
  for (const { name, source } of callSites()) {
    it(`${name} routes every input and select through a primitive`, () => {
      const allowed = RAW_CONTROL_ALLOWLIST.get(name);
      const raw = [...source.matchAll(/<(input|select)\b[^>]*>/gs)]
        .map(([tag]) => tag.replace(/\s+/g, ' '))
        .filter((tag) => !(allowed && tag.includes(allowed)));
      expect(raw).toEqual([]);
    });
  }
});
