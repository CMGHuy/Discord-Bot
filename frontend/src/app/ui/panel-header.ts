import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

import { Hint } from './hint';

/** Consistent panel provenance: title, population, scope, definition, and table view.
 *
 * v179 §3.4: title, N=, total and the hint share the text baseline; the
 * header is one control tall. v186 D1: the title matches sb-panel's.
 * v195 Phase 2: the title (13px, 600, sentence case as given) has its `?`
 * hint right beside it on the left; the quiet meta (N=, all-time, the
 * total), the Table toggle and the `[header-actions]` slot sit together on
 * the right, styled by the global `.sb-meta`. */
@Component({
  selector: 'sb-panel-header',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hint],
  template: `
    <header>
      <div class="heading">
        <h2>{{ title() }}</h2>
        @if (hint()) { <sb-hint [text]="hint()!" [label]="title() + ' definition'" /> }
      </div>
      <div class="meta sb-meta">
        @if (n() !== null) { <span class="n num">N={{ n() }}</span> }
        @if (allTime()) { <span class="all-time">all-time</span> }
        @if (total()) { <span class="total">{{ total() }}</span> }
        @if (tableable()) { <button type="button" class="table sb-hit" [attr.aria-pressed]="tableOpen()" (click)="tableOpen.set(!tableOpen())">Table</button> }
        <ng-content select="[header-actions]" />
      </div>
    </header>
  `,
  styles: `
    header {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      align-content: center;
      justify-content: space-between;
      gap: var(--space-6) var(--space-8);
      min-height: var(--control-h);
    }
    .heading { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--space-6); min-width: 0; }
    h2 { margin: 0; font-family: var(--font-sans); font-weight: 600; font-size: var(--text-table); color: var(--text); letter-spacing: normal; overflow-wrap: anywhere; }
    .meta { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: flex-end; gap: var(--space-6) var(--space-10); margin-left: auto; }
    .meta:empty { display: none; }
    .n,.all-time { font-family: var(--font-num); font-size:var(--text-micro); letter-spacing:.06em; text-transform:uppercase; color: var(--text-muted); }
    .all-time { color:var(--warn); }
    .total { font-family: var(--font-figure); font-weight: var(--figure-weight); letter-spacing: var(--figure-tracking); font-variant-numeric: tabular-nums; font-size: var(--text-chip); color: var(--text-secondary); }
    .table { border:0; padding:0; background:none; color:var(--accent); cursor:pointer; font:inherit; font-size:var(--text-chip); }
    .table:focus-visible { outline:1px solid var(--accent); outline-offset:2px; }
    @media (pointer: coarse), (max-width: 1023px) {
      sb-hint { margin-block: calc((14px - var(--control-h)) / 2); }
    }
  `,
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
