import type { IconName } from '../ui/icon';

/** One page on the rail. `label` is the route's own title (nav.spec.ts holds
 *  them equal), so the rail, the breadcrumb and the browser tab agree. */
export interface NavEntry {
  path: string;
  label: string;
  icon: IconName;
}

export interface NavGroup {
  id: string;
  label: string;
  entries: readonly NavEntry[];
}

/**
 * The nav model -- v195 §5.1. Four groups, split by question:
 *   Monitor   what is happening right now
 *   Review    the trade book and its history
 *   Insights  what the measurements say (split out of Review, which had six)
 *   System    what the bot itself is doing
 *
 * One model for the rail, the phone tab bar and More sheet, the command
 * palette and the breadcrumb. The rail shows the groups as dividers; the
 * breadcrumb shows their names. The /ui gallery is a developer surface,
 * reachable by URL and the palette, never the rail.
 */
export const NAV_GROUPS: readonly NavGroup[] = [
  {
    id: 'nav-monitor',
    label: 'Monitor',
    entries: [
      { path: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
      { path: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
      { path: '/risk', label: 'Risk', icon: 'risk' },
    ],
  },
  {
    id: 'nav-review',
    label: 'Review',
    entries: [
      { path: '/trades', label: 'Trades', icon: 'trades' },
      { path: '/calendar', label: 'Calendar', icon: 'calendar' },
      { path: '/cancels', label: 'Cancels', icon: 'cancelled' },
    ],
  },
  {
    id: 'nav-insights',
    label: 'Insights',
    entries: [
      { path: '/analytics', label: 'Analytics', icon: 'analytics' },
      { path: '/research', label: 'Research', icon: 'research' },
      { path: '/reports', label: 'Reports', icon: 'reports' },
    ],
  },
  {
    id: 'nav-system',
    label: 'System',
    entries: [
      { path: '/system', label: 'System', icon: 'system' },
      { path: '/versions', label: 'Versions', icon: 'versions' },
    ],
  },
];

/** Paths that belong to another entry: a plan is part of the trade book, and
 *  /universe is the watchlist's old name (app.routes.ts redirects it). */
const ALIASES: Readonly<Record<string, string>> = { '/plans': '/trades', '/universe': '/watchlist' };

/** '/trades/812?tab=plan#why' -> '/trades'; '' and '/' -> '/'. */
function firstSegment(url: string): string {
  const path = url.split(/[?#]/)[0];
  return `/${path.split('/').find((part) => part !== '') ?? ''}`;
}

/** The group and entry a URL belongs to, by its first path segment; null off
 *  the nav (the /ui gallery, the root, an unknown path). */
export function navEntryFor(url: string): { group: NavGroup; entry: NavEntry } | null {
  const first = firstSegment(url);
  const path = ALIASES[first] ?? first;
  for (const group of NAV_GROUPS) {
    const entry = group.entries.find((candidate) => candidate.path === path);
    if (entry) return { group, entry };
  }
  return null;
}

/** The phone bottom bar's four page tabs (Phase 3), in order; PhoneTabBar
 *  adds More as the fifth. */
export const PHONE_TABS: readonly NavEntry[] = ['/dashboard', '/watchlist', '/trades', '/risk']
  .map((path) => navEntryFor(path)!.entry);

/** `Group / Page`, plus the detail segment a detail route supplies
 *  ('Review / Trades / NVDA #812'). Empty off the nav. */
export function breadcrumbFor(url: string, detail: string | null): string[] {
  const found = navEntryFor(url);
  if (!found) return [];
  const crumbs = [found.group.label, found.entry.label];
  return detail ? [...crumbs, detail] : crumbs;
}

/** A trade or plan's detail segment: 'NVDA #812'. Either half may be missing;
 *  both missing is '' (breadcrumbFor treats it as no detail). */
export function detailCrumb(ticker: string | null, id: string | number | null): string {
  const symbol = ticker?.trim() || null;
  const number = id === null || id === '' ? null : `#${id}`;
  return [symbol, number].filter((part): part is string => part !== null).join(' ');
}
