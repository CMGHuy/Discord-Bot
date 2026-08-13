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

const DEFAULT_PER_PAGE = 25;

/** The per-page values the UI offers. A stored value outside this set is
 *  treated as absent — it would otherwise let a hand-edited preference ask
 *  the server for an unbounded page. */
export const PER_PAGE_OPTIONS = [10, 25, 50, 100] as const;

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

export function readTablePerPage(prefs: Preferences, tableId: string): number {
  const stored = prefs[`tables.${tableId}.per_page`];
  return typeof stored === 'number' && (PER_PAGE_OPTIONS as readonly number[]).includes(stored)
    ? stored
    : DEFAULT_PER_PAGE;
}

export function writeTablePerPage(
  prefs: Preferences,
  tableId: string,
  perPage: number,
): Preferences {
  return { ...prefs, [`tables.${tableId}.per_page`]: perPage };
}
