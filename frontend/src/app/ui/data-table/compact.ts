import { ColumnDef } from './data-table.types';

/**
 * The phone compact row -- spec v179 §3.1, §6a.1.
 *
 * `rendered` is the table's `visible` list: what the user's `Columns` choice
 * shows. Everything here works on that, never on `columns` alone, so a
 * column the user hid is absent from the row AND from the drawer, and
 * "reachable" means exactly what the table would show today.
 */
export interface CompactLines<T> {
  line1: ColumnDef<T>[];
  line2: ColumnDef<T>[];
}

/** `rendered` resolved to definitions, in rendered order; unknown keys (a
 *  stale saved preference) are skipped, as `DataTable.renderedColumns` does. */
function resolve<T>(columns: ColumnDef<T>[], rendered: readonly string[]): ColumnDef<T>[] {
  const byKey = new Map(columns.map((column) => [column.key, column]));
  return rendered
    .map((key) => byKey.get(key))
    .filter((column): column is ColumnDef<T> => column !== undefined);
}

/** Rendered columns on one line, by slot order. `Array.sort` is stable, so
 *  equal orders keep rendered order. */
function onLine<T>(shown: ColumnDef<T>[], line: 1 | 2): ColumnDef<T>[] {
  return shown
    .filter((column) => column.compact?.line === line)
    .sort((a, b) => a.compact!.order - b.compact!.order);
}

export function compactLines<T>(columns: ColumnDef<T>[], rendered: readonly string[]): CompactLines<T> {
  const shown = resolve(columns, rendered);
  return { line1: onLine(shown, 1), line2: onLine(shown, 2) };
}

/** Any rendered column has a slot -- the switch into compact mode. */
export function hasCompact<T>(columns: ColumnDef<T>[], rendered: readonly string[]): boolean {
  return resolve(columns, rendered).some((column) => column.compact !== undefined);
}

/** Rendered, not on the compact row, in rendered order: the drawer's fields. */
export function drawerColumns<T>(columns: ColumnDef<T>[], rendered: readonly string[]): ColumnDef<T>[] {
  return resolve(columns, rendered).filter((column) => column.compact === undefined);
}
