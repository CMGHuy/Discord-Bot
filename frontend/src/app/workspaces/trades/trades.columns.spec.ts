import { describe, expect, it } from 'vitest';

import { STATUS_CHIPS, chipQuery } from './trades.columns';

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
