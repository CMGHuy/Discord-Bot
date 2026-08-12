import {
  Component,
  TemplateRef,
  computed,
  provideZonelessChangeDetection,
  signal,
  viewChild,
} from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { DataTable } from './data-table';
import {
  ColumnDef,
  EmptyState,
  PageSpec,
  RowContext,
  SortSpec,
} from './data-table.types';

/* NG37 — the load-bearing table.
 *
 * These tests are organised around the five properties spec v14 Decision 1
 * says the contract exists to enforce, because those are the things that cost
 * four workspace rewrites if they regress. Cosmetics are deliberately not
 * asserted.
 */

interface Row {
  id: string;
  ticker: string;
  pnl: number | null;
}

const ROWS: Row[] = [
  { id: 'a', ticker: 'AAPL', pnl: 4.2 },
  { id: 'b', ticker: 'MSFT', pnl: -1.5 },
  { id: 'c', ticker: 'NVDA', pnl: null },
];

@Component({
  imports: [DataTable],
  template: `
    <ng-template #expansion let-row>
      <div class="expansion-body">{{ row.ticker }} detail</div>
    </ng-template>
    <ng-template #actionCell>
      <button type="button" class="action">Close</button>
    </ng-template>

    <sb-data-table
      [rows]="rows()"
      [columns]="columns()"
      [visible]="visible()"
      [rowKey]="rowKey"
      [sort]="sort()"
      [pagination]="pagination()"
      [loading]="loading()"
      [expansion]="withExpansion() ? expansionTemplate() : null"
      [emptyState]="emptyState()"
      (sortChange)="lastSort = $event"
      (pageChange)="pages.push($event)"
      (rowActivate)="activated.push($event)"
    />
  `,
})
class Host {
  readonly rows = signal<Row[]>(ROWS);
  readonly visible = signal<string[]>(['ticker', 'pnl']);
  readonly sort = signal<SortSpec | null>(null);
  readonly pagination = signal<PageSpec | null>(null);
  readonly loading = signal(false);
  readonly emptyState = signal<EmptyState | null>(null);
  readonly withExpansion = signal(false);

  readonly expansionTemplate =
    viewChild.required<TemplateRef<RowContext<Row>>>('expansion');
  private readonly actionCell =
    viewChild.required<TemplateRef<RowContext<Row>>>('actionCell');

  readonly rowKey = (row: Row) => row.id;

  readonly columns = computed<ColumnDef<Row>[]>(() => [
    { key: 'ticker', header: 'Ticker', value: (row) => row.ticker, sortable: true },
    { key: 'pnl', header: 'P&L %', value: (row) => row.pnl, numeric: true, sortable: true },
    { key: 'held', header: 'Held', value: () => '3d' },
    { key: 'actions', header: '', cell: this.actionCell() },
  ]);

  lastSort: SortSpec | null = null;
  readonly pages: number[] = [];
  readonly activated: Row[] = [];
}

describe('DataTable', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = (): HTMLElement => fixture.nativeElement;
  const headers = () => [...el().querySelectorAll('thead th')].map((h) => h.textContent!.trim());
  const bodyRows = () => [...el().querySelectorAll('tbody tr.row')];
  const cells = (row: Element) => [...row.querySelectorAll('td')].map((c) => c.textContent!.trim());

  /* -- property 2: visibility is a set, order comes from `columns` -------- */

  it('renders only the visible columns', () => {
    expect(headers()).toEqual(['Ticker', 'P&L %']);
  });

  it('ignores the order of `visible` and renders in `columns` order', () => {
    // The whole point of the contract: there is no way to express an order,
    // so drag-to-reorder cannot come back through a call site.
    host.visible.set(['pnl', 'ticker']);
    fixture.detectChanges();

    expect(headers()).toEqual(['Ticker', 'P&L %']);
  });

  it('ignores a visible key that no column declares', () => {
    host.visible.set(['ticker', 'nonsense']);
    fixture.detectChanges();

    expect(headers()).toEqual(['Ticker']);
  });

  /* -- property 1: server-side everything -------------------------------- */

  it('renders every row it is given, even when a page is smaller', () => {
    // The table must not slice. If it did, a workspace could paginate twice
    // and silently drop rows the server already sliced for it.
    host.pagination.set({ total: 90, page: 1, perPage: 2 });
    fixture.detectChanges();

    expect(bodyRows()).toHaveLength(3);
  });

  it('emits a sort instead of reordering the rows', () => {
    const before = bodyRows().map((row) => cells(row)[0]);
    (el().querySelector('thead th .sort') as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(host.lastSort).toEqual({ key: 'ticker', direction: 'asc' });
    expect(bodyRows().map((row) => cells(row)[0])).toEqual(before);
  });

  it('starts a newly clicked column ascending and toggles on repeat', () => {
    const tickerHeader = () => el().querySelector('thead th .sort') as HTMLButtonElement;

    tickerHeader().click();
    expect(host.lastSort).toEqual({ key: 'ticker', direction: 'asc' });

    host.sort.set({ key: 'ticker', direction: 'asc' });
    fixture.detectChanges();
    tickerHeader().click();
    expect(host.lastSort).toEqual({ key: 'ticker', direction: 'desc' });

    host.sort.set({ key: 'ticker', direction: 'desc' });
    fixture.detectChanges();
    tickerHeader().click();
    expect(host.lastSort).toEqual({ key: 'ticker', direction: 'asc' });
  });

  it('switching columns starts ascending rather than inheriting a direction', () => {
    host.sort.set({ key: 'ticker', direction: 'desc' });
    fixture.detectChanges();

    const pnlHeader = el().querySelectorAll('thead th .sort')[1] as HTMLButtonElement;
    pnlHeader.click();

    expect(host.lastSort).toEqual({ key: 'pnl', direction: 'asc' });
  });

  it('marks the sorted column for assistive technology', () => {
    host.sort.set({ key: 'pnl', direction: 'desc' });
    fixture.detectChanges();

    const sorted = [...el().querySelectorAll('thead th')].map((h) => h.getAttribute('aria-sort'));
    expect(sorted).toEqual([null, 'descending']);
  });

  it('offers no sort control on a column that is not sortable', () => {
    host.visible.set(['held']);
    fixture.detectChanges();

    expect(el().querySelector('thead th .sort')).toBeNull();
  });

  /* -- property 4: pagination is supplied as a unit, or not at all -------- */

  it('shows no pager when the data is not paginated', () => {
    // Risk, Universe and Analytics/Strategies all return plain lists. Under
    // the original contract each would have passed total = rows.length, which
    // is the bug the `total` rule exists to prevent.
    expect(host.pagination()).toBeNull();
    expect(el().querySelector('.pager')).toBeNull();
  });

  it('shows no pager when everything fits on one page', () => {
    host.pagination.set({ total: 3, page: 1, perPage: 25 });
    fixture.detectChanges();

    expect(el().querySelector('.pager')).toBeNull();
  });

  it('derives the pager from `total`, not from the rows it was handed', () => {
    host.pagination.set({ total: 90, page: 2, perPage: 25 });
    fixture.detectChanges();

    expect(el().querySelector('.pager .range')!.textContent).toContain('26–50 of 90');
    expect(el().querySelector('.pager .of')!.textContent).toContain('2 / 4');
  });

  it('emits the requested page and disables the ends', () => {
    host.pagination.set({ total: 90, page: 1, perPage: 25 });
    fixture.detectChanges();

    const [previous, next] = [...el().querySelectorAll('.pager button')] as HTMLButtonElement[];
    expect(previous.disabled).toBe(true);

    next.click();
    expect(host.pages).toEqual([2]);

    host.pagination.set({ total: 90, page: 4, perPage: 25 });
    fixture.detectChanges();
    const last = [...el().querySelectorAll('.pager button')][1] as HTMLButtonElement;
    expect(last.disabled).toBe(true);
  });

  it('survives a perPage of zero without dividing by it', () => {
    host.pagination.set({ total: 90, page: 1, perPage: 0 });
    fixture.detectChanges();

    expect(el().querySelector('.pager')).toBeNull();
  });

  /* -- property 3: expansion is the caller's template --------------------- */

  it('shows no expander column when no expansion template is given', () => {
    expect(el().querySelector('.expander')).toBeNull();
    expect(headers()).toHaveLength(2);
  });

  it('renders the caller template on expand and removes it on collapse', () => {
    host.withExpansion.set(true);
    fixture.detectChanges();

    const expander = () => el().querySelector('.expander') as HTMLButtonElement;
    expander().click();
    fixture.detectChanges();
    expect(el().querySelector('.expansion-body')!.textContent).toContain('AAPL detail');

    expander().click();
    fixture.detectChanges();
    expect(el().querySelector('.expansion-body')).toBeNull();
  });

  it('spans the expansion across every rendered column', () => {
    host.withExpansion.set(true);
    fixture.detectChanges();
    (el().querySelector('.expander') as HTMLButtonElement).click();
    fixture.detectChanges();

    // Two visible columns plus the expander cell.
    expect(el().querySelector('tr.expansion td')!.getAttribute('colspan')).toBe('3');
  });

  it('keeps expansion attached to the row, not to its position', () => {
    // A refetch reorders rows constantly under real-time push. Keying by
    // index would leave a different trade expanded after every event.
    host.withExpansion.set(true);
    fixture.detectChanges();
    (el().querySelectorAll('.expander')[2] as HTMLButtonElement).click();
    fixture.detectChanges();

    host.rows.set([ROWS[2], ROWS[0], ROWS[1]]);
    fixture.detectChanges();

    const expandedRow = el().querySelector('tr.expansion')!.previousElementSibling!;
    expect(cells(expandedRow)).toContain('NVDA');
  });

  /* -- row activation ----------------------------------------------------- */

  it('activates a row that is clicked', () => {
    bodyRows()[1].dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(host.activated).toEqual([ROWS[1]]);
  });

  it('does not activate the row when an action button is clicked', () => {
    // Otherwise no workspace could put "close trade" in a cell without it
    // also navigating to the trade.
    host.visible.set(['ticker', 'actions']);
    fixture.detectChanges();

    (bodyRows()[0].querySelector('button.action') as HTMLButtonElement).dispatchEvent(
      new MouseEvent('click', { bubbles: true }),
    );

    expect(host.activated).toEqual([]);
  });

  it('does not activate the row when the expander is clicked', () => {
    host.withExpansion.set(true);
    fixture.detectChanges();

    (el().querySelector('.expander') as HTMLButtonElement).dispatchEvent(
      new MouseEvent('click', { bubbles: true }),
    );

    expect(host.activated).toEqual([]);
  });

  /* -- cells and the empty state ------------------------------------------ */

  it('renders a null value as an em dash rather than a blank or a zero', () => {
    // On P&L those differ by everything: blank reads as a rendering fault and
    // zero reads as a flat trade.
    expect(cells(bodyRows()[2])[1]).toBe('—');
  });

  it('prefers a cell template over the value function', () => {
    host.visible.set(['actions']);
    fixture.detectChanges();

    expect(bodyRows()[0].querySelector('button.action')).not.toBeNull();
  });

  it('shows the empty state only once there is nothing and nothing is loading', () => {
    host.emptyState.set({ title: 'No trades match this filter', hint: 'Clear the filters' });
    host.rows.set([]);
    host.loading.set(true);
    fixture.detectChanges();
    // "No trades match" under a spinner is a claim the table cannot yet make.
    expect(el().querySelector('.empty')).toBeNull();

    host.loading.set(false);
    fixture.detectChanges();
    expect(el().querySelector('.empty-title')!.textContent).toContain('No trades match');
    expect(el().querySelector('.empty-hint')!.textContent).toContain('Clear the filters');
  });

  it('shows no empty state when the caller did not supply one', () => {
    host.rows.set([]);
    fixture.detectChanges();

    expect(el().querySelector('.empty')).toBeNull();
  });

  it('marks itself busy while loading', () => {
    host.loading.set(true);
    fixture.detectChanges();

    expect(el().querySelector('.wrap')!.getAttribute('aria-busy')).toBe('true');
  });
});
