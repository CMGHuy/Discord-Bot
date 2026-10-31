import { describe, expect, it } from 'vitest';

import { Ticker, TradeRow } from '../../api/models';
import { NAV_GROUPS } from '../nav';
import {
  PALETTE_GROUP_LABELS,
  PREFERENCE_ITEMS,
  PaletteItem,
  RECENT_TRADES,
  TAB_PAGES,
  emptyQueryItems,
  pageItems,
  rankPaletteItems,
  tickerItems,
  tradeItems,
} from './palette-items';

const ticker = (symbol: string, company_name: string | null): Ticker =>
  ({ symbol, company_name, open_trades: 0, closed_trades: 0 }) as Ticker;

const trade = (id: string, symbol: string, status: string, created_at: string | null, extra: Partial<TradeRow> = {}): TradeRow =>
  ({ id, ticker: symbol, status, strategy: 'RSI', created_at, opened_at: null, ...extra }) as TradeRow;

const labels = (items: readonly PaletteItem[]) => items.map((item) => item.label);
const RAIL = NAV_GROUPS.flatMap((group) => group.entries.map((entry) => entry.label));

describe('palette items (v195 §3.1)', () => {
  it('lists every rail entry as a page, in rail order, then the workspace tabs', () => {
    const pages = pageItems();
    expect(labels(pages.slice(0, RAIL.length))).toEqual(RAIL);
    expect(pages.slice(RAIL.length)).toEqual([...TAB_PAGES]);
    expect(pages.every((item) => item.group === 'pages')).toBe(true);
    expect(pages.find((item) => item.label === 'Risk')).toMatchObject({ route: '/risk', sub: 'Monitor' });
  });

  it('opens a workspace tab through its ?tab= value, never the default tab', () => {
    expect(TAB_PAGES.find((item) => item.label === 'Logs'))
      .toMatchObject({ route: '/system', queryParams: { tab: 'logs' }, sub: 'System' });
    expect(TAB_PAGES.map((item) => `${item.route}?tab=${item.queryParams!['tab']}`)).toEqual([
      '/analytics?tab=attribution', '/analytics?tab=execution', '/analytics?tab=edge',
      '/analytics?tab=pipeline', '/analytics?tab=tuning', '/analytics?tab=partials',
      '/reports?tab=gates',
      '/system?tab=scan', '/system?tab=providers', '/system?tab=logs',
      '/watchlist?tab=earnings',
    ]);
  });

  it('makes a ticker item from the watchlist row, linking its detail page', () => {
    expect(tickerItems([ticker('NVDA', 'NVIDIA Corp'), ticker('SPY', null)])).toEqual([
      { key: 'ticker:NVDA', group: 'tickers', label: 'NVDA', sub: 'NVIDIA Corp', route: '/watchlist/NVDA' },
      { key: 'ticker:SPY', group: 'tickers', label: 'SPY', route: '/watchlist/SPY' },
    ]);
  });

  it('sends an unfilled plan to /plans/:id and everything else to /trades/:id', () => {
    const [plan, open, closed] = tradeItems([
      trade('901', 'AMD', 'PENDING', '2026-10-26T09:00:00Z'),
      trade('812', 'NVDA', 'ACTIVE', '2026-10-20T09:00:00Z'),
      trade('700', 'MSFT', 'CLOSED', null, { opened_at: '2026-09-01T14:30:00Z', strategy: null }),
    ]);
    expect(plan).toEqual({
      key: 'trade:901', group: 'trades', label: 'AMD #901', sub: 'Plan · RSI',
      route: '/plans/901', recency: Date.parse('2026-10-26T09:00:00Z'),
    });
    expect(open).toMatchObject({ label: 'NVDA #812', sub: 'Active · RSI', route: '/trades/812' });
    // No created_at: the open time stands in. No strategy: the status alone.
    expect(closed).toMatchObject({ sub: 'Closed', route: '/trades/700', recency: Date.parse('2026-09-01T14:30:00Z') });
  });

  it('gives a row with no readable time a recency of 0, so it sorts last and never throws', () => {
    expect(tradeItems([trade('1', 'X', 'ACTIVE', 'not a date')])[0].recency).toBe(0);
    expect(tradeItems([trade('2', 'Y', 'ACTIVE', null)])[0].recency).toBe(0);
  });

  it('offers the density preference both ways, applied in place', () => {
    expect(PREFERENCE_ITEMS.map((item) => [item.label, item.density, item.route])).toEqual([
      ['Density: Dense', 'dense', null],
      ['Density: Comfortable', 'comfortable', null],
    ]);
    expect(PALETTE_GROUP_LABELS).toEqual({ tickers: 'Ticker', trades: 'Trade', pages: 'Page', preferences: 'Preference' });
  });

  it('registers no destructive or money-moving action: every item navigates or sets density', () => {
    const all = [
      ...tickerItems([ticker('NVDA', 'NVIDIA Corp')]),
      ...tradeItems([trade('812', 'NVDA', 'ACTIVE', null)]),
      ...pageItems(),
      ...PREFERENCE_ITEMS,
    ];
    const allowedKeys = new Set(['key', 'group', 'label', 'sub', 'route', 'queryParams', 'density', 'recency']);
    for (const item of all) {
      // An item is data, never a callback: no field can carry an action.
      expect(Object.keys(item).filter((key) => !allowedKeys.has(key)), item.key).toEqual([]);
      expect(Object.values(item).some((value) => typeof value === 'function'), item.key).toBe(false);
      expect(item.route !== null || item.density !== undefined, item.key).toBe(true);
      expect(`${item.label} ${item.sub ?? ''} ${item.route ?? ''}`, item.key)
        .not.toMatch(/kill|halt|restart|stop bot|clear|delete|close all|discard|scan now|order/i);
    }
  });
});

describe('palette ranking (v195 §3.1)', () => {
  const items: PaletteItem[] = [
    ...tickerItems([ticker('ARIS', 'Aris Water'), ticker('RIOT', 'Riot Platforms'), ticker('AAPL', 'Apple Inc')]),
    ...tradeItems([trade('812', 'NVDA', 'ACTIVE', null), trade('8120', 'AMD', 'CLOSED', null)]),
    ...pageItems(),
    ...PREFERENCE_ITEMS,
  ];

  it('ranks a ticker prefix first, then a name prefix, then a substring', () => {
    // RIOT: ticker prefix. Risk: page-name prefix. ARIS (a ticker) and
    // Attribution (a tab) hold "ri" only inside: substrings, tickers first.
    const ranked = labels(rankPaletteItems('ri', items));
    expect(ranked.slice(0, 2)).toEqual(['RIOT', 'Risk']);
    expect(ranked.indexOf('ARIS')).toBeGreaterThan(ranked.indexOf('Risk'));
    expect(ranked.indexOf('ARIS')).toBeLessThan(ranked.indexOf('Attribution'));
  });

  it('matches a company-name prefix below every ticker prefix', () => {
    expect(labels(rankPaletteItems('apple', items))).toEqual(['AAPL']);
    // ARIS and AAPL (tickers, input order), then AMD #8120 (a trade ticker):
    // all tier 0, so group order then input order decides.
    expect(labels(rankPaletteItems('a', items)).slice(0, 3)).toEqual(['ARIS', 'AAPL', 'AMD #8120']);
  });

  it('matches a trade by ticker or by id, with or without the #', () => {
    expect(labels(rankPaletteItems('nvda', items))[0]).toBe('NVDA #812');
    expect(labels(rankPaletteItems('812', items))).toEqual(['NVDA #812', 'AMD #8120']);
    expect(labels(rankPaletteItems('#8120', items))).toEqual(['AMD #8120']);
  });

  it('keeps the group order on a tie: pages before preferences', () => {
    // Dashboard and Density: ... are both name prefixes of "d" (tier 1).
    const ranked = labels(rankPaletteItems('d', items));
    expect(ranked.indexOf('Dashboard')).toBeLessThan(ranked.indexOf('Density: Dense'));
    expect(ranked.indexOf('Density: Dense')).toBeLessThan(ranked.indexOf('Density: Comfortable'));
  });

  it('is case-insensitive and ignores surrounding spaces', () => {
    expect(labels(rankPaletteItems('  RISK ', items))[0]).toBe('Risk');
  });

  it('returns nothing for an empty query or a symbol that is not on the watchlist', () => {
    expect(rankPaletteItems('', items)).toEqual([]);
    expect(rankPaletteItems('   ', items)).toEqual([]);
    expect(rankPaletteItems('ZZZZ', items)).toEqual([]);
  });

  it('never reorders the list it is given', () => {
    const before = labels(items);
    rankPaletteItems('ri', items);
    expect(labels(items)).toEqual(before);
  });
});

describe('the empty query (v195 §3.1)', () => {
  it('shows the rail pages, then the five most recent trades, newest first', () => {
    const rows = ['01', '05', '03', '07', '02', '06', '04'].map((day, i) =>
      trade(String(100 + i), `T${day}`, 'ACTIVE', `2026-10-${day}T10:00:00Z`));
    const shown = emptyQueryItems([...tickerItems([ticker('NVDA', null)]), ...tradeItems(rows), ...pageItems(), ...PREFERENCE_ITEMS]);
    expect(labels(shown.slice(0, RAIL.length))).toEqual(RAIL);
    expect(labels(shown.slice(RAIL.length))).toEqual(['T07 #103', 'T06 #105', 'T05 #101', 'T04 #106', 'T03 #102']);
    expect(shown).toHaveLength(RAIL.length + RECENT_TRADES);
  });

  it('shows the pages alone before the trades have loaded', () => {
    const shown = emptyQueryItems(pageItems());
    expect(labels(shown)).toEqual(RAIL);
  });
});
