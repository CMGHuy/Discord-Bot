import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { callSites } from './testing/call-sites';

/**
 * Raw buttons that stay raw, each with the reason.
 *
 * One entry, and it should stay that way. A gate that starts life with a
 * fistful of exceptions teaches everyone that exceptions are normal.
 */
const RAW_BUTTON_ALLOWLIST = new Map<string, string>([
  // The whole toast IS the dismiss control -- a full-bleed surface with its
  // own kind-coloured background, not a button sitting inside a toast. Giving
  // it a variant would mean a variant used exactly once, which is a worse
  // answer than one justified exception.
  ['shell/toast-host.ts', 'class="toast elev-overlay"'],
]);

describe('no call site hand-rolls a button', () => {
  for (const { name, source } of callSites()) {
    it(`${name} routes every button through sb-button`, () => {
      const allowed = RAW_BUTTON_ALLOWLIST.get(name);
      const raw = [...source.matchAll(/<button\b[^>]*>/gs)]
        .map(([tag]) => tag.replace(/\s+/g, ' '))
        .filter((tag) => !tag.includes('sb-button'))
        .filter((tag) => !(allowed && tag.includes(allowed)));
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

/**
 * Colour literals outside tokens.css.
 *
 * Empty, and that is the point: `--chart-1..8` (wave `_4`) moved the last
 * eight out of `ui/line-chart.ts`. An entry here is a hue that escaped the
 * valence law.
 */
const HEX_ALLOWLIST = new Map<string, string>([]);

describe('no colour is declared outside tokens.css', () => {
  for (const { name, source } of callSites()) {
    it(`${name} declares no hex literal`, () => {
      const allowed = HEX_ALLOWLIST.get(name);
      // (?<!&) -- an HTML numeric character reference (&#9650; is a
      // triangle glyph, not a colour) matches this pattern just as well as
      // a real hex literal whenever its digits happen to fall in a-f/0-9.
      const hexes = [...source.matchAll(/(?<!&)#[0-9a-fA-F]{3,8}\b/g)]
        .map(([hex]) => hex)
        .filter((hex) => !(allowed && allowed.includes(hex)));
      expect(hexes).toEqual([]);
    });
  }
});

describe('every allowlist entry is justified', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/primitives.spec.ts'), 'utf8');

  // PROMOTED_ALLOWLIST is this file's own addition (v54 Task 5, the
  // trade-detail.ts rich-heading exception) -- the plan's own list here
  // named only the three it introduced, but the principle is general.
  for (const list of [
    'RAW_CONTROL_ALLOWLIST', 'RAW_BUTTON_ALLOWLIST', 'HEX_ALLOWLIST', 'PROMOTED_ALLOWLIST',
  ]) {
    it(`${list} has a comment above every entry`, () => {
      const body = SOURCE.slice(SOURCE.indexOf(`const ${list}`));
      const block = body.slice(0, body.indexOf(']);'));
      const entries = [...block.matchAll(/^\s*\[['"]/gm)];
      const comments = [...block.matchAll(/^\s*\/\//gm)];
      expect(comments.length).toBeGreaterThanOrEqual(entries.length);
    });
  }
});
