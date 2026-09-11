import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { TapeRow } from '../../../api/models';
import { Panel, TabBar } from '../../../ui/layout';
import { pct } from '../../../ui/format';

type MoverTab = 'gainers' | 'losers';

/**
 * Top gainers and top losers, ranked from the tape already on screen.
 *
 * **Two tabs, not the mockup's three.** `TapeRow` carries no volume, so
 * "Most Active" cannot be answered — v85 D17. A proxy would be a number that
 * looks like activity and is not.
 */
@Component({
  selector: 'sb-market-movers',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, TabBar],
  template: `
    <sb-panel heading="Market movers">
      <sb-tab-bar [tabs]="tabs" [active]="active()" (activeChange)="active.set($any($event))" />
      <ul class="movers">
        @for (row of visible(); track row.symbol) {
          <li>
            <span class="symbol">{{ row.symbol }}</span>
            <span class="change" [class.pos]="row.change_pct! > 0" [class.neg]="row.change_pct! < 0">
              {{ fmtPct(row.change_pct) }}
            </span>
          </li>
        } @empty {
          <li class="empty">No priced symbols yet.</li>
        }
      </ul>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .movers { margin: var(--space-8) 0 0; padding: 0; list-style: none; display: grid; gap: var(--space-6); }
    .movers li { display: flex; justify-content: space-between; font-size: var(--text-table); }
    .symbol { font-family: var(--font-mono); color: var(--text); }
    .change { font-variant-numeric: tabular-nums; }
    .change.pos { color: var(--pos); }
    .change.neg { color: var(--neg); }
    .empty { color: var(--text-faint); font-size: var(--text-chip); }
  `,
})
export class MarketMovers {
  readonly rows = input<readonly TapeRow[]>([]);
  readonly limit = input(5);

  protected readonly active = signal<MoverTab>('gainers');
  protected readonly tabs = [
    { id: 'gainers', label: 'Top gainers' },
    { id: 'losers', label: 'Top losers' },
  ];

  /** Unpriced symbols are dropped, not sorted as 0: a symbol whose quote has
   *  not arrived is not a symbol that did not move.
   *
   *  Also filtered by sign, not just sorted -- with fewer priced rows than
   *  `limit` a sort-only pass would show every row on both tabs, just
   *  reordered, including negative movers under "Top gainers". */
  protected readonly visible = computed(() => {
    const gainers = this.active() === 'gainers';
    const priced = this.rows().filter((row) =>
      gainers ? (row.change_pct ?? 0) > 0 : (row.change_pct ?? 0) < 0);
    const sorted = [...priced].sort((a, b) =>
      gainers
        ? (b.change_pct ?? 0) - (a.change_pct ?? 0)
        : (a.change_pct ?? 0) - (b.change_pct ?? 0),
    );
    return sorted.slice(0, this.limit());
  });

  protected fmtPct = pct;
}
