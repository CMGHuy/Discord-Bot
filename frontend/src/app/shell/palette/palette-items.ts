import { Ticker, TradeRow } from '../../api/models';
import { RowDensity } from '../../ui/density.service';
import { NAV_GROUPS, NavGroup, detailCrumb } from '../nav';

/**
 * The command palette's items and ranking -- v195 §3.1.
 *
 * Pure: no Angular, no store. The palette component feeds it the rows
 * `SearchIndexStore` holds and renders what comes back, so the ranking, the
 * routes and the one hard rule (navigation and preferences only, never an
 * action) are pinned here without a fixture.
 *
 * An item is data, never a callback: it names a route (with optional query
 * params) or a density, nothing else. Nothing in this file can make an item
 * that scans, restarts, halts, deletes or orders, and palette-items.spec.ts
 * fails if a field that could carry one ever appears.
 */

export type PaletteGroup = 'tickers' | 'trades' | 'pages' | 'preferences';

export interface PaletteItem {
  /** Unique across groups: `ticker:NVDA`, `trade:812`, `page:/risk`, ... */
  key: string;
  group: PaletteGroup;
  label: string;
  sub?: string;
  /** A path to navigate to, or null for a preference applied in place. */
  route: string | null;
  queryParams?: Record<string, string>;
  density?: RowDensity;
  /** Epoch ms; trades only, for the empty query's "most recent". */
  recency?: number;
}

/** The tie-break order: the spec's table order (§3.1). */
export const PALETTE_GROUP_ORDER: readonly PaletteGroup[] = ['tickers', 'trades', 'pages', 'preferences'];

/** The kind each result row names on its right edge. */
export const PALETTE_GROUP_LABELS: Record<PaletteGroup, string> = {
  tickers: 'Ticker',
  trades: 'Trade',
  pages: 'Page',
  preferences: 'Preference',
};

/** How many trades the empty query shows. */
export const RECENT_TRADES = 5;

const tab = (route: string, page: string, id: string, label: string): PaletteItem => ({
  key: `tab:${route}?${id}`,
  group: 'pages',
  label,
  sub: page,
  route,
  queryParams: { tab: id },
});

/**
 * Every workspace tab a `?tab=` value opens, minus each workspace's default
 * tab (the page entry already lands there). Ids and labels match the tab
 * bars in analytics.ts, reports.ts, system.ts and watchlist.ts. `providers`
 * is V195-22's; until it lands the System route falls back to Settings.
 */
export const TAB_PAGES: readonly PaletteItem[] = [
  tab('/analytics', 'Analytics', 'attribution', 'Attribution'),
  tab('/analytics', 'Analytics', 'execution', 'Execution'),
  tab('/analytics', 'Analytics', 'edge', 'Edge'),
  tab('/analytics', 'Analytics', 'pipeline', 'Pipeline'),
  tab('/analytics', 'Analytics', 'tuning', 'Tuning'),
  tab('/analytics', 'Analytics', 'partials', 'Partials'),
  tab('/reports', 'Reports', 'gates', 'Gate counterfactual'),
  tab('/system', 'System', 'scan', 'Scan'),
  tab('/system', 'System', 'providers', 'Providers'),
  tab('/system', 'System', 'logs', 'Logs'),
  tab('/watchlist', 'Watchlist', 'earnings', 'Earnings'),
];

/** Density, both ways (spec §1.4). Applied in place; no route. */
export const PREFERENCE_ITEMS: readonly PaletteItem[] = [
  { key: 'pref:density:dense', group: 'preferences', label: 'Density: Dense', sub: '28px rows on desktop', route: null, density: 'dense' },
  { key: 'pref:density:comfortable', group: 'preferences', label: 'Density: Comfortable', sub: '44px rows on desktop', route: null, density: 'comfortable' },
];

/** Every rail entry, in rail order and labelled with its group, then the tabs. */
export function pageItems(groups: readonly NavGroup[] = NAV_GROUPS): PaletteItem[] {
  const entries = groups.flatMap((group) =>
    group.entries.map((entry): PaletteItem => ({
      key: `page:${entry.path}`,
      group: 'pages',
      label: entry.label,
      sub: group.label,
      route: entry.path,
    })),
  );
  return [...entries, ...TAB_PAGES];
}

/** One item per watchlist symbol, opening its detail page. */
export function tickerItems(tickers: readonly Ticker[]): PaletteItem[] {
  return tickers.map((row): PaletteItem => ({
    key: `ticker:${row.symbol}`,
    group: 'tickers',
    label: row.symbol,
    ...(row.company_name ? { sub: row.company_name } : {}),
    route: `/watchlist/${row.symbol}`,
  }));
}

const capitalised = (word: string): string => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();

/** Epoch ms of an ISO time, or 0 when there is none or it does not parse. */
function epochOf(iso: string | null | undefined): number {
  const at = iso ? Date.parse(iso) : Number.NaN;
  return Number.isFinite(at) ? at : 0;
}

/**
 * One item per trade or plan. An unfilled plan (`PENDING`) opens the plan
 * page (`/plans/:id`, v151); anything filled opens the trade record. Labelled
 * `NVDA #812`, like the breadcrumb's detail segment.
 */
export function tradeItems(rows: readonly TradeRow[]): PaletteItem[] {
  return rows.map((row): PaletteItem => {
    const status = (row.status ?? '').toUpperCase();
    const isPlan = status === 'PENDING';
    const state = isPlan ? 'Plan' : capitalised(status);
    return {
      key: `trade:${row.id}`,
      group: 'trades',
      label: detailCrumb(row.ticker, row.id),
      sub: [state, row.strategy].filter(Boolean).join(' · '),
      route: `/${isPlan ? 'plans' : 'trades'}/${row.id}`,
      recency: epochOf(row.created_at ?? row.opened_at),
    };
  });
}

/** The query as matched: trimmed, lower-case, a leading `#` dropped. */
function normalised(query: string): string {
  return query.trim().toLowerCase().replace(/^#/, '');
}

/** Ticker symbols and trade ids: the "exact prefix" tier. */
function codesOf(item: PaletteItem): string[] {
  if (item.group === 'tickers') return [item.label];
  if (item.group === 'trades') return [item.label.split(' ')[0], item.key.slice('trade:'.length)];
  return [];
}

/** The "name" a prefix is matched on: a company name, a page or preference label. */
function nameOf(item: PaletteItem): string {
  if (item.group === 'tickers') return item.sub ?? '';
  if (item.group === 'trades') return '';
  return item.label;
}

/** 0 code prefix, 1 name prefix, 2 substring, null no match. */
function tierOf(query: string, item: PaletteItem): number | null {
  if (codesOf(item).some((code) => code.toLowerCase().replace(/^#/, '').startsWith(query))) return 0;
  if (nameOf(item).toLowerCase().startsWith(query)) return 1;
  return `${item.label} ${item.sub ?? ''}`.toLowerCase().includes(query) ? 2 : null;
}

/**
 * Rank by tier, then group order, then the order the items came in. Returns
 * a new list; an empty query matches nothing (the caller shows
 * `emptyQueryItems` instead).
 */
export function rankPaletteItems(query: string, items: readonly PaletteItem[]): PaletteItem[] {
  const q = normalised(query);
  if (!q) return [];
  const groupRank = (item: PaletteItem) => PALETTE_GROUP_ORDER.indexOf(item.group);
  return items
    .map((item, index) => ({ item, index, tier: tierOf(q, item) }))
    .filter((hit): hit is { item: PaletteItem; index: number; tier: number } => hit.tier !== null)
    .sort((a, b) => a.tier - b.tier || groupRank(a.item) - groupRank(b.item) || a.index - b.index)
    .map((hit) => hit.item);
}

/** The empty query: the rail pages (no tabs), then the five newest trades. */
export function emptyQueryItems(items: readonly PaletteItem[]): PaletteItem[] {
  const pages = items.filter((item) => item.group === 'pages' && !item.queryParams);
  const recent = items
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.group === 'trades')
    .sort((a, b) => (b.item.recency ?? 0) - (a.item.recency ?? 0) || a.index - b.index)
    .slice(0, RECENT_TRADES)
    .map(({ item }) => item);
  return [...pages, ...recent];
}
