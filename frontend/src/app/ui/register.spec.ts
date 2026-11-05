import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { callSites } from './testing/call-sites';
import { resolveToken } from './testing/resolve-token';

const GLOBAL = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');

const rule = (name: string) => GLOBAL.match(new RegExp(`\\.${name}\\s*\\{[^}]*\\}`, 's'))?.[0] ?? '';

describe('the two registers', () => {
  it('defines both', () => {
    expect(rule('register-presentation')).not.toBe('');
    expect(rule('register-instrument')).not.toBe('');
  });

  for (const name of ['register-presentation', 'register-instrument']) {
    it(`${name} introduces no off-scale value`, () => {
      // Every length must come from a token. A register that needed a new
      // size would be a review defect, exactly as an off-scale literal is.
      const literals = [...rule(name).matchAll(/:\s*([0-9.]+)px/g)]
        .map(([, v]) => Number(v))
        .filter((v) => v > 2);
      expect(literals).toEqual([]);
    });
  }

  it('gives the two registers different density', () => {
    expect(rule('register-presentation')).not.toBe(rule('register-instrument'));
  });
});

const WORKSPACE_ROOTS = [
  'workspaces/dashboard/dashboard.ts',
  'workspaces/trades/trades.ts',
  'workspaces/analytics/analytics.ts',
  'workspaces/risk/risk.ts',
  'workspaces/watchlist/watchlist.ts',
  'workspaces/versions/versions.ts',
  'workspaces/system/system.ts',
  'workspaces/calendar/calendar.ts',
];

const sources = new Map(callSites().map(({ name, source }) => [name, source]));

describe('every workspace declares a register', () => {
  for (const file of WORKSPACE_ROOTS) {
    it(`${file} declares one`, () => {
      expect(sources.get(file) ?? '').toMatch(/register-(presentation|instrument)/);
    });
  }
});

describe('both registers are actually used', () => {
  const all = [...sources.values()].join('\n');
  // If everything ended up in one register, D1 was applied mechanically.
  it('uses presentation somewhere', () => expect(all).toContain('register-presentation'));
  it('uses instrument somewhere', () => expect(all).toContain('register-instrument'));
});

/* v195 §1.4 (correction 11): the instrument register's figure was the 13px
 * table step, which put entry/stop/target/size/risk figures on Trades, Risk
 * and System under the 14px order-figure floor. It is the body step now. */
describe('v195 §1.4: order figures never shrink', () => {
  it('sets the instrument figure on the 14px body step', () => {
    expect(rule('register-instrument')).toContain('--register-figure: var(--text-body);');
    expect(rule('register-instrument')).not.toContain('--register-figure: var(--text-table);');
    expect(resolveToken('--text-body')).toBe('calc(14px * 1)');
  });

  it('keeps the presentation figure on the 28px metric step', () => {
    expect(rule('register-presentation')).toContain('--register-figure: var(--text-metric);');
  });
});
