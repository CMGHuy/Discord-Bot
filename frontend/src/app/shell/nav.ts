import type { IconName } from '../ui/icon';

/** One tab inside a destination (v202 §1): `/trades/calendar`, 'Calendar'. */
export interface NavSection {
  path: string;
  label: string;
}

/** One destination on the rail. `label` is the title of its first section's
 *  route, and each section's `label` its own route's title, except where an
 *  override below records otherwise (nav.spec.ts holds both). */
export interface NavEntry {
  path: string;
  label: string;
  icon: IconName;
  /** The destination's tabs, the first one its default; absent on a single page. */
  sections?: readonly NavSection[];
  /** Drawn at the rail's foot, apart from the work destinations. */
  foot?: boolean;
  /** v207: hidden from viewers; the server refuses its API anyway. */
  adminOnly?: boolean;
}

/**
 * The nav model -- v202 §1. Six destinations, with sub-pages as their
 * sections. One model for the rail, the phone tab bar and More sheet, the
 * command palette, the section tabs and the breadcrumb. The /ui gallery is
 * a developer surface, reachable by URL and the palette, never the rail.
 * Every consumer reads it through `navEntriesFor` (v207), which hides the
 * admin-only entries from a viewer.
 */
export const NAV_ENTRIES: readonly NavEntry[] = [
  { path: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
  { path: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
  {
    path: '/trades', label: 'Trades', icon: 'trades',
    sections: [
      { path: '/trades', label: 'Book' },
      { path: '/trades/calendar', label: 'Calendar' },
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
    path: '/system', label: 'System', icon: 'system', foot: true, adminOnly: true,
    sections: [
      { path: '/system', label: 'Health' },
      { path: '/system/versions', label: 'Versions' },
    ],
  },
];

/** The entries a principal may see: all of them for the admin (the same
 *  array), without the `adminOnly` ones for a viewer (v207). */
export function navEntriesFor(isAdmin: boolean, entries: readonly NavEntry[] = NAV_ENTRIES): readonly NavEntry[] {
  return isAdmin ? entries : entries.filter((entry) => !entry.adminOnly);
}

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
  '/cancels': '/insights/analytics',
  '/analytics': '/insights/analytics',
  '/research': '/insights/research',
  '/reports': '/insights/reports',
  '/versions': '/system/versions',
};

/** '/calendar/2026-10-01?x#y' -> ['trades', 'calendar', '2026-10-01']; '' -> []. */
function segments(url: string): string[] {
  const parts = url.split(/[?#]/)[0].split('/').filter((part) => part !== '');
  if (parts.length === 0) return [];
  const alias = ALIASES[`/${parts[0]}`];
  return alias ? [...alias.split('/').filter((part) => part !== ''), ...parts.slice(1)] : parts;
}

function entryAt(first: string | undefined): NavEntry | undefined {
  return first === undefined ? undefined : NAV_ENTRIES.find((entry) => entry.path === `/${first}`);
}

/** The section a second segment names in this destination, if it names one. */
function namedSection(entry: NavEntry, word: string | undefined): NavSection | undefined {
  if (word === undefined) return undefined;
  return entry.sections?.find((section) => section.path === `${entry.path}/${word}`);
}

/**
 * The destination and section a URL belongs to -- v202 second-segment rule.
 * The second segment is a section exactly when it is one of this
 * destination's section words; anything else there (`/trades/812`) is a
 * detail id and keeps the first section. A single page has no section.
 * Null off the nav (the /ui gallery, the root, an unknown path).
 */
export function navEntryFor(url: string): { entry: NavEntry; section: NavSection | null } | null {
  const [first, second] = segments(url);
  const entry = entryAt(first);
  if (!entry) return null;
  return { entry, section: namedSection(entry, second) ?? entry.sections?.[0] ?? null };
}

/** The destination path a URL belongs to ('/insights'), or null off the nav. */
export function destinationFor(url: string): string | null {
  return navEntryFor(url)?.entry.path ?? null;
}

/** True when the URL's second segment (after ALIASES) names one of its
 *  destination's sections: '/trades/calendar', not '/trades' or '/trades/812'. */
export function isSectionUrl(url: string): boolean {
  const [first, second] = segments(url);
  const entry = entryAt(first);
  return entry !== undefined && namedSection(entry, second) !== undefined;
}

/** The phone tab bar's own label where it differs from the rail's: the
 *  landing page reads as Home on a 64 px tab (v202 §3). */
const PHONE_TAB_LABELS: Readonly<Record<string, string>> = { '/dashboard': 'Home' };

/** The phone bottom bar's four tabs, in order; PhoneTabBar adds More as the
 *  fifth. Three are destinations (paths and icons their own); Calendar is the
 *  one section promoted to a tab, so the P&L view is a single tap away. Risk
 *  lives in the More sheet. */
const PHONE_TAB_ENTRIES: readonly NavEntry[] = [
  ...['/dashboard', '/watchlist'].map((path) => navEntryFor(path)!.entry),
  { path: '/trades/calendar', label: 'Calendar', icon: 'calendar' },
  navEntryFor('/trades')!.entry,
];

export const PHONE_TABS: readonly NavEntry[] = PHONE_TAB_ENTRIES
  .map((entry) => ({ ...entry, label: PHONE_TAB_LABELS[entry.path] ?? entry.label }));

/** The phone tab a URL lights: its section's own tab when the section is one
 *  (Calendar), else its destination's; null off the nav. */
export function phoneTabPathFor(url: string): string | null {
  const found = navEntryFor(url);
  if (!found) return null;
  const sectionTab = PHONE_TABS.find((tab) => tab.path === found.section?.path);
  return sectionTab?.path ?? found.entry.path;
}

/** `Destination / Section` ('Trades / Calendar'), the destination alone on a
 *  single page ('Risk'), plus the detail segment a detail route supplies
 *  ('Trades / Book / NVDA #812'). Empty off the nav. */
export function breadcrumbFor(url: string, detail: string | null): string[] {
  const found = navEntryFor(url);
  if (!found) return [];
  const crumbs = found.section ? [found.entry.label, found.section.label] : [found.entry.label];
  return detail ? [...crumbs, detail] : crumbs;
}

/** A trade or plan's detail segment: 'NVDA #812'. Either half may be missing;
 *  both missing is '' (breadcrumbFor treats it as no detail). */
export function detailCrumb(ticker: string | null, id: string | number | null): string {
  const symbol = ticker?.trim() || null;
  const number = id === null || id === '' ? null : `#${id}`;
  return [symbol, number].filter((part): part is string => part !== null).join(' ');
}
