import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TapeRow } from '../../../api/models';
import { Panel } from '../../../ui/layout';
import { num, pct } from '../../../ui/format';

/** The watchlist, as a table rather than a moving strip — the same tape data
 *  the top bar scrolls, sitting still long enough to read. */
@Component({
  selector: 'sb-watchlist-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, RouterLink],
  template: `
    <sb-panel heading="Watchlist">
      <a panel-actions class="all-link" routerLink="/watchlist">View all</a>
      <table>
        <thead>
          <tr><th scope="col">Symbol</th><th scope="col">Price</th><th scope="col">1D</th></tr>
        </thead>
        <tbody>
          @for (row of visible(); track row.symbol) {
            <tr>
              <td><a class="symbol" [routerLink]="['/watchlist', row.symbol]">{{ row.symbol }}</a></td>
              <td class="price">{{ row.price === null ? '—' : fmtNum(row.price) }}</td>
              <td class="change"
                  [class.pos]="(row.change_pct ?? 0) > 0"
                  [class.neg]="(row.change_pct ?? 0) < 0">
                {{ row.change_pct === null ? '—' : fmtPct(row.change_pct) }}
              </td>
            </tr>
          }
        </tbody>
      </table>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    table { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    th {
      text-align: left;
      color: var(--text-faint);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      font-weight: 500;
      padding-bottom: var(--space-4);
    }
    td { padding: var(--space-4) 0; font-variant-numeric: tabular-nums; }
    td.price, td.change, th:not(:first-child) { text-align: right; }
    .symbol { color: var(--accent); font-family: var(--font-mono); text-decoration: none; }
    .symbol:hover { text-decoration: underline; }
    .change.pos { color: var(--pos); }
    .change.neg { color: var(--neg); }
    .all-link { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
  `,
})
export class WatchlistPanel {
  readonly rows = input<readonly TapeRow[]>([]);
  readonly limit = input(6);

  protected readonly visible = computed(() => this.rows().slice(0, this.limit()));
  protected fmtNum = num;
  protected fmtPct = pct;
}
