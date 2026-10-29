import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { stripComments } from './testing/all-sources';

/**
 * Spec v195 Phase 6: the SVG chart primitives hold no chart-local colour --
 * every fill, stroke and text colour reads a token -- and none sets readable
 * text in --text-faint, the rule, divider and disabled-glyph colour
 * (correction 13). primitives.spec.ts already bans hex and rgb()/hsl()
 * literals app-wide; this closes what that pattern cannot see: a named colour
 * keyword, the other CSS colour functions, a color-mix() fed a literal, and
 * faint text. A SOURCE scan, because jsdom resolves neither a component's
 * var() chain nor an SVG presentation attribute. Comments are stripped first,
 * so prose like "green or red" in a doc comment is not a finding.
 */

/** The spec's list (sparkline .. timeline), plus the line chart small multiples draws with. */
const SVG_PRIMITIVES = [
  'sparkline', 'histogram', 'heat-grid', 'gauge', 'waterfall', 'donut', 'dot-plot', 'strip-plot',
  'matrix', 'small-multiples', 'line-chart', 'timeline',
] as const;

/** Selectors allowed to keep --text-faint, each with its reason. */
const FAINT_ALLOWED: Partial<Record<(typeof SVG_PRIMITIVES)[number], string[]>> = {
  // The '—' a matrix prints for a missing cell: a disabled glyph, the one
  // non-rule use correction 13 allows.
  matrix: ['.missing'],
};

const read = (stem: string) =>
  stripComments(readFileSync(join(process.cwd(), 'src/app/ui', `${stem}.ts`), 'utf8'));

/** A named colour keyword as the value of a colour property or an SVG paint attribute. */
const NAMED_COLOUR =
  /(?<![-\w])(?:color|fill|stroke|background(?:-color)?|stop-color|border(?:-\w+)?-color|outline-color)\s*[:=]\s*["'`]?\s*(?:red|green|blue|white|black|gr[ae]y|orange|yellow|purple|pink|cyan|magenta|lime|navy|teal|silver|maroon|olive|aqua|fuchsia)\b/gi;

/** CSS colour functions other than color-mix(), whose inputs colorMixArgs/residue check. */
const COLOUR_FUNCTION = /\b(?:oklch|oklab|lab|lch|hwb|color)\(/g;

/** `color:` as the whole property name (so `border-color:` stays a rule) set to --text-faint. */
const FAINT_TEXT = /(?<![-\w])color:\s*var\(--text-faint\)/g;

/** Every color-mix() call's argument list, matched by balanced parentheses. */
function colorMixArgs(source: string): string[] {
  const out: string[] = [];
  const head = 'color-mix(';
  for (let at = source.indexOf(head); at !== -1; at = source.indexOf(head, at + 1)) {
    let depth = 0;
    let end = at + head.length - 1;
    for (; end < source.length; end += 1) {
      if (source[end] === '(') depth += 1;
      else if (source[end] === ')' && --depth === 0) break;
    }
    out.push(source.slice(at + head.length, end));
  }
  return out;
}

/** What a color-mix() argument list holds besides tokens, its space, weights and `transparent`: '' when it mixes tokens only. */
function residue(args: string): string {
  return args
    .replace(/\$\{[^}]*\}/g, '')
    .replace(/var\(\s*(?:--[\w-]+)?\s*\)/g, '')
    .replace(/\bin\s+(?:srgb|oklab|oklch|lab|lch|hsl|hwb|display-p3)\b/g, '')
    .replace(/\b(?:transparent|currentColor)\b/g, '')
    .replace(/\d+(?:\.\d+)?%/g, '')
    .replace(/[\s,%]/g, '');
}

/** The selector a declaration sits under: the last line of the text between the previous `}` and its `{`. */
function selectorAt(source: string, index: number): string {
  const open = source.lastIndexOf('{', index);
  const close = source.lastIndexOf('}', open);
  return source.slice(close + 1, open).split('\n').pop()!.trim();
}

describe('the scanners (v195 Phase 6)', () => {
  it('catch a named colour and leave white-space and tokens alone', () => {
    expect('.x { fill: red; }'.match(NAMED_COLOUR)).toHaveLength(1);
    expect('<rect fill="white" />'.match(NAMED_COLOUR)).toHaveLength(1);
    expect('.x { white-space: nowrap; color: var(--text); fill: none; }'.match(NAMED_COLOUR)).toBeNull();
  });

  it('catch a colour function and leave color-mix() to the residue check', () => {
    expect('.x { color: oklch(70% 0.1 150); }'.match(COLOUR_FUNCTION)).toHaveLength(1);
    expect('.x { background: color-mix(in oklab, var(--pos) 70%, var(--surface)); }'.match(COLOUR_FUNCTION)).toBeNull();
    expect(colorMixArgs('a{b:color-mix(in oklab,var(--pos) 70%,var(--surface))}').map(residue)).toEqual(['']);
    expect(colorMixArgs('a{b:color-mix(in oklab,var(--text) ${Math.round(70-(n>1?i/(n-1):0)*45)}%,transparent)}').map(residue))
      .toEqual(['']);
    expect(colorMixArgs('a{b:color-mix(in srgb,#fff 10%,var(--bg))}').map(residue)).toEqual(['#fff']);
  });

  it('name the selector a faint text colour sits under, multi-line or minified', () => {
    const multi = '.b5 { background: var(--quality-5); }\n    .missing { color: var(--text-faint); background: none; }';
    expect(selectorAt(multi, multi.indexOf('color:'))).toBe('.missing');
    const mini = 'table{width:100%}th{font-size:var(--text-micro);color:var(--text-faint)}';
    expect(selectorAt(mini, mini.indexOf('color:'))).toBe('th');
    expect('.x { border-color: var(--text-faint); }'.match(FAINT_TEXT)).toBeNull();
  });
});

describe('the SVG chart primitives read tokens only (v195 Phase 6)', () => {
  for (const stem of SVG_PRIMITIVES) {
    describe(`${stem}.ts`, () => {
      const source = read(stem);

      it('names no colour keyword', () => expect(source.match(NAMED_COLOUR) ?? []).toEqual([]));

      it('calls no colour function but color-mix()', () => expect(source.match(COLOUR_FUNCTION) ?? []).toEqual([]));

      it('mixes tokens only', () => expect(colorMixArgs(source).map(residue).filter(Boolean)).toEqual([]));

      it('draws in tokens', () => expect(source).toMatch(/var\(\s*(?:--[\w-]+|\$\{CHART_CHROME\.\w+\})/));

      it('sets no readable text in --text-faint', () => {
        const hits = [...source.matchAll(FAINT_TEXT)].map((m) => selectorAt(source, m.index ?? 0));
        expect(hits).toEqual(FAINT_ALLOWED[stem] ?? []);
      });
    });
  }

  it('every FAINT_ALLOWED entry still matches a faint declaration (no stale allowance)', () => {
    for (const [stem, selectors] of Object.entries(FAINT_ALLOWED)) {
      const source = read(stem);
      const found = [...source.matchAll(FAINT_TEXT)].map((m) => selectorAt(source, m.index ?? 0));
      for (const selector of selectors ?? []) expect(found, stem).toContain(selector);
    }
  });
});
