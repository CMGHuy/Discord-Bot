import { describe, expect, it } from 'vitest';

import { compactLines, drawerColumns, hasCompact } from './compact';
import { ColumnDef } from './data-table.types';

/* v179 §3.1 / §6a.1 -- which rendered column goes on which compact line,
 * and what is left for the row drawer. Pure, so the per-table
 * reachability tests (V179-11..13) can lean on it without a TestBed. */

interface Row { id: string }

const COLUMNS: ColumnDef<Row>[] = [
  { key: 'ticker', header: 'Ticker', compact: { line: 1, order: 1 } },
  { key: 'pnl', header: 'P&L', compact: { line: 1, order: 2 } },
  { key: 'plan', header: 'Plan', compact: { line: 2, order: 1 } },
  { key: 'held', header: 'Held' },
  { key: 'status', header: 'Status', compact: { line: 2, order: 0 } },
  { key: 'actions', header: '' },
];
const keys = (columns: ColumnDef<Row>[]) => columns.map((column) => column.key);

describe('compactLines', () => {
  it('splits the rendered compact columns by line, ordered by slot not by visible order', () => {
    const lines = compactLines(COLUMNS, ['held', 'pnl', 'plan', 'ticker', 'status', 'actions']);
    expect(keys(lines.line1)).toEqual(['ticker', 'pnl']);
    expect(keys(lines.line2)).toEqual(['status', 'plan']);
  });

  it('leaves out a compact column the user hid', () => {
    const lines = compactLines(COLUMNS, ['ticker', 'plan']);
    expect(keys(lines.line1)).toEqual(['ticker']);
    expect(keys(lines.line2)).toEqual(['plan']);
  });

  it('skips a key from a stale saved preference', () => {
    expect(keys(compactLines(COLUMNS, ['ticker', 'gone']).line1)).toEqual(['ticker']);
  });
});

describe('hasCompact', () => {
  it('is true when one rendered column declares a slot', () => {
    expect(hasCompact(COLUMNS, ['held', 'pnl'])).toBe(true);
  });

  it('is false when no column declares one', () => {
    expect(hasCompact([{ key: 'held', header: 'Held' }], ['held'])).toBe(false);
  });

  it('is false when only hidden columns declare one -- the scroller comes back', () => {
    expect(hasCompact(COLUMNS, ['held', 'actions'])).toBe(false);
  });
});

describe('drawerColumns', () => {
  it('is every rendered column not on the compact row, in rendered order', () => {
    expect(keys(drawerColumns(COLUMNS, ['actions', 'ticker', 'held', 'pnl']))).toEqual(['actions', 'held']);
  });

  it('never lists a column the user hid', () => {
    expect(keys(drawerColumns(COLUMNS, ['ticker']))).toEqual([]);
  });

  it('together with the compact row reaches every rendered column exactly once', () => {
    const rendered = ['held', 'pnl', 'plan', 'ticker', 'status', 'actions'];
    const { line1, line2 } = compactLines(COLUMNS, rendered);
    const reached = [...keys(line1), ...keys(line2), ...keys(drawerColumns(COLUMNS, rendered))];
    expect([...reached].sort()).toEqual([...rendered].sort());
  });
});
