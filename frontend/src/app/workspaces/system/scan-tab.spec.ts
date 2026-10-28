import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { SCAN_CONTROLS } from './scan-tab';

describe('Scan tab controls', () => {
  it('declares a floor for every control', () => {
    expect(SCAN_CONTROLS.every((c) => c.inlineFrom !== undefined)).toBe(true);
  });

  it('keeps every scan command inline -- three short buttons never need a sheet', () => {
    expect(SCAN_CONTROLS.every((c) => c.inlineFrom === 'xs')).toBe(true);
  });
});

describe('Scan tab after the Providers split (v195 §5.1)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/system/scan-tab.ts'), 'utf8');

  it('no longer carries the provider and swallowed-error panels; Providers does', () => {
    expect(src).not.toContain('sb-provider-health-panel');
    expect(src).not.toContain('sb-swallowed-errors-panel');
    expect(src).not.toContain('store.health');
  });
});
