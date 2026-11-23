import { describe, expect, it } from 'vitest';

import { allSources } from './testing/all-sources';
import { styleRules } from './testing/style-rules';

/**
 * Spec v240 §3: headings keep weight 600 and gain −0.02em tracking at
 * --text-title and above (index Decision 7: the literal -0.02em; a display
 * figure's var(--figure-tracking) is the same -0.02em). Every rule set at
 * var(--text-title) is either a heading below, which must track, or a
 * pinned non-heading, so a new title-size rule has to be classified.
 */
const HEADINGS: [file: string, selector: string][] = [
  ['app/shell/login/login.css', '.mark'],
  ['app/ui/page.ts', '.title'],
  ['app/ui/section-head.ts', 'h1'],
  ['app/workspaces/dashboard/panels/portfolio-value.ts', '.figure'],
  ['app/workspaces/gallery/gallery.ts', 'h1'],
  ['app/workspaces/plans/plan-detail.ts', '.plan-title'],
  ['app/workspaces/trades/outcome-strip.ts', '.tile-value'],
  ['app/workspaces/trades/trade-detail.ts', '.trade-title'],
];

/** Title-size rules that are not headings: nothing to tighten. */
const NOT_HEADINGS: [file: string, selector: string, why: string][] = [
  ['app/ui/figure.ts', '.value', "the @container size step of a display figure; the base .value rule tracks"],
];

const TITLE_SIZE = /(?:^|[\s;{])font-size:\s*var\(--text-title\)/;
const TRACKED = /letter-spacing:\s*(?:-0\.02em|var\(--figure-tracking\))/;
const key = (file: string, selector: string) => `${file} ${selector}`;

const titleRules = allSources().flatMap(({ name, source }) =>
  styleRules(name, source)
    .filter((rule) => TITLE_SIZE.test(rule.body))
    .map((rule) => ({ key: key(name, rule.selector), body: rule.body })));

describe('v240 §3: headings at --text-title track at -0.02em', () => {
  for (const [file, selector] of HEADINGS) {
    it(`${file} "${selector}" tracks at -0.02em`, () => {
      const rule = titleRules.find((candidate) => candidate.key === key(file, selector));
      expect(rule, key(file, selector)).toBeDefined();
      expect(rule!.body).toMatch(TRACKED);
    });
  }

  it('classifies every rule set at --text-title as a heading or a pinned non-heading', () => {
    const known = new Set([...HEADINGS, ...NOT_HEADINGS].map(([file, selector]) => key(file, selector)));
    expect(titleRules.map((rule) => rule.key).filter((found) => !known.has(found))).toEqual([]);
  });

  it('keeps the non-heading list exact: each entry is still a title-size rule', () => {
    for (const [file, selector] of NOT_HEADINGS) {
      expect(titleRules.some((rule) => rule.key === key(file, selector)), key(file, selector)).toBe(true);
    }
  });
});
