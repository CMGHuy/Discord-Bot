import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { CancelPlanRow } from '../../api/models';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, EmptyState } from '../../ui/data-table/data-table.types';
import { rText, verdictLabel } from './cancels.helpers';

type ReasonText = (row: CancelPlanRow) => string;

/** How a row's reason reads; a lookup on `row.reason`, not an if chain. */
const REASON_TEXT: Record<string, ReasonText> = {
  risk_cap: (row) => (row.entry_model === 'cancel_fill'
    ? `risk_cap · crossing (${row.entry_source ?? 'estimated'})`
    : 'risk_cap · trigger'),
  other: (row) => `other (${row.raw_reason ?? 'unknown'})`,
};

function reasonText(row: CancelPlanRow): string {
  return (REASON_TEXT[row.reason] ?? ((r: CancelPlanRow) => r.reason))(row);
}

/**
 * One row per replayed cancel (a `risk_cap` plan has two: trigger and
 * crossing). Rows arrive in the server's order, newest cancel first, and the
 * table never sorts them. Read-only.
 */
@Component({
  selector: 'sb-cancels-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DataTable],
  template: `
    <sb-data-table [rows]="rows()" [columns]="columns()" [visible]="visible" [rowKey]="rowKey"
      clientPaging="cancels-plans" [fillPage]="false" [emptyState]="empty" />
  `,
})
export class CancelsTable {
  readonly rows = input.required<CancelPlanRow[]>();

  protected readonly rowKey = (row: CancelPlanRow): string => `${row.plan_id}:${row.entry_model}`;
  protected readonly empty: EmptyState = {
    title: 'No cancelled plans match this filter',
    hint: 'Clear the filter, or wait for the bot to cancel a plan.',
  };
  protected readonly visible = [
    'ticker', 'strategy', 'badge', 'horizon', 'reason', 'cancel_date', 'verdict', 'r', 'cap_size',
  ];

  protected readonly columns = computed<ColumnDef<CancelPlanRow>[]>(() => [
    { key: 'ticker', header: 'Ticker', value: (r) => r.ticker, compact: { line: 1, order: 1 } },
    { key: 'strategy', header: 'Strategy', value: (r) => r.strategy },
    { key: 'badge', header: 'Badge tier', value: (r) => r.badge },
    { key: 'horizon', header: 'Horizon', value: (r) => r.horizon_key },
    { key: 'reason', header: 'Reason', value: reasonText },
    { key: 'cancel_date', header: 'Cancelled', value: (r) => r.cancel_date, compact: { line: 2, order: 1 } },
    { key: 'verdict', header: 'Verdict', value: verdictLabel, compact: { line: 1, order: 2 } },
    {
      key: 'r', header: 'R', numeric: true, compact: { line: 2, order: 2 },
      value: (r) => (r.r === null ? null : rText(r.r)),
    },
    {
      key: 'cap_size', header: 'Cap-implied size', numeric: true,
      value: (r) => (r.cap_size_pct === null ? null : `${r.cap_size_pct.toFixed(1)}%`),
    },
  ]);
}
