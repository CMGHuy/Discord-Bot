import { describe, expect, it } from 'vitest';

import { allSources } from './testing/all-sources';
import { StyleRule, styleRules, withChartChrome } from './testing/style-rules';

/**
 * Spec v240 §1 (corrected): mint never marks navigation. --pos and --neg
 * mean money, direction and good/bad status; navigation, the brand,
 * active and current states and focus rings use --accent. Index
 * Decision 5:
 *  (a) no rule whose selector holds :focus, [aria-current or .active reads
 *      --pos/--neg, anywhere;
 *  (b) no rule in a nav file reads them; in shell.css, the rules whose
 *      selector names the rail, brand, wordmark, nav or a tab.
 */
const NAV_FILES: readonly string[] = [
  'app/shell/breadcrumb.ts',
  'app/shell/more-sheet.ts',
  'app/shell/phone-tab-bar.ts',
  'app/shell/section-tabs.ts',
];

const SHELL_CSS = 'app/shell/shell.css';
const SHELL_NAV_SELECTOR = /rail|brand|wordmark|nav|tab/;
const STATE_SELECTOR = /:focus|\[aria-current|\.active(?![\w-])/;
const MONEY = /var\(--(?:pos|neg)\b/;
const RING_FROM_MONEY = /(?:^|[\s;{])(?:outline(?:-color)?|box-shadow)\s*:[^;]*var\(--(?:pos|neg)\b/;

/** Status that happens to change on focus, never a focus ring: each entry
 *  is a [file, exact selector] the scan lets read --pos/--neg. */
const STATUS_STATES: [file: string, selector: string, why: string][] = [
  [
    'app/ui/button.ts',
    ':host(.danger-icon:not([disabled]):hover), :host(.danger-icon:not([disabled]):focus-visible)',
    'the delete icon turns red on hover or focus: danger status; the ring stays :host(:focus-visible) accent',
  ],
];

const isStatus = (name: string, rule: StyleRule) =>
  STATUS_STATES.some(([file, selector]) => file === name && selector === rule.selector);

function isNavRule(name: string, rule: StyleRule): boolean {
  if (NAV_FILES.includes(name)) return true;
  return name === SHELL_CSS && SHELL_NAV_SELECTOR.test(rule.selector);
}

/** The selectors in one file that break (a) or (b). */
function moneyOffenders(name: string, source: string): string[] {
  return styleRules(name, withChartChrome(source))
    .filter((rule) => MONEY.test(rule.body))
    .filter((rule) => isNavRule(name, rule) || (STATE_SELECTOR.test(rule.selector) && !isStatus(name, rule)))
    .map((rule) => rule.selector);
}

describe('v240: the money-colour scan, on fixtures', () => {
  it('flags a focus ring, an active state and an aria-current link in --pos/--neg anywhere', () => {
    const css = [
      '.x:focus-visible { outline: 1px solid var(--neg); }',
      '.tab.active { color: var(--pos); }',
      'a[aria-current="page"] { border-color: var(--pos-soft); }',
      '.row:focus-within { background: var(--accent-soft); }',
    ].join('\n');
    expect(moneyOffenders('app/ui/x.css', css)).toEqual(['.x:focus-visible', '.tab.active', 'a[aria-current="page"]']);
  });

  it('flags every --pos/--neg rule in a nav file, and only rail/brand/nav/tab rules in shell.css', () => {
    expect(moneyOffenders('app/shell/breadcrumb.ts', 'styles: `.sep { color: var(--neg); }`')).toEqual(['.sep']);
    const shell = '.rail-link { color: var(--pos); }\n.killswitch-strip { color: var(--neg); }';
    expect(moneyOffenders(SHELL_CSS, shell)).toEqual(['.rail-link']);
  });

  it('leaves money and status rules elsewhere alone, and an .active-x class is not .active', () => {
    const css = '.pnl.neg { color: var(--neg); }\n.chip.good { color: var(--pos); }\n.active-row { color: var(--pos); }';
    expect(moneyOffenders('app/ui/x.css', css)).toEqual([]);
  });
});

describe('v240: navigation, brand, active and focus never read --pos/--neg', () => {
  const SOURCES = allSources();

  for (const { name, source } of SOURCES) {
    it(`${name} keeps --pos/--neg off nav, active and focus rules`, () => {
      expect(moneyOffenders(name, source)).toEqual([]);
    });
  }

  it('scans nav files that exist', () => {
    const names = new Set(SOURCES.map(({ name }) => name));
    expect(NAV_FILES.filter((file) => !names.has(file))).toEqual([]);
  });

  it("finds the shell.css nav rules (the selector filter still bites)", () => {
    const shell = SOURCES.find(({ name }) => name === SHELL_CSS)!;
    const navRules = styleRules(SHELL_CSS, shell.source).filter((rule) => SHELL_NAV_SELECTOR.test(rule.selector));
    expect(navRules.map((rule) => rule.selector)).toContain('.rail-link.active');
    expect(navRules.map((rule) => rule.selector)).toContain('.brand .word');
  });

  for (const [file, selector, why] of STATUS_STATES) {
    it(`${file} "${selector}" is still status on --pos/--neg and paints no ring from them (${why})`, () => {
      const source = SOURCES.find(({ name }) => name === file)!.source;
      const rule = styleRules(file, source).find((candidate) => candidate.selector === selector);
      expect(rule, `${file} ${selector}`).toBeDefined();
      expect(rule!.body).toMatch(MONEY);
      expect(rule!.body).not.toMatch(RING_FROM_MONEY);
    });
  }
});
