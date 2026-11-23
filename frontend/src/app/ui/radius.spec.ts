import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { allSources } from './testing/all-sources';
import { StyleRule, styleRules } from './testing/style-rules';

/**
 * Spec v240 §3: --radius-sm is 6px, for swatches and cells. A bar or track
 * under 6px tall takes --pill-radius instead: a 6px corner on a 3px bar is
 * not a shape anyone chose. The gate reads every rule that rounds its
 * corners with --radius-sm and declares a px height; any height under 6px
 * fails. A height in %, rem or a token is not read (a % bar follows its
 * parent, which the gate checks in its own rule).
 */
const THIN_PX = 6;
const RADIUS_SM = /border(?:-[a-z]+)*-radius:\s*var\(--radius-sm\)/;
const PX_HEIGHT = /(?:^|[\s;{])height:\s*(\d+(?:\.\d+)?)px/g;

function thinOnRadiusSm(rule: StyleRule): boolean {
  if (!RADIUS_SM.test(rule.body)) return false;
  return [...rule.body.matchAll(PX_HEIGHT)].some(([, px]) => Number(px) < THIN_PX);
}

function offenders(name: string, source: string): string[] {
  return styleRules(name, source).filter(thinOnRadiusSm).map((rule) => rule.selector);
}

describe('v240 §3: thin bars are pills, not 6px corners', () => {
  it('flags a 3px track on --radius-sm and passes the same track on --pill-radius', () => {
    expect(offenders('a.css', '.t { height: 3px; border-radius: var(--radius-sm); }')).toEqual(['.t']);
    expect(offenders('a.css', '.t { height: 3px; border-radius: var(--pill-radius); }')).toEqual([]);
  });

  it('passes a 6px or taller bar, a min-height and a % height on --radius-sm', () => {
    const css = [
      '.a { height: 6px; border-radius: var(--radius-sm); }',
      '.b { height: 14px; border-radius: var(--radius-sm); }',
      '.c { min-height: 3px; border-radius: var(--radius-sm); }',
      '.d { height: 100%; border-radius: var(--radius-sm); }',
    ].join('\n');
    expect(offenders('a.css', css)).toEqual([]);
  });

  for (const { name, source } of allSources()) {
    it(`${name} rounds no bar under 6px tall with --radius-sm`, () => {
      expect(offenders(name, source)).toEqual([]);
    });
  }

  /* The six rules the gate found when it landed, plus magnitude's .bar,
   * which is height: 100% of its 3px host. */
  const PILLS: [file: string, selector: string][] = [
    ['app/ui/layout.ts', '.drag-handle'],
    ['app/ui/magnitude.ts', ':host'],
    ['app/ui/magnitude.ts', '.bar'],
    ['app/shell/scan-progress.css', '.track'],
    ['app/ui/chart-tooltip.ts', '.swatch'],
    ['app/ui/status-cell.ts', '.track'],
    ['app/ui/status-indicator.ts', '.track'],
  ];

  for (const [file, selector] of PILLS) {
    it(`${file} "${selector}" ends in --pill-radius`, () => {
      const rules = styleRules(file, readFileSync(join(process.cwd(), 'src', file), 'utf8'));
      const rule = rules.find((candidate) => candidate.selector === selector && /radius/.test(candidate.body));
      expect(rule, `${file} ${selector}`).toBeDefined();
      expect(rule!.body).toMatch(/border-radius:\s*var\(--pill-radius\)/);
    });
  }
});
