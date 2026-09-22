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
  // v94: `workspaces/analytics/analytics.ts` used to be here and is not any
  // more. It is now a shell -- a tab strip, a scope bar and a switch -- and
  // it renders no fetched value of its own, so an sb-async on it would gate
  // nothing. Deleted deliberately, as this list's own rule requires. What
  // replaced it is panel-level: each tab under `workspaces/analytics/tabs/`
  // carries its own `sb-panel-error` and `sb-empty-state`, because v94 H4
  // makes every panel fail on its own terms rather than one gate blanking
  // a tab full of panels that arrived fine. ANALYTICS_PANELS below pins
  // that for the tabs that are finished; T2/T4/T5/T6 add theirs.
  'workspaces/risk/risk.ts',
  'workspaces/watchlist/watchlist.ts',
  'workspaces/versions/versions.ts',
  'workspaces/system/logs-tab.ts',
  'workspaces/system/settings-tab.ts',
  // v53's calendar.
  'workspaces/calendar/calendar.ts',
];

/**
 * v94's per-panel replacement for the Analytics workspace's one sb-async.
 * Enumerated for the same reason FETCHING is: a tab that loses its retry
 * affordance should fail here rather than quietly degrade to a blank panel
 * with no way back. Only the tabs whose own task has landed are listed.
 */
const ANALYTICS_PANELS = [
  'workspaces/analytics/tabs/overview.ts',
  'workspaces/analytics/tabs/execution.ts',
];

const sources = new Map(callSites().map(({ name, source }) => [name, source]));

describe('G1: every fetching surface uses sb-async', () => {
  for (const file of FETCHING) {
    it(`${file} wraps its fetch in sb-async`, () => {
      expect(sources.get(file) ?? '').toContain('<sb-async');
    });
  }

  for (const file of ANALYTICS_PANELS) {
    it(`${file} offers a retry on every panel that can fail`, () => {
      expect(sources.get(file) ?? '').toContain('<sb-panel-error');
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
