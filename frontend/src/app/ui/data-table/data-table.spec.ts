import {
  Component,
  TemplateRef,
  computed,
  provideZonelessChangeDetection,
  signal,
  viewChild,
} from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DataTable, SPINNER_DELAY_MS } from './data-table';
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
      [rowClass]="rowClass()"
      [sort]="sort()"
      [pagination]="pagination()"
      [loading]="loading()"
      [expansion]="withExpansion() ? expansionTemplate() : null"
      [emptyState]="emptyState()"
      [pinned]="pinned()"
      [cardsAt]="cardsAt()"
      (sortChange)="lastSort = $event"
      (pageChange)="pages.push($event)"
      (rowActivate)="activated.push($event)"
      (reorder)="reordered.push($event)"
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
  readonly pinned = signal<string[]>([]);
  readonly cardsAt = signal<boolean | null>(null);

  readonly expansionTemplate =
    viewChild.required<TemplateRef<RowContext<Row>>>('expansion');
  private readonly actionCell =
    viewChild.required<TemplateRef<RowContext<Row>>>('actionCell');

  readonly rowKey = (row: Row) => row.id;
  readonly rowClass = signal<(row: Row) => string | null>(() => null);

  readonly columns = computed<ColumnDef<Row>[]>(() => [
    { key: 'ticker', header: 'Ticker', value: (row) => row.ticker, sortable: true },
    { key: 'pnl', header: 'P&L %', value: (row) => row.pnl, numeric: true, sortable: true },
    { key: 'held', header: 'Held', value: () => '3d' },
    { key: 'actions', header: '', cell: this.actionCell() },
  ]);

  lastSort: SortSpec | null = null;
  readonly pages: number[] = [];
  readonly activated: Row[] = [];
  readonly reordered: string[][] = [];
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

  /* -- property 2: `visible` decides membership AND order ----------------- */

  it('renders only the visible columns', () => {
    expect(headers()).toEqual(['Ticker', 'P&L %']);
  });

  it('honours the order of `visible`', () => {
    // SR14 reverses the original contract, which said order could not be
    // expressed at all so that drag-to-reorder could never return through a
    // call site. Spec v18 Decision 4 brings it back deliberately -- see
    // "Reversal recorded" there, and ui/table-prefs.ts for the tolerance that
    // keeps a stale saved order from breaking a table.
    host.visible.set(['pnl', 'ticker']);
    fixture.detectChanges();

    expect(headers()).toEqual(['P&L %', 'Ticker']);
  });

  it('skips a visible key that is not a column', () => {
    // `visible` can arrive from a saved preference naming a column that has
    // since been removed.
    host.visible.set(['pnl', 'gone', 'ticker']);
    fixture.detectChanges();

    expect(headers()).toEqual(['P&L %', 'Ticker']);
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
    // Risk, Watchlist and Analytics/Strategies all return plain lists. Under
    // the original contract each would have passed total = rows.length, which
    // is the bug the `total` rule exists to prevent.
    expect(host.pagination()).toBeNull();
    expect(el().querySelector('.pager')).toBeNull();
  });

  it('keeps the row count visible when everything fits on one page', () => {
    host.pagination.set({ total: 3, page: 1, perPage: 25 });
    fixture.detectChanges();

    expect(el().querySelector('.pager .range')!.textContent).toContain('3 rows');
    expect(el().querySelectorAll('.pager button')).toHaveLength(0);
  });

  it('derives the pager from `total`, not from the rows it was handed', () => {
    host.pagination.set({ total: 90, page: 2, perPage: 25 });
    fixture.detectChanges();

    expect(el().querySelector('.pager .range')!.textContent).toContain('26–50 of 90');
    expect(el().querySelector('.pager .of')!.textContent).toContain('/ 4');
  });

  it('emits the requested page and disables the ends', () => {
    host.pagination.set({ total: 90, page: 1, perPage: 25 });
    fixture.detectChanges();

    const [, previous, next] = [...el().querySelectorAll('.pager button')] as HTMLButtonElement[];
    expect(previous.disabled).toBe(true);

    next.click();
    expect(host.pages).toEqual([2]);

    host.pagination.set({ total: 90, page: 4, perPage: 25 });
    fixture.detectChanges();
    const last = [...el().querySelectorAll('.pager button')][3] as HTMLButtonElement;
    expect(last.disabled).toBe(true);
  });

  it('survives a perPage of zero without dividing by it', () => {
    host.pagination.set({ total: 90, page: 1, perPage: 0 });
    fixture.detectChanges();

    expect(el().querySelector('.pager .range')!.textContent).toContain('90 rows');
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

  /* Report: a refetch reads as "frozen" rather than "updating" -- the dim
   * alone (`.wrap[aria-busy]`) is the only feedback, and most local/event-
   * driven fetches clear before a human would even register it. The spinner
   * is the fix, gated on a short delay so IT doesn't become a second flicker
   * on the fetches that were already fast enough. */
  describe('the delayed loading spinner', () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it('does not show immediately when loading starts', () => {
      host.loading.set(true);
      fixture.detectChanges();

      expect(el().querySelector('.loading-spinner')).toBeNull();
    });

    it('shows once loading has stayed true past the delay', () => {
      host.loading.set(true);
      fixture.detectChanges();

      vi.advanceTimersByTime(SPINNER_DELAY_MS);
      fixture.detectChanges();

      expect(el().querySelector('.loading-spinner')).not.toBeNull();
    });

    it('never shows when loading clears before the delay elapses', () => {
      host.loading.set(true);
      fixture.detectChanges();

      vi.advanceTimersByTime(SPINNER_DELAY_MS - 1);
      host.loading.set(false);
      fixture.detectChanges();

      vi.advanceTimersByTime(SPINNER_DELAY_MS);
      fixture.detectChanges();

      expect(el().querySelector('.loading-spinner')).toBeNull();
    });

    it('hides again once loading clears after having shown', () => {
      host.loading.set(true);
      fixture.detectChanges();
      vi.advanceTimersByTime(SPINNER_DELAY_MS);
      fixture.detectChanges();
      expect(el().querySelector('.loading-spinner')).not.toBeNull();

      host.loading.set(false);
      fixture.detectChanges();

      expect(el().querySelector('.loading-spinner')).toBeNull();
    });
  });
});

// --- SR14: drag-to-reorder, and its keyboard equivalent -------------------
// Spec v18 Decision 4, "Reversal recorded". Order is meaningful again, so the
// component must honour `visible`'s order and let it be changed by both mouse
// and keyboard.

describe('DataTable reordering', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.visible.set(['ticker', 'pnl', 'held']);
    fixture.detectChanges();
  });

  const ths = () => [...fixture.nativeElement.querySelectorAll('thead th')] as HTMLElement[];
  const headerText = () => ths().map((th) => th.textContent!.trim());

  function drag(fromIndex: number, toIndex: number): void {
    const data = new Map<string, string>();
    const dataTransfer = {
      setData: (k: string, v: string) => void data.set(k, v),
      getData: (k: string) => data.get(k) ?? '',
      effectAllowed: '',
      dropEffect: '',
    };
    const list = ths();
    for (const [type, index] of [['dragstart', fromIndex], ['dragover', toIndex], ['drop', toIndex]] as const) {
      list[index].dispatchEvent(
        Object.assign(new Event(type, { bubbles: true, cancelable: true }), { dataTransfer }));
    }
    fixture.detectChanges();
  }

  function arrow(index: number, key: 'ArrowLeft' | 'ArrowRight'): void {
    ths()[index].dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    fixture.detectChanges();
  }

  it('renders in `visible` order, not in `columns` order', () => {
    host.visible.set(['held', 'ticker']);
    fixture.detectChanges();
    expect(headerText()).toEqual(['Held', 'Ticker']);
  });

  it('reorders on drop and emits the new order', () => {
    drag(2, 0);                                   // Held onto Ticker
    expect(host.reordered.at(-1)).toEqual(['held', 'ticker', 'pnl']);
  });

  it('moves rather than swaps across a gap', () => {
    // A swap is only equivalent for adjacent columns; dropped across two, a
    // column should land where it was dropped.
    drag(0, 2);                                   // Ticker onto Held
    expect(host.reordered.at(-1)).toEqual(['pnl', 'held', 'ticker']);
  });

  it('will not drag a pinned column', () => {
    host.pinned.set(['ticker']);
    fixture.detectChanges();
    drag(0, 2);
    expect(host.reordered).toEqual([]);
  });

  it('will not drop onto a pinned column', () => {
    host.pinned.set(['ticker']);
    fixture.detectChanges();
    drag(2, 0);
    expect(host.reordered).toEqual([]);
  });

  it('marks only the unpinned headers draggable', () => {
    host.pinned.set(['ticker']);
    fixture.detectChanges();
    expect(ths()[0].getAttribute('draggable')).toBeNull();
    expect(ths()[1].getAttribute('draggable')).toBe('true');
  });

  it('moves a column with the arrow keys', () => {
    arrow(0, 'ArrowRight');
    expect(host.reordered.at(-1)).toEqual(['pnl', 'ticker', 'held']);
  });

  it('does not walk a column off either end', () => {
    arrow(0, 'ArrowLeft');
    expect(host.reordered).toEqual([]);
  });

  it('skips over a pinned neighbour rather than swapping with it', () => {
    host.pinned.set(['pnl']);
    fixture.detectChanges();
    arrow(0, 'ArrowRight');
    expect(host.reordered.at(-1)).toEqual(['pnl', 'held', 'ticker']);
  });

  it('gives a keyboard user something to focus and a hint about it', () => {
    expect(ths()[0].getAttribute('tabindex')).toBe('0');
    expect(ths()[0].getAttribute('aria-label')).toContain('arrow keys to reorder');
  });
});

// --- SR24: card mode below 640px ------------------------------------------
// Forced through `cardsAt` rather than by resizing: jsdom does not lay out,
// so driving this with a real width would assert nothing.

describe('DataTable card mode', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.visible.set(['ticker', 'pnl', 'held']);
    host.pinned.set(['actions']);
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const cards = () => [...el().querySelectorAll('.card')];

  function asCards() {
    host.cardsAt.set(true);
    fixture.detectChanges();
  }

  it('renders a table by default', () => {
    expect(el().querySelector('table')).not.toBeNull();
    expect(cards()).toHaveLength(0);
  });

  it('renders one card per row and no table below the breakpoint', () => {
    asCards();
    expect(el().querySelector('table')).toBeNull();
    expect(cards()).toHaveLength(ROWS.length);
  });

  it('heads each card with the identifying columns', () => {
    asCards();
    expect(cards()[0].querySelector('.card-head')!.textContent).toContain('AAPL');
  });

  it('renders the rest as label/value pairs', () => {
    asCards();
    const body = cards()[0].querySelector('.card-body')!;
    expect([...body.querySelectorAll('dt')].map((d) => d.textContent!.trim()))
      .toEqual(['P&L %', 'Held']);
  });

  it('gives pinned columns their own full-width block', () => {
    // A 24px icon button is not a phone target.
    asCards();
    expect(cards()[0].querySelector('.card-actions')).not.toBeNull();
  });

  it('renders EVERY visible column -- a card drops nothing the table shows', () => {
    // The card is a rendering MODE, not a reduced view: a phone has to be
    // able to read the same figures a desktop does, or the density toggle
    // and the column picker mean nothing there. Headline and body together
    // are the visible set, exactly, with no key in both and none missing.
    host.visible.set(['ticker', 'pnl', 'held']);
    asCards();
    const card = cards()[0];
    const headline = [...card.querySelectorAll('.card-head .head-cell')];
    const labels = [...card.querySelectorAll('.card-body dt')]
      .map((d) => d.textContent!.trim());

    // 'ticker' heads the card (no label of its own), the rest are labelled.
    expect(headline).toHaveLength(1);
    expect(headline[0].textContent).toContain('AAPL');
    expect(labels).toEqual(['P&L %', 'Held']);
  });

  it('carries a value for every labelled row, not just the label', () => {
    // A <dt> with an empty <dd> beside it is the failure that looks like a
    // working card: the layout is right and the data is gone.
    host.visible.set(['ticker', 'pnl', 'held']);
    asCards();
    const values = [...cards()[0].querySelectorAll('.card-body dd')]
      .map((d) => d.textContent!.trim());
    expect(values).toEqual(['4.2', '3d']);
  });

  it('marks each value .card-value, the hook a dense cell wraps on', () => {
    // PlanCell and the Dashboard's P&L cell drop their table-only
    // `white-space: nowrap` under this class -- a card has no horizontal
    // scroller, so a run that does not wrap is simply off the side.
    host.visible.set(['ticker', 'pnl', 'held']);
    asCards();
    expect(cards()[0].querySelectorAll('.card-body dd.card-value')).toHaveLength(2);
  });

  it('still activates a row', () => {
    asCards();
    (cards()[1] as HTMLElement).click();
    expect(host.activated.map((r) => r.ticker)).toEqual(['MSFT']);
  });

  it('keeps pagination working', () => {
    host.pagination.set({ page: 1, perPage: 2, total: 9 });
    asCards();
    expect(el().querySelector('sb-pagination')).not.toBeNull();
  });

  it('returns to the table above the breakpoint', () => {
    asCards();
    host.cardsAt.set(false);
    fixture.detectChanges();
    expect(el().querySelector('table')).not.toBeNull();
    expect(cards()).toHaveLength(0);
  });
});

describe('DataTable rowClass', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const bodyRows = () => [...el().querySelectorAll('tbody tr.row')];

  it('adds nothing extra when unset — the three other call sites are unaffected', () => {
    expect(bodyRows().every((r) => r.className.trim() === 'row')).toBe(true);
  });

  it('applies the class only to rows the callback names', () => {
    host.rowClass.set((row) => (row.ticker === 'MSFT' ? 'blink' : null));
    fixture.detectChanges();

    const classes = bodyRows().map((r) => r.className);
    expect(classes).toEqual(['row', 'row blink', 'row']);
  });

  it('applies to cards too, not just table rows', () => {
    host.cardsAt.set(true);
    host.rowClass.set((row) => (row.ticker === 'MSFT' ? 'blink' : null));
    fixture.detectChanges();

    const cards = [...el().querySelectorAll('.card')];
    expect(cards.map((c) => c.className)).toEqual(['card', 'card blink', 'card']);
  });
});
