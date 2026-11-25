import { describe, expect, it } from 'vitest';

import { allSources, stripComments } from './testing/all-sources';
import { StyleRule, styleRules, withChartTokens } from './testing/style-rules';

/**
 * Spec v240 §2 and §11, two source gates over every style rule in src/
 * (allSources(): .ts styles: literals and .css files; specs and styles/
 * are out):
 *
 * - tabular: Jost is proportional, so a rule that reads --font-num or
 *   --font-mono, or styles a .num cell, sets
 *   `font-variant-numeric: tabular-nums` (index Decision 4: everywhere, no
 *   exemptions; it changes only digits).
 * - faint: --text-faint is a divider colour (the corrected spec §1), so no
 *   rule's `color` reads it; captions and hints use --text-muted (index
 *   Decision 3). border-color, background and fill stay legal.
 *
 * Both gates started (V240-9) with a pending set of the offenders they
 * found; part 3's sweeps emptied it area by area and V240-16 deleted it.
 * They now run over every source with no exemptions: fix the rule, never
 * add one back.
 */


/* A numeric face, with or without a var() fallback:
 * `var(--font-mono, monospace)` (calendar.ts .trade-id) counts too. */
const NUM_FACE = /var\(--font-(?:num|mono)\s*(?:,[^)]*)?\)/;
const NUM_CELL = /\.num(?![\w-])/;
const TABULAR = /font-variant-numeric:[^;]*tabular-nums/;
const FAINT_TEXT = /(?:^|[\s;{])color\s*:[^;]*var\(--text-faint\)/;

type Gate = {
  id: string;
  rule: string;
  offends: (rule: StyleRule) => boolean;
};

const GATES: Gate[] = [
  {
    id: 'tabular',
    rule: 'sets tabular-nums on every --font-num, --font-mono and .num rule',
    offends: (rule) => (NUM_FACE.test(rule.body) || NUM_CELL.test(rule.selector)) && !TABULAR.test(rule.body),
  },
  {
    id: 'faint',
    rule: 'paints no text in --text-faint',
    offends: (rule) => FAINT_TEXT.test(rule.body),
  },
];

/** Every source's style rules, with shared chart tokens resolved. */
const SOURCES = allSources().map(({ name, source }) => ({
  name,
  source,
  rules: styleRules(name, withChartTokens(source)),
}));

const offenders = (gate: Gate, rules: StyleRule[]) => rules.filter(gate.offends).map((rule) => rule.selector);

describe('v240 type gates: the predicates', () => {
  const [tabular, faint] = GATES;
  const rules = (css: string) => styleRules('a.css', css);

  it('tabular flags a numeric face or a .num cell without tabular-nums', () => {
    expect(offenders(tabular, rules('.a { font-family: var(--font-num); }'))).toEqual(['.a']);
    expect(offenders(tabular, rules('.b { font-family: var(--font-mono); }'))).toEqual(['.b']);
    expect(offenders(tabular, rules('td.num { text-align: right; }'))).toEqual(['td.num']);
  });

  it('tabular sees a numeric face behind a var() fallback', () => {
    expect(offenders(tabular, rules('.d { font-family: var(--font-mono, monospace); }'))).toEqual(['.d']);
    expect(offenders(tabular, rules('.e { font-family: var(--font-num , ui-monospace, monospace); }'))).toEqual(['.e']);
    expect(offenders(tabular, rules('.f { font-family: var(--font-mono, monospace); font-variant-numeric: tabular-nums; }'))).toEqual([]);
    expect(offenders(tabular, rules('.g { font-family: var(--font-numeric, monospace); }'))).toEqual([]);
  });

  it('tabular passes the same rules with tabular-nums, and ignores .number and .num-x', () => {
    expect(offenders(tabular, rules('.a { font-family: var(--font-num); font-variant-numeric: tabular-nums; }'))).toEqual([]);
    expect(offenders(tabular, rules('.number { gap: 0; } .num-x { gap: 0; } .c { font-family: var(--font-sans); }'))).toEqual([]);
  });

  it('faint flags color but not border-color, background or fill', () => {
    expect(offenders(faint, rules('.a { color: var(--text-faint); }'))).toEqual(['.a']);
    expect(offenders(faint, rules('.b{gap:0;color:var(--text-faint)}'))).toEqual(['.b']);
    const legal = '.c { border-color: var(--text-faint); background: var(--text-faint); fill: var(--text-faint); }';
    expect(offenders(faint, rules(legal))).toEqual([]);
  });
});

for (const gate of GATES) {
  describe(`v240 type gate: ${gate.id}`, () => {
    for (const { name, rules } of SOURCES) {
      it(`${name} ${gate.rule}`, () => {
        expect(offenders(gate, rules)).toEqual([]);
      });
    }
  });
}

describe('v240 type gates: they still have something to check', () => {
  it('finds the numeric rules (78 at 146b4600), so an empty parse cannot pass', () => {
    const numeric = SOURCES.flatMap(({ rules }) => rules)
      .filter((rule) => NUM_FACE.test(rule.body) || NUM_CELL.test(rule.selector));
    expect(numeric.length).toBeGreaterThanOrEqual(70);
  });
});

describe('v240 type gates: nothing hides from them', () => {
  /* The chart components whose styles use shared token interpolation. */
  const INTERPOLATED = [
    'app/ui/bar-list.ts',
    'app/ui/chart-tooltip.ts',
    'app/ui/dot-plot.ts',
    'app/ui/gauge.ts',
    'app/ui/histogram.ts',
    'app/ui/line-chart.ts',
    'app/ui/share-bar.ts',
    'app/ui/sparkline.ts',
    'app/ui/strip-plot.ts',
    'app/ui/waterfall.ts',
  ];
  const holdsExpr = (rules: StyleRule[]) => rules.some((rule) => `${rule.selector} ${rule.body}`.includes('__expr__'));

  it('pins the files whose style rules interpolate, read raw', () => {
    const raw = SOURCES.filter(({ name, source }) => holdsExpr(styleRules(name, source))).map(({ name }) => name);
    expect(raw).toEqual(INTERPOLATED);
  });

  it('leaves no interpolation in any rule once shared chart tokens are substituted', () => {
    expect(SOURCES.filter(({ rules }) => holdsExpr(rules)).map(({ name }) => name)).toEqual([]);
  });

  const INLINE_FAINT = /(?:^|[\s;{"'])color\s*:\s*var\(--text-faint\)/g;
  const BOUND_FAINT = /\[style\.color\]\s*=\s*"[^"]*--text-faint/;
  const count = (text: string) => (text.match(INLINE_FAINT) ?? []).length;

  for (const { name, source, rules } of SOURCES) {
    it(`${name} paints no template or inline text in --text-faint`, () => {
      const code = stripComments(source);
      const inRules = rules.reduce((n, rule) => n + count(` ${rule.body}`), 0);
      expect(count(code)).toBe(inRules);
      expect(code).not.toMatch(BOUND_FAINT);
    });
  }
});
