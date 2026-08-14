import { Observable } from 'rxjs';

import { ApiClient } from '../../api/api-client';
import { TradeRow } from '../../api/models';
import { dateTime } from '../../ui/format';

export type TradeActionKind = 'close' | 'cancel' | 'delete';

/**
 * The three irreversible trade commands, and the sentences that justify them.
 *
 * **This file exists so those sentences cannot drift.** They are needed in two
 * places — the Trades list's row actions and the detail view's Live tab — and
 * two copies of a safety message is how one of them ends up vaguer than the
 * other. Spec v14 is explicit that these dialogs must name what is being
 * destroyed rather than ask "are you sure?": they act on paper-trade history
 * with no undo and no backup, and a generic prompt is answered yes reflexively
 * by anyone who has seen it twice.
 */
export const ACTION_TITLES: Record<TradeActionKind, string> = {
  close: 'Close trade',
  cancel: 'Cancel plan',
  delete: 'Delete trade',
};

export const ACTION_LABELS: Record<TradeActionKind, string> = {
  close: 'Close',
  cancel: 'Cancel plan',
  delete: 'Delete',
};

/** Names the specific trade and what will not come back. */
export function actionConsequence(kind: TradeActionKind, row: TradeRow): string {
  const opened = row.opened_at ? `, opened ${dateTime(row.opened_at)}` : '';

  switch (kind) {
    case 'close':
      return `${row.ticker}${opened} will be closed at the current price and counted as a settled result.`;
    case 'cancel':
      return `The planned ${row.ticker} entry${opened} will be cancelled and never opened.`;
    case 'delete':
      return `${row.ticker}${opened} will be deleted permanently, along with its notes and history. This cannot be undone.`;
  }
}

/** Which commands make sense for a trade in this state. A cancel offered on a
 *  closed trade is a button that can only ever produce an error.
 *
 *  **Matches the plan vocabulary, case-insensitively.** `status` on a row is
 *  always PENDING / ACTIVE / PARTIAL / CLOSED / CANCELLED / EXPIRED — a plan's
 *  own status passed through verbatim, or a legacy trade's mapped into it
 *  (`api_v1/trades.py:49-54, 119, 159`). This function used to switch on
 *  `'open'` / `'planned'` / `'pending'`, none of which any row carries, so
 *  every row fell through to Delete alone and neither Close nor Cancel ever
 *  rendered (SR48).
 *
 *  `open` stays accepted as an alias because the server uses it as one — it
 *  means ACTIVE-or-PARTIAL in a query (`_OPEN_STATUSES`) — but nothing here
 *  depends on it. The case-insensitive compare is the actual guard: it is what
 *  stops the next serialiser change reproducing the bug silently. */
export function availableActions(status: string): TradeActionKind[] {
  switch ((status || '').toUpperCase()) {
    case 'ACTIVE':
    case 'PARTIAL':
    // Not a row status, but the server's own alias for the two above.
    case 'OPEN':
      return ['close', 'delete'];
    case 'PENDING':
      return ['cancel', 'delete'];
    // CLOSED, CANCELLED, EXPIRED — and anything a future build adds. Delete is
    // the floor: a row that can be neither operated nor removed is a dead end.
    default:
      return ['delete'];
  }
}

/**
 * Typed as `Observable<unknown>` on purpose: the three endpoints return
 * different bodies, and a union of Observables has no callable `subscribe`.
 * Nothing here reads the response — success is signalled by the server's
 * `trades` event, which every trade store already refetches on.
 */
export function runTradeAction(
  api: ApiClient,
  kind: TradeActionKind,
  id: string,
): Observable<unknown> {
  switch (kind) {
    case 'close':
      return api.closeTrade(id);
    case 'cancel':
      return api.cancelTrade(id);
    case 'delete':
      return api.deleteTrade(id);
  }
}
