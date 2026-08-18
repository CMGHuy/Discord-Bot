import { describe, expect, it } from 'vitest';

import { TRADE_SORTABLE } from '../../api/models';

import {
  COMPACT_COLUMNS,
  FULL_COLUMNS,
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

  it('routes every lifecycle chip through status', () => {
    for (const label of ['Pending', 'Open', 'Cancelled', 'Expired']) {
      const chip = STATUS_CHIPS.find((c) => c.label === label)!;
      expect(chip.param).toBe('status');
    }
  });

  it('sends plan statuses in the case the rows actually carry', () => {
    // The bug was `cancelled` vs CANCELLED. `open` is exempt: it is a
    // server-side alias for ACTIVE-or-PARTIAL, not a status.
    for (const label of ['Pending', 'Cancelled', 'Expired']) {
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
      'num', 'status', 'ticker', 'confidence_level', 'direction',
      'now', 'plan', 'pnl_pct', 'r_multiple', 'opened_at', 'closed_at',
    ]);
  });

  it('full is exactly the spec list', () => {
    expect(FULL_COLUMNS).toEqual([
      'num', 'status', 'ticker', 'confidence_level', 'direction',
      'now', 'plan', 'risk_reward', 'r_multiple', 'strategy', 'horizon',
      'pnl_pct', 'held', 'realized_pnl_amount', 'opened_at', 'closed_at',
    ]);
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

  it('offers "hold" for the Dashboard Closed table without adding it to either picker set', () => {
    // Not in COMPACT_COLUMNS/FULL_COLUMNS or the Trades picker -- the
    // Dashboard's Closed group opts into it explicitly via `deriveClosedVisible`
    // (dashboard.helpers.ts), inserted ahead of 'opened_at'.
    const known = new Set(tradeColumns().map((c) => c.key));
    expect(known).toContain('hold');
    expect(COMPACT_COLUMNS).not.toContain('hold');
    expect(FULL_COLUMNS).not.toContain('hold');
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
});
