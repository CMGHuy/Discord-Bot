import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { PageSpec } from './data-table/data-table.types';
import { ALL_PER_PAGE, PER_PAGE_OPTIONS } from './table-prefs';

@Component({
  selector: 'sb-pagination',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (!navOnly() || pageCount() > 1) {
    <div class="bar">
      @if (!navOnly()) {
        <span class="range num">{{ rangeLabel() }}</span>
      }
      @if (showPerPage() && !navOnly()) {
        <label class="per-page"><span class="sb-label">Rows</span><select aria-label="Rows per page" (change)="onPerPage($any($event.target).value)">
          @for (option of perPageOptions; track option) {
            <option [value]="option" [selected]="option === selectedPerPage()">{{ perPageLabel(option) }}</option>
          }
        </select></label>
      }
      @if (pageCount() > 1) {
        <div class="nav" role="group" aria-label="Pagination">
          <button type="button" class="edge" aria-label="First page" [disabled]="pagination().page <= 1" (click)="jump(1)">⏮</button>
          <button type="button" aria-label="Previous page" [disabled]="pagination().page <= 1" (click)="goTo(-1)"><span aria-hidden="true">‹</span><span class="word"> Previous</span></button>
          <label class="of"><span class="word">Page</span><input class="jump num" type="number" inputmode="numeric" aria-label="Page number" min="1" [max]="pageCount()" [value]="pagination().page" (change)="onJump($any($event.target).value)" /><span class="total num">/ {{ pageCount() }}</span></label>
          <button type="button" aria-label="Next page" [disabled]="pagination().page >= pageCount()" (click)="goTo(1)"><span class="word">Next </span><span aria-hidden="true">›</span></button>
          <button type="button" class="edge" aria-label="Last page" [disabled]="pagination().page >= pageCount()" (click)="jump(pageCount())">⏭</button>
        </div>
      }
    </div>
    @if (announce()) { <span class="sr-only" role="status" aria-live="polite">{{ announcement() }}</span> }
    }
  `,
  styles: `
    /* v167. One bar: range, rows-per-page and page controls share a row on a
       wide container and wrap into two on a narrow one. The query is on the
       host's own width (container-type), not the viewport, so a pager inside
       a half-width panel wraps correctly on a desktop too. Padding matches
       the table cells' --space-10 inset so everything shares one left edge. */
    :host { display: block; container: pager / inline-size; }
    .bar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-8) var(--space-10); padding: var(--space-10); font-size: var(--text-table); color: var(--text-secondary); }
    .range { margin-right: auto; }
    .per-page { display: inline-flex; align-items: center; gap: var(--space-6); }
    .per-page select, .jump { height: var(--control-h); background: var(--surface); color: var(--text); border: 1px solid var(--border-strong); border-radius: var(--radius); font: inherit; font-size: var(--text-control); }
    .per-page select { padding: 0 var(--space-4); min-width: 4.5rem; }
    .nav { display: inline-flex; align-items: center; gap: var(--space-6); }
    .jump { width: 3.5rem; padding: 0 var(--space-4); text-align: center; }
    .of { display: inline-flex; align-items: center; gap: var(--space-4); white-space: nowrap; }
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
    button { min-height: var(--control-h); min-width: var(--control-h); padding: 0 var(--space-10); background: transparent; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--text); font: inherit; cursor: pointer; transition: border-color var(--transition); }
    button:disabled { opacity: 0.45; cursor: default; }
    button:not(:disabled):hover { border-color: var(--accent); }
    button:focus-visible, select:focus-visible, .jump:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    /* Narrow container (phone, tablet, or a small panel): range left and
       rows right on the first line; the nav takes the second line full
       width with the page box centred between two large prev/next targets. */
    @container pager (max-width: 639px) {
      .range { margin-right: 0; flex: 1 1 auto; }
      .nav { flex: 1 1 100%; justify-content: space-between; }
      .of { flex: 1 1 auto; justify-content: center; }
      .word { display: none; }
      .of .word { display: inline; }
      button { min-width: 2.75rem; min-height: 2.75rem; font-size: var(--text-body); }
      .nav button:not(.edge) { flex: 1 1 0; max-width: 5rem; }
      .jump, .per-page select { height: 2.75rem; }
    }
  `,
})
export class PaginationComponent {
  readonly pagination = input.required<PageSpec>();
  readonly pageChange = output<number>();
  readonly showPerPage = input(false);
  readonly perPageChange = output<number>();
  readonly announce = input(false);
  readonly navOnly = input(false);
  /** What the user picked, when the pager's own `perPage` is not it -- a
   *  server-paged "All" comes back as the API's 200-row cap. */
  readonly perPageChoice = input<number | null>(null);
  protected readonly selectedPerPage = computed(() => this.perPageChoice() ?? this.pagination().perPage);
  protected readonly perPageOptions = PER_PAGE_OPTIONS;
  protected readonly allPerPage = ALL_PER_PAGE;
  protected onPerPage(value: string): void { this.perPageChange.emit(Number(value)); }
  protected perPageLabel(value: number): string { return value === ALL_PER_PAGE ? 'All' : String(value); }
  protected readonly pageCount = computed(() => { const { total, perPage } = this.pagination(); return perPage <= 0 ? 1 : Math.max(1, Math.ceil(total / perPage)); });
  protected readonly rangeLabel = computed(() => { const { total, page, perPage } = this.pagination(); if (this.pageCount() <= 1) return `${total} ${total === 1 ? 'row' : 'rows'}`; const first = (page - 1) * perPage + 1; const last = Math.min(page * perPage, total); const capped = this.perPageChoice() === ALL_PER_PAGE && total > perPage ? ' (capped)' : ''; return `${first}–${last} of ${total}${capped}`; });
  protected readonly announcement = computed(() => `Page ${this.pagination().page} of ${this.pageCount()}, showing ${this.rangeLabel()}`);
  protected jump(target: number): void { const clamped = Math.min(Math.max(1, Math.trunc(target) || 1), this.pageCount()); if (clamped !== this.pagination().page) this.pageChange.emit(clamped); }
  protected onJump(value: string): void { this.jump(Number(value)); }
  protected goTo(delta: number): void { this.jump(this.pagination().page + delta); }
}
