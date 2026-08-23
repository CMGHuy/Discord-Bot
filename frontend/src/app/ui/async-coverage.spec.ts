import { describe, expect, it } from 'vitest';

import { callSites } from './testing/call-sites';

/* The plan's given code for this gate imported readFileSync/join from
 * node:fs/node:path but never called them -- callSites() already reads the
 * files. Dropped as dead imports rather than transcribed unused. */

/**
 * Surfaces that fetch. Enumerated, not inferred: a workspace that stops
 * fetching should make this list fail so someone deletes the entry
 * deliberately, rather than the gate quietly covering one file less.
 */
const FETCHING = [
  'workspaces/dashboard/dashboard.ts',
  'workspaces/trades/trades.ts',
  'workspaces/trades/trade-detail.ts',
  'workspaces/analytics/analytics.ts',
  'workspaces/risk/risk.ts',
  'workspaces/watchlist/watchlist.ts',
  'workspaces/versions/versions.ts',
  'workspaces/system/logs-tab.ts',
  'workspaces/system/settings-tab.ts',
  // v53's calendar.
  'workspaces/calendar/calendar.ts',
];

const sources = new Map(callSites().map(({ name, source }) => [name, source]));

describe('G1: every fetching surface uses sb-async', () => {
  for (const file of FETCHING) {
    it(`${file} wraps its fetch in sb-async`, () => {
      expect(sources.get(file) ?? '').toContain('<sb-async');
    });
  }
});

describe('G2: every sb-async names which empty it is', () => {
  for (const { name, source } of callSites()) {
    const uses = [...source.matchAll(/<sb-async\b[^>]*>/gs)].map(([tag]) => tag);
    if (!uses.length) continue;
    it(`${name} passes emptyReason on every sb-async`, () => {
      expect(uses.filter((tag) => !tag.includes('emptyReason'))).toEqual([]);
    });
  }
});

describe('the two empty reasons are both actually used', () => {
  const all = [...sources.values()].join('\n');
  // If every surface picked the same reason, the distinction was applied
  // mechanically rather than thought about -- which is the failure D3 exists
  // to prevent, and it would pass a per-file check.
  it('uses measured-zero somewhere', () => expect(all).toContain("'measured-zero'"));
  it('uses no-data-yet somewhere', () => expect(all).toContain("'no-data-yet'"));
});

describe('no workspace still hand-rolls a loading or error branch', () => {
  for (const { name, source } of callSites()) {
    if (!source.includes('<sb-async')) continue;
    it(`${name} has no leftover skeleton or error markup`, () => {
      expect(source).not.toMatch(/class="(skeleton|loading|error-panel)"/);
    });
  }
});
