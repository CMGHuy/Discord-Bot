import { describe, expect, it } from 'vitest';

import { ACTION_LABELS, ACTION_TITLES, availableActions } from './trade-actions';

/* SR48 — the row actions that never rendered.
 *
 * `availableActions()` switched on 'open' / 'planned' / 'pending'. The
 * collection endpoint never emits any of the three: `_row_from_plan` passes
 * the plan's own status through verbatim, and `_row_from_trade` maps legacy
 * statuses through `_LEGACY_STATUS` into ACTIVE / CLOSED
 * (swingbot/admin/api_v1/trades.py:49-54, 119, 159). Every row therefore fell
 * to the default branch and offered Delete alone.
 *
 * Like NG54 before it, this looked like working software: a row with only a
 * Delete button reads as "this trade cannot be closed from here", which is a
 * perfectly ordinary thing for a paper-trading UI to say. It survived to the
 * Phase 3 gate and was found by the parity audit, not by using the page.
 *
 * These cases are written against the UPPERCASE vocabulary on purpose. The
 * same suite written against the lowercase strings passes today and proves
 * nothing.
 */

describe('availableActions', () => {
  it('offers Close on the two live statuses', () => {
    // ACTIVE and PARTIAL are both open positions -- PARTIAL is "TP1 hit, the
    // runner is still on". Closing is exactly as meaningful for one as the
    // other, and PARTIAL is the case most likely to be missed.
    for (const status of ['ACTIVE', 'PARTIAL']) {
      expect(availableActions(status)).toContain('close');
    }
  });

  it('offers Cancel on a plan that has not filled', () => {
    expect(availableActions('PENDING')).toContain('cancel');
  });

  it('does not offer Cancel on a position that has already filled', () => {
    // A cancel here can only ever produce an error: there is nothing left to
    // call off once the entry is in.
    for (const status of ['ACTIVE', 'PARTIAL']) {
      expect(availableActions(status)).not.toContain('cancel');
    }
  });

  it('does not offer Close on a plan that never opened', () => {
    expect(availableActions('PENDING')).not.toContain('close');
  });

  it('offers Delete alone on every terminal status', () => {
    for (const status of ['CLOSED', 'CANCELLED', 'EXPIRED']) {
      expect(availableActions(status)).toEqual(['delete']);
    }
  });

  it('still understands the open alias', () => {
    // `open` is the server's query alias for ACTIVE-or-PARTIAL
    // (_OPEN_STATUSES, trades.py:75). No ROW ever carries it, so nothing may
    // depend on it -- but the Dashboard queries with it and a future endpoint
    // could echo it back, and silently dropping Close in that case would
    // reintroduce this very bug.
    expect(availableActions('open')).toContain('close');
  });

  it('never leaves a row with no action at all', () => {
    // A row you can neither operate nor remove is a dead end. Delete is the
    // floor, including for a status this build has never heard of.
    for (const status of ['ACTIVE', 'PARTIAL', 'PENDING', 'CLOSED', 'CANCELLED',
                          'EXPIRED', 'SOMETHING_NEW', '']) {
      expect(availableActions(status).length).toBeGreaterThan(0);
      expect(availableActions(status)).toContain('delete');
    }
  });

  it('tolerates the vocabulary arriving in the wrong case', () => {
    // The defect was a case mismatch. Matching case-insensitively is what
    // stops the next serialiser change reproducing it.
    expect(availableActions('active')).toContain('close');
    expect(availableActions('pending')).toContain('cancel');
  });

  it('has a label and a title for every action it can return', () => {
    const kinds = new Set(
      ['ACTIVE', 'PARTIAL', 'PENDING', 'CLOSED'].flatMap(availableActions),
    );
    for (const kind of kinds) {
      expect(ACTION_LABELS[kind]).toBeTruthy();
      expect(ACTION_TITLES[kind]).toBeTruthy();
    }
  });
});
