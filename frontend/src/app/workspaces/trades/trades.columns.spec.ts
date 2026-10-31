import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { TRADE_SORTABLE, TradeRow } from '../../api/models';
import { DataTable } from '../../ui/data-table/data-table';
import { isInline } from '../../ui/priority';
import { compactLines, drawerColumns } from '../../ui/data-table/compact';
import { deriveOpenVisible } from '../dashboard/dashboard.helpers';

import {
  COMPACT_COLUMNS,
  FULL_COLUMNS,
  NEVER_COLLAPSED_COLUMNS,
  PHONE_COMPACT_COLUMNS,
  baselineColumns,
  PINNED_COLUMNS,
  STATUS_CHIPS,
  chipQuery,
  tradeColumns,
} from './trades.columns';

/* NG54 — the status chips.
 *
 * Five of the six returned an empty list before this. They sent the legacy
 * vocabulary (`open`, `win`, `loss`, `cancelled`, `expired`) at a `status`
 * field that carries the plan vocabulary (PENDING, ACTIVE, PARTIAL, CLOSED,
 * CANCELLED, EXPIRED) — so `cancelled` missed on case, and `win` and `loss`
 * missed on the more fundamental problem that they are not statuses at all.
 * Both normalise to CLOSED.
 *
 * The table looked like it was working. An empty result under a selected chip
 * reads as "you have no cancelled trades", which is a perfectly ordinary
 * thing for a trading UI to say. It took opening the page and knowing there
 * WAS a cancelled trade in the fixture set.
 *
 * The server half is tested in tests/admin/test_api_v1_trades.py; these are
 * the parameters this end promises to send.
 */

describe('status chips', () => {
  it('offers Pending, without which the old /plans page has no equivalent', () => {
    const pending = STATUS_CHIPS.find((c) => c.label === 'Pending');
    expect(pending).toBeDefined();
    expect(pending!.value).toBe('PENDING');
    expect(pending!.param).toBe('status');
  });

  it('routes win and loss through outcome, not status', () => {
    for (const label of ['Win', 'Loss']) {
      const chip = STATUS_CHIPS.find((c) => c.label === label)!;
      expect(chip.param).toBe('outcome');
    }
  });

  it('offers Closed -- Win and Loss between them miss a break-even scratch', () => {
    // And there was no one-click "everything that is done", which is where
    // the Dashboard's Closed group links to.
    const closed = STATUS_CHIPS.find((c) => c.label === 'Closed');
    expect(closed).toBeDefined();
    expect(closed!.value).toBe('CLOSED');
    expect(closed!.param).toBe('status');
  });

  it('routes every lifecycle chip through status', () => {
    for (const label of ['Pending', 'Open', 'Closed', 'Cancelled', 'Expired']) {
      const chip = STATUS_CHIPS.find((c) => c.label === label)!;
      expect(chip.param).toBe('status');
    }
  });

  it('sends plan statuses in the case the rows actually carry', () => {
    // The bug was `cancelled` vs CANCELLED. `open` is exempt: it is a
    // server-side alias for ACTIVE-or-PARTIAL, not a status.
    for (const label of ['Pending', 'Closed', 'Cancelled', 'Expired']) {
      const chip = STATUS_CHIPS.find((c) => c.label === label)!;
      expect(chip.value).toBe(chip.value.toUpperCase());
    }
  });
});

describe('chipQuery', () => {
  it('sets the chip parameter and clears the other one', () => {
    expect(chipQuery('win')).toEqual({ status: null, outcome: 'win' });
    expect(chipQuery('CANCELLED')).toEqual({ status: 'CANCELLED', outcome: null });
  });

  it('clears both for "All"', () => {
    expect(chipQuery(null)).toEqual({ status: null, outcome: null });
  });

  it('clears both for a value no chip owns', () => {
    // A hand-edited URL should not leave a filter set that no chip can undo.
    expect(chipQuery('nonsense')).toEqual({ status: null, outcome: null });
  });

  it('never leaves the previous chip behind when switching', () => {
    // The failure this prevents: ?outcome=win&status=CANCELLED, which the
    // server intersects to nothing while a chip still looks selected.
    const afterWin = chipQuery('win');
    const afterCancelled = chipQuery('CANCELLED');
    expect(afterWin.status).toBeNull();
    expect(afterCancelled.outcome).toBeNull();
  });
});

// --- SR16: the two column sets -------------------------------------------

describe('trade column sets', () => {
  it('compact is exactly the spec list', () => {
    expect(COMPACT_COLUMNS).toEqual([
      'num', 'status', 'ticker', 'confidence_level', 'direction', 'badge',
      'now', 'plan', 'pnl_pct', 'r_multiple', 'held', 'opened_at', 'closed_at',
    ]);
  });

  it('full is exactly the spec list', () => {
    expect(FULL_COLUMNS).toEqual([
      'num', 'status', 'ticker', 'confidence_level', 'direction', 'badge',
      'now', 'plan', 'risk_reward', 'r_multiple', 'strategy', 'horizon',
      'pnl_pct', 'realized_pnl_amount', 'held', 'opened_at', 'closed_at',
    ]);
  });

  it('puts the holding period immediately left of Opened, in both densities', () => {
    // How long it has been held and when it started are read together; the
    // pair is one span, not two facts at opposite ends of the row.
    for (const set of [COMPACT_COLUMNS, FULL_COLUMNS]) {
      expect(set.indexOf('held')).toBe(set.indexOf('opened_at') - 1);
    }
  });

  it('actions are pinned, not a member of either set', () => {
    expect(PINNED_COLUMNS).toEqual(['actions']);
    expect(COMPACT_COLUMNS).not.toContain('actions');
    expect(FULL_COLUMNS).not.toContain('actions');
  });

  it('every key in both sets exists in tradeColumns()', () => {
    const known = new Set(tradeColumns().map((c) => c.key));
    for (const k of [...COMPACT_COLUMNS, ...FULL_COLUMNS, ...PINNED_COLUMNS]) {
      expect(known, `missing column def: ${k}`).toContain(k);
    }
  });

  it('the plan column is not sortable', () => {
    // It is three numbers in one cell; there is no single field to sort on,
    // and the server would 400 on `sort=plan`.
    expect(tradeColumns().find((c) => c.key === 'plan')!.sortable).toBeFalsy();
  });

  it('keeps entry, stop and target available to the picker', () => {
    // Folded into `plan` for the default view, not deleted -- anyone who
    // wants them as separate sortable columns can still add them.
    const known = new Set(tradeColumns().map((c) => c.key));
    for (const k of ['entry', 'stop_loss', 'target']) expect(known).toContain(k);
  });

  it('uses the shared Held column for the Dashboard Closed table', () => {
    const known = new Set(tradeColumns().map((c) => c.key));
    expect(known).toContain('held');
    expect(known).not.toContain('hold');
  });

  it('only offers sortable on keys the API will accept', () => {
    // A sortable column the server rejects is a 400 on click, which is worse
    // than not offering the control.
    //
    // Reads TRADE_SORTABLE rather than restating it. It used to hold its own
    // copy of the list, which is the drift this test exists to catch: SR53 made
    // created_at and follow_score sortable on both sides and this failed
    // anyway, against a third list that agreed with neither.
    const sortable = tradeColumns().filter((c) => c.sortable).map((c) => c.key);
    const apiSortable = new Set<string>(TRADE_SORTABLE);
    for (const key of sortable) {
      expect(apiSortable, `not in TRADE_SORTABLE: ${key}`).toContain(
        key === 'held' ? 'held_hours' : key,
      );
    }
  });
  it('renders the shares column, and so its row drawer, with fractional shares (v194 B4)', () => {
    const shares = tradeColumns().find((column) => column.key === 'shares')!;
    expect(shares.value!({ shares: 2.72 } as TradeRow)).toBe('2.72');
    expect(shares.value!({ shares: 3 } as TradeRow)).toBe('3');
    expect(shares.value!({ shares: null } as TradeRow)).toBe('—');
  });

});

/* -- v95 C2 -- column floors, amended 2026-09-28 --------------------------- */

describe('Trades column floors', () => {
  it('declares a floor on every column', () => {
    expect(tradeColumns().filter((c) => c.inlineFrom === undefined)).toEqual([]);
  });

  it('keeps identity and outcome inline on a phone', () => {
    // What a trader opens a phone to check: which trade, and how is it doing.
    const xs = tradeColumns().filter((c) => c.inlineFrom === 'xs').map((c) => c.key);
    expect(xs).toEqual(expect.arrayContaining(['ticker', 'plan', 'pnl_pct']));
  });

  it('demotes the progress bar, which ate 40% of a 390px row', () => {
    expect(isInline(tradeColumns().find((c) => c.key === 'status')!.inlineFrom, 'xs'))
      .toBe(false);
  });

  it('inlines exactly ticker, plan, P&L % and the badge at xs -- the rest is the row accordion', () => {
    // Amended 2026-09-28: the 8-column phone row behind a horizontal scroller
    // is gone; everything else is one tap on the row's expand arrow.
    const xs = tradeColumns().filter((c) => isInline(c.inlineFrom, 'xs')).map((c) => c.key);
    expect(xs.sort()).toEqual(['badge', 'plan', 'pnl_pct', 'ticker']);
  });
});

/* -- v195 correction 8 -- what never collapses on a tablet ------------------- */

describe('never-collapsed trade columns (v195 correction 8)', () => {
  const columns = tradeColumns();
  const floor = (key: string) => columns.find((column) => column.key === key)?.inlineFrom;

  it('names ticker, side, plan, stop, P&L, R, tier and the strategy badge', () => {
    expect([...NEVER_COLLAPSED_COLUMNS]).toEqual(['ticker', 'direction', 'plan', 'stop_loss', 'pnl_pct', 'r_multiple', 'tier', 'badge']);
  });

  it('declares every never-collapsed key in tradeColumns()', () => {
    const known = new Set(columns.map((column) => column.key));
    for (const key of NEVER_COLLAPSED_COLUMNS) expect(known, `missing column def: ${key}`).toContain(key);
  });

  it.each(['sm', 'md', 'lg', 'xl'] as const)('keeps every one inline at %s -- never in the row expansion', (viewport) => {
    for (const key of NEVER_COLLAPSED_COLUMNS) {
      expect(isInline(floor(key), viewport), `${key} collapses at ${viewport}`).toBe(true);
    }
  });

  it('lifts the stop and the tier off the picker-only lg floor', () => {
    expect(floor('stop_loss')).toBe('sm');
    expect(floor('tier')).toBe('sm');
  });

  it('shows the strategy badge by default and on every device, phone card included', () => {
    expect(COMPACT_COLUMNS).toContain('badge');
    expect(FULL_COLUMNS).toContain('badge');
    expect(floor('badge')).toBe('xs');
    expect(columns.find((column) => column.key === 'badge')!.compact).toEqual({ line: 2, order: 3 });
  });

  it('reads the badge as its word, so colour is never the only cue', () => {
    const badge = columns.find((column) => column.key === 'badge')!;
    expect(badge.value!({ badge: 'WEAK' } as TradeRow)).toBe('WEAK');
    expect(badge.value!({ badge: 'VALIDATED' } as TradeRow)).toBe('VALIDATED');
    expect(badge.value!({ badge: null } as TradeRow)).toBe('\u2014');
  });
});

@Component({
  imports: [DataTable],
  template: `<sb-data-table [rows]="rows" [columns]="columns" [visible]="visible" [rowKey]="key" viewportAt="xs" [cardsAt]="true" />`,
})
class PhoneTradesHost {
  readonly rows = [{ id: '1', leg_index: 0, ticker: 'NVDA', badge: 'WEAK' } as unknown as TradeRow];
  readonly columns = tradeColumns().filter((column) => column.key === 'ticker' || column.key === 'badge');
  readonly visible = ['ticker', 'badge'];
  readonly key = (row: TradeRow) => row.id;
}

describe('the strategy badge on a phone (v195 correction 8)', () => {
  it('renders a WEAK row as WEAK on the 390px card, not behind a tap', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(PhoneTradesHost);
    fixture.detectChanges();
    const cell = (fixture.nativeElement as HTMLElement).querySelector('.compact-row [data-col="badge"]');
    expect(cell).not.toBeNull();
    expect(cell!.textContent!.trim()).toBe('WEAK');
  });
});

describe('phone column baseline', () => {
  it('shows the same compact set, with P&L ahead of the 12rem Plan cell', () => {
    expect([...PHONE_COMPACT_COLUMNS].sort()).toEqual([...COMPACT_COLUMNS].sort());
    expect(PHONE_COMPACT_COLUMNS.indexOf('pnl_pct')).toBeLessThan(PHONE_COMPACT_COLUMNS.indexOf('plan'));
    expect(PHONE_COMPACT_COLUMNS.slice(0, 4)).toEqual(['status', 'ticker', 'pnl_pct', 'plan']);
  });

  it('only re-orders compact: full is an explicit request for width', () => {
    expect(baselineColumns('full', true)).toBe(FULL_COLUMNS);
    expect(baselineColumns('compact', false)).toBe(COMPACT_COLUMNS);
    expect(baselineColumns('compact', true)).toBe(PHONE_COMPACT_COLUMNS);
  });
});

describe('Trades compact row -- v179 §3.1', () => {
  const columns = tradeColumns();
  const keys = (list: { key: string }[]) => list.map((column) => column.key);
  const SETS: [string, string[]][] = [
    ['Trades, phone compact', [...PHONE_COMPACT_COLUMNS, ...PINNED_COLUMNS]],
    ['Trades, full', [...FULL_COLUMNS, ...PINNED_COLUMNS]],
    ['Dashboard open positions', deriveOpenVisible([...PHONE_COMPACT_COLUMNS, ...PINNED_COLUMNS])],
  ];

  it('leads line 1 with identity, direction and P&L; line 2 with the plan, status and badge', () => {
    const { line1, line2 } = compactLines(columns, FULL_COLUMNS);
    expect(keys(line1)).toEqual(['ticker', 'direction', 'pnl_pct']);
    expect(keys(line2)).toEqual(['plan', 'status', 'badge']);
  });

  it('declares a slot on those six columns only -- the rest is one tap away', () => {
    expect(keys(columns.filter((column) => column.compact)).sort()).toEqual(['badge', 'direction', 'plan', 'pnl_pct', 'status', 'ticker']);
  });

  it.each(SETS)('%s: P&L (with its amount) and the plan (with its stop) stay on the row', (_, shown) => {
    const { line1, line2 } = compactLines(columns, shown);
    expect(keys([...line1, ...line2])).toEqual(expect.arrayContaining(['pnl_pct', 'plan']));
  });

  it.each(SETS)('%s: the row and the drawer reach every rendered column', (_, shown) => {
    const { line1, line2 } = compactLines(columns, shown);
    const reached = [...keys(line1), ...keys(line2), ...keys(drawerColumns(columns, shown))];
    expect([...reached].sort()).toEqual([...shown].sort());
  });
});
