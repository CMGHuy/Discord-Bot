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

/**
 * Promoted classes a call site may still define, each with the reason
 * sb-section-head cannot cover it. Adding a name here is a claim about
 * the file, so it needs a reason.
 */
const PROMOTED_ALLOWLIST = new Map<string, string[]>([
  // Trade detail's <h1> is a ticker span plus a live sb-status-indicator --
  // rich content, not a string. sb-section-head's `heading` input is
  // `string` only (Task 5's given design); there is no slot to project a
  // component into in its place.
  ['workspaces/trades/trade-detail.ts', ['head']],
]);

describe('the valence law is not forked', () => {
  for (const { name, source } of callSites()) {
    it(`${name} does not redefine .pos, .neg or .muted`, () => {
      const offenders = ['pos', 'neg', 'muted'].filter((cls) =>
        new RegExp(`^\\s*\\.${cls}\\s*[,{]`, 'm').test(source),
      );
      expect(offenders).toEqual([]);
    });
  }
});

describe('no call site redefines a promoted composite', () => {
  const PROMOTED = ['head', 'row-link', 'note', 'chips'];
  for (const { name, source } of callSites()) {
    it(`${name} defines none of the promoted classes`, () => {
      const allowed = new Set(PROMOTED_ALLOWLIST.get(name) ?? []);
      const offenders = PROMOTED.filter((cls) =>
        !allowed.has(cls) && new RegExp(`^\\s*\\.${cls}\\s*[,{]`, 'm').test(source),
      );
      expect(offenders).toEqual([]);
    });
  }
});
