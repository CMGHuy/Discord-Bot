import { Preferences } from '../api/models';
import { Density } from './data-table/data-table.types';

/**
 * Reading and writing a table's saved layout — spec v18 Decision 4,
 * "Persistence".
 *
 * **Every read is tolerant, and that is the point.** These preferences are
 * written by one version of the app and read by the next: a column gets
 * renamed, a density gets added, someone hand-edits the JSON. A reader that
 * trusted what it found would turn any of those into a broken table, and a
 * broken table for a preference nobody remembers setting is close to
 * impossible to diagnose from the outside.
 *
 * So a stored value is a *hint*, validated against the baseline the caller
 * passes in. The worst case is that the table renders its default, which is
 * exactly what a user who has never touched it sees.
 *
 * Keys are flat and dotted (`tables.trades.compact.columns`) rather than a
 * nested object, so adding a preference is adding a key and never a schema
 * migration of everything already saved.
 */

/** "All" — the UI's word for it, and 0 on the wire between the selector and
 *  the store. Never sent to the API; see `perPageForApi`. */
export const ALL_PER_PAGE = 0;

/** The API's documented ceiling (`MAX_PER_PAGE` in api_v1/__init__.py). The
 *  endpoint clamps to it anyway; asking for exactly it is how "All" is
 *  expressed to a paginated API that has no unbounded mode. */
export const API_MAX_PER_PAGE = 200;

/** The per-page values the UI offers, "All" included. A stored value outside
 *  this set is treated as absent — it would otherwise let a hand-edited
 *  preference ask the server for an unbounded page.
 *
 *  v167: 5/10/20/50/100/All. */
export const PER_PAGE_OPTIONS = [5, 10, 20, 50, 100, ALL_PER_PAGE] as const;

/** Rows per page when nothing is saved: a phone or tablet shows 5 so the
 *  pager stays on screen, a desktop shows 10. */
export const DEFAULT_PER_PAGE_DESKTOP = 10;
export const DEFAULT_PER_PAGE_COMPACT = 5;

/** The default for a device class (`compact` = tablet and phone). */
export function defaultPerPage(compact: boolean): number {
  return compact ? DEFAULT_PER_PAGE_COMPACT : DEFAULT_PER_PAGE_DESKTOP;
}

/**
 * What to actually send as `per_page`.
 *
 * "All" is 0 everywhere inside the client, and 0 is precisely what the
 * collection endpoint rejects — `_positive_int` requires a positive value. So
 * the one place the two meet translates it to the documented cap rather than
 * every call site remembering to.
 */
export function perPageForApi(perPage: number): number {
  return perPage === ALL_PER_PAGE ? API_MAX_PER_PAGE : perPage;
}

function key(tableId: string, density: Density, name: string): string {
  return `tables.${tableId}.${density}.${name}`;
}

export function readTableDensity(prefs: Preferences, tableId: string): Density {
  const stored = prefs[`tables.${tableId}.density`];
  // Compact by default: the table exists to show many rows at once, and a
  // user who wants room can ask for it.
  return stored === 'full' || stored === 'compact' ? stored : 'compact';
}

export function writeTableDensity(
  prefs: Preferences,
  tableId: string,
  density: Density,
): Preferences {
  return { ...prefs, [`tables.${tableId}.density`]: density };
}

/**
 * The visible columns, in order.
 *
 * The stored value is a **filter and sort over the baseline**, never a
 * parallel list. That single property is what makes the ordering reversal
 * safe: an unknown key cannot appear (it is not in the baseline), and a new
 * column cannot vanish (anything the stored order omits is appended rather
 * than dropped). A user who saved a layout in March sees April's new column
 * at the end instead of never discovering it exists.
 */
export function readTableColumns(
  prefs: Preferences,
  tableId: string,
  density: Density,
  baseline: string[],
): string[] {
  const stored = prefs[key(tableId, density, 'columns')];
  if (!Array.isArray(stored)) return [...baseline];

  const known = new Set(baseline);
  const ordered = stored.filter((k): k is string => typeof k === 'string' && known.has(k));
  const seen = new Set(ordered);
  return [...ordered, ...baseline.filter((k) => !seen.has(k))];
}

export function writeTableColumns(
  prefs: Preferences,
  tableId: string,
  density: Density,
  columns: string[],
): Preferences {
  return { ...prefs, [key(tableId, density, 'columns')]: [...columns] };
}

function perPageKey(tableId: string, compact: boolean): string {
  return `tables.${tableId}.${compact ? 'compact' : 'desktop'}.per_page`;
}

/** Saved per table AND per device class, so choosing 50 on a laptop does not
 *  put 50 rows on a phone. `compact` is tablet and phone. */
export function readTablePerPage(
  prefs: Preferences,
  tableId: string,
  compact = false,
  fallback = defaultPerPage(compact),
): number {
  const stored = prefs[perPageKey(tableId, compact)];
  return typeof stored === 'number' && (PER_PAGE_OPTIONS as readonly number[]).includes(stored)
    ? stored
    : fallback;
}

export function writeTablePerPage(
  prefs: Preferences,
  tableId: string,
  compact: boolean,
  perPage: number,
): Preferences {
  return { ...prefs, [perPageKey(tableId, compact)]: perPage };
}

/**
 * Forget a table's saved columns for one density, so its baseline applies
 * again.
 *
 * Deleting the key rather than storing the baseline as a choice: a table
 * whose designed columns change later should pick the new ones up, and a
 * stored copy of March's defaults would quietly prevent that forever.
 */
export function clearTableColumns(
  prefs: Preferences,
  tableId: string,
  density: Density,
): Preferences {
  const next = { ...prefs };
  delete next[key(tableId, density, 'columns')];
  return next;
}
