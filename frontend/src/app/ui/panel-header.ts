import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

import { Hint } from './hint';

/** Consistent panel provenance: title, population, scope, definition, and table view. */
@Component({
  selector: 'sb-panel-header',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hint],
  template: `
    <header>
      <div class="heading"><h2>{{ title() }}</h2>
        @if (n() !== null) { <span class="n num">N={{ n() }}</span> }
        @if (allTime()) { <span class="all-time">all-time</span> }
        @if (total()) { <span class="total num">{{ total() }}</span> }
        @if (hint()) { <sb-hint [text]="hint()!" [label]="title() + ' definition'" /> }
      </div>
      @if (tableable()) { <button type="button" class="table" [attr.aria-pressed]="tableOpen()" (click)="tableOpen.set(!tableOpen())">Table</button> }
    </header>
  `,
  styles: `header { display:flex; align-items:center; justify-content:space-between; gap:var(--space-8); } .heading { display:flex; align-items:center; flex-wrap:wrap; gap:var(--space-6); } h2 { margin:0; font-size:var(--text-section); color:var(--text); } .n,.all-time { font-size:var(--text-micro); letter-spacing:.06em; text-transform:uppercase; color:var(--text-faint); } .all-time { color:var(--warn); } .total { font-size:var(--text-chip); color:var(--text-secondary); } .table { border:0; padding:0; background:none; color:var(--accent); cursor:pointer; font:inherit; font-size:var(--text-chip); } .table:focus-visible { outline:1px solid var(--accent); outline-offset:2px; }`,
})
export class PanelHeader {
  readonly title = input.required<string>();
  readonly n = input<number | null>(null);
  readonly allTime = input(false);
  readonly hint = input<string | null>(null);
  readonly tableable = input(false);
  readonly total = input<string | null>(null);
  readonly tableOpen = model(false);
}
