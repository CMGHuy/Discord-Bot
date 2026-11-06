import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { CancelsStore } from '../../stores/cancels.store';
import { Async, asyncInputs } from '../../ui/async';
import { Button } from '../../ui/button';
import { Panel } from '../../ui/layout';
import { Page } from '../../ui/page';
import { CancelsSummary } from './cancels-summary';
import { CancelsTable } from './cancels-table';

/*
 * Read-only. The screen shows a hypothetical replay and changes no cancel
 * rule. The store is root-provided, so a revisit shows the last figures while
 * the reload runs.
 */
@Component({
  selector: 'sb-cancels',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Page, Async, Button, Panel, CancelsSummary, CancelsTable],
  host: { class: 'register-instrument' },
  styles: `
    /* v195 Phase 4: sb-page owns the page rhythm; the summary and the table
       keep the 14px gap the host used to give them. */
    :host { display: block; min-width: 0; }
    sb-async[page-primary] { display: grid; gap: var(--space-14); }
    .filter-line {
      display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8);
      margin: 0 0 var(--space-8); font-size: var(--text-body);
    }
  `,
  template: `
    <sb-page>
      <!-- v195 Phase 4: the route title is the page's one h1. One primary
           element: the summary's cards filter the table below them, so the
           two stay together. Read-only, so the header carries no action. -->
      <sb-async page-primary [loading]="async().loading" [error]="async().error" [empty]="async().empty"
        [staleAsOf]="async().staleAsOf" emptyReason="measured-zero" emptyTitle="Nothing to replay"
        shape="panel" (retry)="reload()">
        @if (store.data(); as data) {
          <sb-cancels-summary [data]="data" [filter]="store.filter()"
            (card)="store.pickCard($event)" (outcome)="store.pickOutcome($event)" (split)="store.pickSplit($event)" />
          <sb-panel heading="Cancelled plans">
            @if (filterText(); as label) {
              <p class="filter-line" role="status">
                Showing {{ label }} · {{ store.rows().length }} of {{ data.rows.length }} rows
                <button sb-button type="button" variant="ghost" (click)="store.clearFilter()">Clear filter</button>
              </p>
            }
            <sb-cancels-table [rows]="store.rows()" />
          </sb-panel>
        }
      </sb-async>
    </sb-page>
  `,
})
export class Cancels {
  protected readonly store = inject(CancelsStore);

  /** An empty book is a measured answer, shown as figures, never an empty state. */
  protected readonly async = computed(() => asyncInputs(this.store, { isEmpty: () => false }));

  protected readonly filterText = computed(() => {
    const { card, outcome, split } = this.store.filter();
    return [card, outcome, split && `${split.dim} ${split.value}`].filter(Boolean).join(' · ');
  });

  protected reload(): void {
    this.store.load().subscribe({ error: () => undefined });
  }
}
