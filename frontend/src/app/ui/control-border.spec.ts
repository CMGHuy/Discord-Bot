import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { styleRules } from './testing/style-rules';

/**
 * Spec v240 §1: inputs, selects and segmented controls are outlined in
 * --control-border (doctena blue in Navy, 3.28:1 on --surface, WCAG 1.4.11;
 * the strong hairline under Black, index Decision 1). --border stays the
 * decorative panel and rule colour. One row per control rule: the file,
 * relative to src/, and its exact selector (the first rule with it).
 */
const CONTROLS: [file: string, selector: string][] = [
  ['app/ui/form-controls.ts', 'select'],
  ['app/ui/form-controls.ts', 'input'],
  ['app/ui/date-range.ts', 'input'],
  ['app/ui/segmented.ts', '.track'],
  ['app/ui/pagination.ts', '.per-page select, .jump'],
  ['app/ui/data-table/data-table.ts', '.phone-sort select'],
];

const rulesOf = (file: string) => styleRules(file, readFileSync(join(process.cwd(), 'src', file), 'utf8'));

describe('v240: controls are outlined in --control-border', () => {
  for (const [file, selector] of CONTROLS) {
    it(`${file} "${selector}" draws its border in --control-border`, () => {
      const rule = rulesOf(file).find((candidate) => candidate.selector === selector);
      expect(rule, `${file} ${selector}`).toBeDefined();
      expect(rule!.body).toContain('border: 1px solid var(--control-border);');
      expect(rule!.body).not.toContain('--border-strong');
    });
  }

  it('leaves no input or select rule in those files on the strong hairline', () => {
    const files = [...new Set(CONTROLS.map(([file]) => file))];
    const offenders = files.flatMap((file) =>
      rulesOf(file)
        .filter((rule) => /(^|[\s,])(input|select)\b/.test(rule.selector))
        .filter((rule) => /\bborder:[^;]*var\(--border-strong\)/.test(rule.body))
        .map((rule) => `${file} ${rule.selector}`));
    expect(offenders).toEqual([]);
  });
});
