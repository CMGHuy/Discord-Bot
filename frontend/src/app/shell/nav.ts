import type { IconName } from '../ui/icon';

/** One tab inside a destination (v202 §1): `/trades/calendar`, 'Calendar'. */
export interface NavSection {
  path: string;
  label: string;
}

/** One destination on the rail. `label` is the title of its first section's
 *  route, and each section's `label` its own route's title, except where an
 *  override below records otherwise (nav.spec.ts holds both). The v195
 *  NAV_GROUPS entries use only path, label and icon. */
export interface NavEntry {
  path: string;
  label: string;
  icon: IconName;
  /** The destination's tabs, the first one its default; absent on a single page. */
  sections?: readonly NavSection[];
  /** Drawn at the rail's foot, apart from the work destinations. */
  foot?: boolean;
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

/**
 * The nav model -- v202 §1. Six destinations, with sub-pages as their
 * sections. One model for the rail, the phone tab bar and More sheet, the
 * command palette, the section tabs and the breadcrumb. The /ui gallery is
 * a developer surface, reachable by URL and the palette, never the rail.
 */
export const NAV_ENTRIES: readonly NavEntry[] = [
  { path: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
  { path: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
  {
    path: '/trades', label: 'Trades', icon: 'trades',
    sections: [
      { path: '/trades', label: 'Book' },
      { path: '/trades/calendar', label: 'Calendar' },
      { path: '/trades/cancels', label: 'Cancels' },
    ],
  },
  { path: '/risk', label: 'Risk', icon: 'risk' },
  {
    path: '/insights', label: 'Insights', icon: 'analytics',
    sections: [
      { path: '/insights/analytics', label: 'Analytics' },
      { path: '/insights/research', label: 'Research' },
      { path: '/insights/reports', label: 'Reports' },
    ],
  },
  {
    path: '/system', label: 'System', icon: 'system', foot: true,
    sections: [
      { path: '/system', label: 'Health' },
      { path: '/system/versions', label: 'Versions' },
    ],
  },
];

/** A section label that is not its route's title. The route keeps the page
 *  name the browser tab shows ('Trades', 'System'); the tab names the view
 *  inside the destination ('Book', 'Health'). */
export const SECTION_LABEL_OVERRIDES: Readonly<Record<string, string>> = {
  '/trades': 'Book',
  '/system': 'Health',
};

/** A destination label that is not its first section's title. Insights has
 *  no page of its own: `/insights` redirects to its Analytics section. */
export const DESTINATION_LABEL_OVERRIDES: Readonly<Record<string, string>> = {
  '/insights': 'Insights',
};

/** Every second-segment word that names a section somewhere ('calendar').
 *  The rule itself is per destination (navEntryFor, V202-6b). */
export const SECTION_WORDS: ReadonlySet<string> = new Set(
  NAV_ENTRIES.flatMap((entry) => entry.sections ?? [])
    .map((section) => section.path.split('/')[2])
    .filter((word): word is string => word !== undefined),
);

/** The v195 lookup's aliases: a plan is part of the trade book, and
 *  /universe is the watchlist's old name. Read only by the NAV_GROUPS
 *  navEntryFor below; V202-6b deletes both. */
const GROUP_ALIASES: Readonly<Record<string, string>> = { '/plans': '/trades', '/universe': '/watchlist' };

/** v202: the paths that belong to another destination. A plan is part of
 *  the trade book, /universe and /cockpit are older names, and the six
 *  pre-v202 pages moved under a destination (app.routes.ts redirects all
 *  but /plans). Resolving them here keeps a rail highlight from blinking
 *  during a redirect. */
export const ALIASES: Readonly<Record<string, string>> = {
  '/plans': '/trades',
  '/universe': '/watchlist',
  '/cockpit': '/dashboard',
  '/calendar': '/trades/calendar',
  '/cancels': '/trades/cancels',
  '/analytics': '/insights/analytics',
  '/research': '/insights/research',
  '/reports': '/insights/reports',
  '/versions': '/system/versions',
};

/** '/trades/812?tab=plan#why' -> '/trades'; '' and '/' -> '/'. */
function firstSegment(url: string): string {
  const path = url.split(/[?#]/)[0];
  return `/${path.split('/').find((part) => part !== '') ?? ''}`;
}

/** The group and entry a URL belongs to, by its first path segment; null off
 *  the nav (the /ui gallery, the root, an unknown path). */
export function navEntryFor(url: string): { group: NavGroup; entry: NavEntry } | null {
  const first = firstSegment(url);
  const path = GROUP_ALIASES[first] ?? first;
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
