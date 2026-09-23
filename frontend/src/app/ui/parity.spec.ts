import { describe, expect, it } from 'vitest';

import { VIEWPORT_ORDER, assertReachable, isInline } from './priority';
import { TRADES_CONTROLS } from '../workspaces/trades/trades';
import { tradeColumns } from '../workspaces/trades/trades.columns';
import { DASHBOARD_COLUMNS } from '../workspaces/dashboard/dashboard';
import { WATCHLIST_COLUMNS, WATCHLIST_CONTROLS } from '../workspaces/watchlist/watchlist';
import { SCAN_CONTROLS } from '../workspaces/system/scan-tab';

/* v95 §9. Parity is a promise about REACHABILITY, not visibility. A demoted
 * item is fine; an item demoted to a destination that does not exist, or that
 * is itself demoted at the same viewport, is not.
 *
 * The plan's own sketch imported a `TRADE_COLUMNS` static export from
 * trades.columns -- there is no such export. trades.ts and dashboard.ts both
 * build their columns from the one shared `tradeColumns()` function
 * (dashboard.ts's own DASHBOARD_COLUMNS is `tradeColumns()` called with the
 * default clock), so 'trades columns' below calls it directly instead. */

const SURFACES = {
  'trades controls': TRADES_CONTROLS.map((c) => ({ ...c, demotesTo: 'sheet' as const })),
  'trades columns': tradeColumns().map((c) => ({ id: c.key, inlineFrom: c.inlineFrom, demotesTo: 'expansion' as const })),
  'dashboard columns': DASHBOARD_COLUMNS.map((c) => ({ id: c.key, inlineFrom: c.inlineFrom, demotesTo: 'expansion' as const })),
  'watchlist columns': WATCHLIST_COLUMNS.map((c) => ({ id: c.key, inlineFrom: c.inlineFrom, demotesTo: 'expansion' as const })),
  'watchlist controls': WATCHLIST_CONTROLS.map((c) => ({ ...c, demotesTo: 'sheet' as const })),
  'scan controls': SCAN_CONTROLS.map((c) => ({ ...c, demotesTo: 'sheet' as const })),
};

describe('content parity', () => {
  it.each(Object.entries(SURFACES))('%s: every item is reachable at every viewport', (_name, decls) => {
    expect(assertReachable(decls)).toEqual([]);
  });

  it.each(Object.entries(SURFACES))('%s: every id is unique', (_name, decls) => {
    const ids = decls.map((d) => d.id);
    expect(ids).toEqual([...new Set(ids)]);
  });

  it('every surface keeps at least one item inline at xs', () => {
    // A surface where everything demotes renders as an empty bar above a
    // sheet button -- technically parity, practically a blank screen.
    for (const [name, decls] of Object.entries(SURFACES)) {
      const inline = decls.filter((d) => isInline(d.inlineFrom, 'xs'));
      expect(inline.length, `${name} has nothing inline at xs`).toBeGreaterThan(0);
    }
  });

  it('covers every viewport in VIEWPORT_ORDER, so a new band cannot be forgotten', () => {
    expect(VIEWPORT_ORDER).toHaveLength(5);
  });
});
