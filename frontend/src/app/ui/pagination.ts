import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { PageSpec } from './data-table/data-table.types';
import { ALL_PER_PAGE, PER_PAGE_OPTIONS } from './table-prefs';

@Component({
  selector: 'sb-pagination',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (showPerPage()) {
      <div class="per-page">
        <label><span class="label">Rows</span><select (change)="onPerPage($any($event.target).value)">
          @for (option of perPageOptions; track option) {
            <option [value]="option" [selected]="option === pagination().perPage">{{ perPageLabel(option) }}</option>
          }
        </select></label>
      </div>
    }
    <div class="pager">
      <span class="range num">{{ rangeLabel() }}</span>
      @if (pageCount() > 1) {
        <button type="button" aria-label="First page" [disabled]="pagination().page <= 1" (click)="jump(1)">⏮</button>
        <button type="button" aria-label="Previous page" [disabled]="pagination().page <= 1" (click)="goTo(-1)">Previous</button>
        <label class="of"><span class="sr-only">Page</span><input class="jump num" type="number" inputmode="numeric" min="1" [max]="pageCount()" [value]="pagination().page" (change)="onJump($any($event.target).value)" /><span aria-hidden="true">/ {{ pageCount() }}</span></label>
        <button type="button" aria-label="Next page" [disabled]="pagination().page >= pageCount()" (click)="goTo(1)">Next</button>
        <button type="button" aria-label="Last page" [disabled]="pagination().page >= pageCount()" (click)="jump(pageCount())">⏭</button>
      }
    </div>
    @if (announce()) { <span class="sr-only" role="status" aria-live="polite">{{ announcement() }}</span> }
  `,
  styles: `
    .per-page { display: flex; align-items: center; gap: var(--space-6); }
    .per-page .label { font-size: var(--text-chip); color: var(--text-secondary); }
    .per-page select, .jump { background: var(--surface-raised); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius); font: inherit; }
    .per-page select { font-size: var(--text-chip); padding: 2px var(--space-4); }
    .pager { display: flex; align-items: center; gap: var(--space-10); padding: var(--space-10); font-size: var(--text-table); color: var(--text-secondary); }
    .range { margin-right: auto; }
    .jump { width: 3.5rem; padding: 2px var(--space-4); text-align: right; }
    .of { display: inline-flex; align-items: center; gap: var(--space-4); }
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
    button { padding: var(--space-4) var(--space-10); background: var(--surface-raised); border: 1px solid var(--border); border-radius: var(--radius); color: var(--text); font: inherit; cursor: pointer; transition: border-color var(--transition); }
    button:disabled { color: var(--text-faint); cursor: default; }
    button:not(:disabled):hover { border-color: var(--border-strong); }
    button:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
  `,
})
export class PaginationComponent {
  readonly pagination = input.required<PageSpec>();
  readonly pageChange = output<number>();
  readonly showPerPage = input(false);
  readonly perPageChange = output<number>();
  readonly announce = input(false);
  protected readonly perPageOptions = PER_PAGE_OPTIONS;
  protected readonly allPerPage = ALL_PER_PAGE;
  protected onPerPage(value: string): void { this.perPageChange.emit(Number(value)); }
  protected perPageLabel(value: number): string { return value === ALL_PER_PAGE ? 'All' : String(value); }
  protected readonly pageCount = computed(() => { const { total, perPage } = this.pagination(); return perPage <= 0 ? 1 : Math.max(1, Math.ceil(total / perPage)); });
  protected readonly rangeLabel = computed(() => { const { total, page, perPage } = this.pagination(); if (this.pageCount() <= 1) return `${total} ${total === 1 ? 'row' : 'rows'}`; const first = (page - 1) * perPage + 1; const last = Math.min(page * perPage, total); return `${first}–${last} of ${total}`; });
  protected readonly announcement = computed(() => `Page ${this.pagination().page} of ${this.pageCount()}, showing ${this.rangeLabel()}`);
  protected jump(target: number): void { const clamped = Math.min(Math.max(1, Math.trunc(target) || 1), this.pageCount()); if (clamped !== this.pagination().page) this.pageChange.emit(clamped); }
  protected onJump(value: string): void { this.jump(Number(value)); }
  protected goTo(delta: number): void { this.jump(this.pagination().page + delta); }
}