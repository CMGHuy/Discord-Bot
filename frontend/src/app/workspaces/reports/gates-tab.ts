import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  inject,
  viewChild,
} from '@angular/core';

import {
  FLOOR_N_DISPLAY,
  GateCellView,
  LATEST_HEADING,
  OVER_CAP_NOTE,
  R_CAPTION,
  ReportsStore,
} from '../../stores/reports.store';
import { Chip } from '../../ui/chip';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, RowContext } from '../../ui/data-table/data-table.types';
import { Panel } from '../../ui/layout';
import { formatInterval, formatR } from './attribution-tab';

const percent = (value: number | null): string =>
  value === null ? '—' : `${(value * 100).toFixed(0)}%`;

/**
 * Gate counterfactual (v147) — does each gate earn the trades it blocks.
 *
 * One row per verdict cell (gate x population). The verdict column is the
 * verdict of record; the three "Latest" columns are the newest reading and
 * are descriptive only. A cell below v147's floor shows WAITING and an N
 * progress figure, and nothing else: no badge, no interval, no difference.
 *
 * Renders `ReportsStore.gates()` and decides nothing. A verdict here changes
 * no gate; that takes its own pre-registration.
 */
@Component({
  selector: 'sb-gates-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip, DataTable, Panel],
  template: `
    @if (store.gates(); as cells) {
      <sb-panel heading="Verdicts">
        <p class="caption">
          Verdict: the verdict of record. The three "Latest" columns: {{ latestHeading }}.
        </p>
        <sb-data-table
          [rows]="cells"
          [columns]="columns()"
          [visible]="visible"
          [rowKey]="cellKey"
          [expansion]="detail"
          clientPaging="reports-gates"
          [fillPage]="false"
        />
        <p class="footer">
          BH family: the five verdict cells. {{ caption }}
          A verdict here changes no gate; a change goes through its own pre-registration.
        </p>
      </sb-panel>
    }

    <ng-template #verdictCell let-cell>
      @switch (cell.state) {
        @case ('verdict') {
          <span class="verdict">
            <sb-chip [label]="cell.verdict.label" [tone]="cell.verdict.tone" />
            <span class="aside">fixed {{ cell.verdict.date }} · N {{ cell.verdict.n }}</span>
          </span>
        }
        @case ('waiting') {
          <span class="waiting">
            <span class="word">WAITING</span>
            <progress [value]="cell.n" [max]="floor" [attr.aria-label]="'N ' + cell.n + ' of ' + floor"></progress>
            <span class="num">N {{ cell.n }} / {{ floor }}</span>
          </span>
        }
        @default { <span class="aside">{{ cell.note }}</span> }
      }
    </ng-template>

    <ng-template #detail let-cell>
      <div class="detail" [attr.data-cell]="cell.id">
        @if (cell.verdict; as verdict) { <p class="sentence">{{ verdict.sentence }}</p> }
        @for (label of cell.labels; track label) { <span class="label">{{ label }}</span> }
        @if (cell.rows.length) {
          <table class="figures">
            <thead>
              <tr>
                <th>Reason</th><th>Blocked N</th><th>No-plan N</th><th>Fill rate</th>
                <th>Blocked ExpR / WR</th><th>Taken N</th><th>Taken ExpR / WR</th>
                <th>Taken booked ExpR</th>
                <th>Near-miss ExpR (N)</th><th>Rest ExpR (N)</th><th>Dollar risk</th>
              </tr>
            </thead>
            <tbody>
              @for (row of cell.rows; track row.reason) {
                <tr>
                  <td>{{ row.reason }}</td>
                  <td class="num">{{ row.blockedN }}</td>
                  <td class="num">{{ row.noPlanN }}</td>
                  <td class="num">{{ pct(row.fillRate) }}</td>
                  <td class="num">{{ r(row.blockedExpR) }} / {{ pct(row.blockedWinRate) }}</td>
                  <td class="num">{{ row.takenN }}</td>
                  <td class="num">{{ r(row.takenExpR) }} / {{ pct(row.takenWinRate) }}</td>
                  <td class="num">{{ r(row.takenRealisedExpR) }}</td>
                  <td class="num">{{ r(row.nearMissExpR) }} ({{ row.nearMissN ?? '—' }})</td>
                  <td class="num">{{ r(row.restExpR) }} ({{ row.restN ?? '—' }})</td>
                  <td class="num">
                    @if (row.dollarRisk !== null) { {{ dollars(row.dollarRisk) }} } @else { — }
                    @if (row.overCap) { <span class="over-cap">over-cap: {{ overCapNote }}</span> }
                  </td>
                </tr>
              }
            </tbody>
          </table>
          <p class="caption">{{ caption }}</p>
        } @else {
          <p class="aside">No blocked-setup rows for this cell.</p>
        }
      </div>
    </ng-template>
  `,
  styles: `
    :host { display: grid; gap: var(--space-14); }
    .verdict, .waiting { display: inline-flex; align-items: center; gap: var(--space-8); flex-wrap: wrap; }
    .word { font-family: var(--font-mono); color: var(--text-muted); letter-spacing: 0.08em; }
    progress { width: 5rem; height: 6px; }
    .detail { display: grid; gap: var(--space-8); }
    .sentence { margin: 0; }
    .label, .over-cap { display: inline-block; color: var(--warn); font-size: var(--text-micro); }
    .label { margin-right: var(--space-10); }
    .figures { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .figures th { text-align: left; color: var(--text-muted); font-weight: 500; }
    .figures th, .figures td { padding: var(--space-4) var(--space-8); border-bottom: 1px solid var(--border); }
    .aside, .caption, .footer { color: var(--text-faint); font-size: var(--text-micro); }
    .caption, .footer { margin: var(--space-8) 0; }
  `,
})
export class GatesTab {
  protected readonly store = inject(ReportsStore);

  protected readonly latestHeading = LATEST_HEADING;
  protected readonly caption = R_CAPTION;
  protected readonly overCapNote = OVER_CAP_NOTE;
  protected readonly floor = FLOOR_N_DISPLAY;

  private readonly verdictCell = viewChild.required<TemplateRef<RowContext<GateCellView>>>('verdictCell');

  protected readonly visible = ['gate', 'population', 'verdict', 'difference', 'interval', 'q'];
  /** The three Latest columns read from `cell.latest`, which the store nulls
   *  unless a verdict of record exists, so they are blank exactly when they must be. */
  protected readonly columns = computed<ColumnDef<GateCellView>[]>(() => [
    { key: 'gate', header: 'Gate', value: (cell) => cell.gate },
    { key: 'population', header: 'Population', value: (cell) => cell.population },
    { key: 'verdict', header: 'Verdict of record', cell: this.verdictCell() },
    { key: 'difference', header: 'Latest: blocked − taken', numeric: true,
      value: (cell) => (cell.latest ? formatR(cell.latest.difference) : '') },
    { key: 'interval', header: 'Latest: 95% CI', numeric: true,
      value: (cell) => (cell.latest ? formatInterval(cell.latest.ciLow, cell.latest.ciHigh) : '') },
    { key: 'q', header: 'Latest: BH q', numeric: true,
      value: (cell) => (cell.latest?.q === null || cell.latest?.q === undefined ? '' : cell.latest.q.toFixed(2)) },
  ]);

  protected readonly cellKey = (cell: GateCellView): string => cell.id;
  protected readonly r = formatR;
  protected readonly pct = percent;

  protected dollars(value: number): string {
    return `$${value.toFixed(2)}`;
  }
}
