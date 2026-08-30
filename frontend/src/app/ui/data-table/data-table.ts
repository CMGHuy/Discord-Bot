import { NgTemplateOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { EmptyStateComponent } from '../empty-state';
import { PaginationComponent } from '../pagination';
import { ViewportService } from '../breakpoints';
import {
  ColumnDef,
  EmptyState,
  PageSpec,
  RowContext,
  SortSpec,
} from './data-table.types';

/** How long `loading` must stay true before the spinner shows -- see
 *  `DataTable.showSpinner`'s own comment for why this exists at all. */
export const SPINNER_DELAY_MS = 200;

/**
 * The load-bearing table — spec `2026-08-08-v14-angular-workspaces-design.md`
 * Decision 1. Trades, Analytics/Strategies, Risk and Watchlist all render
 * through this one component, which is why it was built and settled before any
 * of them started: discovering the API is wrong afterwards means rewriting
 * four workspaces.
 *
 * Five properties the contract enforces, none of which are conveniences:
 *
 *  1. **Server-side everything.** Sorting and paging emit events; this
 *     component never reorders or slices `rows`. The API already works this
 *     way, and a table that sorts only the page it can see is the specific bug
 *     that convention exists to prevent.
 *  2. **`visible` is a set of keys and its order is ignored.** Render order
 *     comes from `columns`. There is no ordering input, so the drag-to-reorder
 *     behaviour that was removed cannot creep back in through a call site.
 *  3. **Row expansion is the caller's template**, not a config object — every
 *     workspace expands into something different, and the alternative slowly
 *     reinvents templates as JSON.
 *  4. **`pagination.total` is post-filter, pre-slice.** See `PageSpec`.
 *  5. **No data access.** This component cannot fetch and does not know a
 *     store exists.
 *
 * The pager and the empty state are `PaginationComponent` and
 * `EmptyStateComponent` (NG39). They live outside this file because Dashboard
 * and the Analytics panels need an empty state without a table, but the table
 * still owns *when* they appear — a caller cannot forget to render the pager.
 */
@Component({
  selector: 'sb-data-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet, EmptyStateComponent, PaginationComponent],
  template: `
    <div class="wrap" [attr.aria-busy]="loading()">
      @if (showSpinner()) {
        <span class="loading-spinner" aria-hidden="true"></span>
      }
      @if (pagination(); as page) {
        <ng-container [ngTemplateOutlet]="pagerTemplate" [ngTemplateOutletContext]="{ $implicit: page, announce: true }" />
      }      @if (cards()) {
        <!-- SR24. A rendering MODE of this component, not a second component:
             same column defs, same sort, same pagination. A separate mobile
             table drifts from the desktop one within two changes, and then
             every column added to one is missing from the other. -->
        <ul class="cards">
          @for (row of rows(); track rowKey()(row)) {
            <li class="card" [class]="rowClass()(row)" (click)="activate(row, $event)">
              <div class="card-head">
                @for (col of headlineColumns(); track col.key) {
                  <span class="head-cell">
                    @if (col.cell; as cellTemplate) {
                      <ng-container
                        [ngTemplateOutlet]="cellTemplate"
                        [ngTemplateOutletContext]="{ $implicit: row }"
                      />
                    } @else {
                      {{ text(col, row) }}
                    }
                  </span>
                }
              </div>

              <!-- The same label/value grid the expansion uses (SR18), so the
                   card and the expanded row cannot drift apart. -->
              <dl class="card-body">
                @for (col of bodyColumns(); track col.key) {
                  <div>
                    <dt>{{ col.header }}</dt>
                    <dd class="card-value" [class.num]="col.numeric">
                      @if (col.cell; as cellTemplate) {
                        <ng-container
                          [ngTemplateOutlet]="cellTemplate"
                          [ngTemplateOutletContext]="{ $implicit: row }"
                        />
                      } @else {
                        {{ text(col, row) }}
                      }
                    </dd>
                  </div>
                }
              </dl>

              @for (col of pinnedColumns(); track col.key) {
                @if (col.cell; as cellTemplate) {
                  <div class="card-actions">
                    <ng-container
                      [ngTemplateOutlet]="cellTemplate"
                      [ngTemplateOutletContext]="{ $implicit: row }"
                    />
                  </div>
                }
              }
            </li>
          }
        </ul>
      } @else {
      <div class="scroller" tabindex="0">
      <table>
        <thead>
          <tr>
            @if (expansion()) {
              <th class="expander-cell"><span class="sr-only">Expand row</span></th>
            }
            @for (col of renderedColumns(); track col.key) {
              <th
                [style.width]="col.width"
                [class.num]="col.numeric"
                [class.dragging]="dragging() === col.key"
                [attr.aria-sort]="ariaSort(col)"
                [attr.draggable]="isPinned(col.key) ? null : 'true'"
                [attr.tabindex]="isPinned(col.key) ? null : 0"
                [attr.aria-label]="isPinned(col.key) ? null : col.header + ' column, arrow keys to reorder'"
                (dragstart)="onDragStart(col.key, $event)"
                (dragover)="onDragOver(col.key, $event)"
                (drop)="onDrop(col.key, $event)"
                (dragend)="onDragEnd()"
                (keydown)="onHeaderKeydown(col.key, $event)"
              >
                @if (col.sortable) {
                  <button type="button" class="sort" (click)="toggleSort(col)">
                    <span>{{ col.header }}</span>
                    <span class="arrow" aria-hidden="true">{{ arrow(col) }}</span>
                  </button>
                } @else {
                  {{ col.header }}
                }
              </th>
            }
          </tr>
        </thead>

        <tbody>
          @for (row of rows(); track rowKey()(row)) {
            <tr class="row" [class]="rowClass()(row)" (click)="activate(row, $event)">
              @if (expansion()) {
                <td class="expander-cell">
                  <button
                    type="button"
                    class="expander"
                    [attr.aria-expanded]="isExpanded(row)"
                    [attr.aria-label]="isExpanded(row) ? 'Collapse row' : 'Expand row'"
                    (click)="toggleExpanded(row)"
                  >
                    {{ isExpanded(row) ? '▾' : '▸' }}
                  </button>
                </td>
              }
              @for (col of renderedColumns(); track col.key) {
                <td [class.num]="col.numeric">
                  @if (col.cell; as cellTemplate) {
                    <ng-container
                      [ngTemplateOutlet]="cellTemplate"
                      [ngTemplateOutletContext]="{ $implicit: row }"
                    />
                  } @else {
                    {{ text(col, row) }}
                  }
                </td>
              }
            </tr>

            @if (expansion(); as expansionTemplate) {
              @if (isExpanded(row)) {
                <tr class="expansion">
                  <td [attr.colspan]="colspan()">
                    <ng-container
                      [ngTemplateOutlet]="expansionTemplate"
                      [ngTemplateOutletContext]="{ $implicit: row }"
                    />
                  </td>
                </tr>
              }
            }
          }
          @for (slot of fillerRows(); track slot) {
            <tr class="filler" aria-hidden="true"><td [attr.colspan]="colspan()"></td></tr>
          }
        </tbody>
        @if (hasFooter()) {
          <tfoot><tr>
            @if (expansion()) { <td class="expander-cell"></td> }
            @for (col of renderedColumns(); track col.key) { <td [class.num]="col.numeric">{{ footerText(col) }}</td> }
          </tr></tfoot>
        }
      </table>
      </div>
      }

      @if (showEmptyState(); as state) {
        <sb-empty-state [title]="state.title" [hint]="state.hint" />
      }

      @if (pagination(); as page) {
        <ng-container [ngTemplateOutlet]="pagerTemplate" [ngTemplateOutletContext]="{ $implicit: page, announce: false }" />
      }
    </div>

    <ng-template #pagerTemplate let-page let-announce="announce">
      <sb-pagination [pagination]="page" [showPerPage]="showPerPage()" [announce]="announce"
        (pageChange)="pageChange.emit($event)" (perPageChange)="perPageChange.emit($event)" />
    </ng-template>  `,
  styles: `
    .cards { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-10); }
    .card {
      padding: var(--space-14);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      display: grid;
      gap: var(--space-10);
    }
    .card-head {
      display: flex;
      align-items: center;
      gap: var(--space-10);
      font-size: var(--text-subhead);
    }
    .card-body { margin: 0; display: grid; gap: var(--space-6); }
    /* align-items: baseline, so a label sits on the first line of a value
       that wrapped to two rather than floating in the middle of it. */
    .card-body > div {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--space-10);
      min-width: 0;
    }
    /* The label never shrinks and never wraps -- it is two or three words and
       it is what makes the value legible. The VALUE is what gives. */
    .card-body dt {
      flex: 0 0 auto;
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }
    /* min-width: 0 is the load-bearing part.
     *
     * A flex item's automatic minimum size is its content's min-content
     * width, so without this a long value pushes the row wider than the card
     * instead of wrapping inside it. The table has .scroller as its
     * backstop for exactly this; a CARD has none, so what overflows is not
     * scrolled to, it is simply off the side of a phone and unreadable --
     * the whole reason card mode exists is that it does not need one.
     *
     * text-align: right so the value column reads down the card the way the
     * numeric columns do, and overflow-wrap so a long single token (a
     * strategy name, an id) breaks rather than being the one thing that can
     * still overflow. */
    .card-body dd {
      margin: 0;
      min-width: 0;
      flex: 0 1 auto;
      text-align: right;
      overflow-wrap: anywhere;
    }
    /* -- the wrap contract for rich cells -------------------------------
     *
     * A dense cell (PlanCell's .plan, the Dashboard's .pnl-plan) declares
     * white-space: nowrap for the TABLE, where a price split over two lines
     * stops reading as one number and .scroller is there when a run does not
     * fit. In a card neither holds: no column to align to, and no scroller --
     * body carries overflow-x: hidden, so a run that does not wrap is not
     * scrolled to, it is CUT OFF. Measured at 375px: the Dashboard's P&L cell
     * came to 279px inside a 255px box, losing the projected half of the line.
     *
     * Custom properties rather than a selector, because no selector can do
     * this. Emulated encapsulation scopes EVERY compound selector, not just
     * the last, so ".card-value .pnl-plan" compiles with a content attribute
     * on BOTH parts -- and the two elements carry different ones (the dd is
     * this component's, the span is the workspace's), so the rule matches
     * from neither side. A global rule reaches both but then loses on
     * specificity to the cell's own scoped ".plan[content-attr]". Custom
     * properties inherit down the DOM and are indifferent to all of it.
     *
     * A cell opts in by reading the fallback form:
     *     white-space: var(--cell-wrap, nowrap);   // the run itself
     *     white-space: var(--sep-wrap, pre);       // its separators
     * Outside a card neither is defined, so the nowrap/pre default applies
     * and the table is unchanged.
     *
     * pre-wrap, not normal, for the separators: their spacing IS the spacing
     * (PlanCell puts it in the text, not a margin), so collapsing it would run
     * the numbers together -- while plain "pre" forbids the wrap this exists
     * to allow. */
    .card-value {
      --cell-wrap: normal;
      --sep-wrap: pre-wrap;
    }
    /* Full width, because a 24px icon button is not a phone target. */
    .card-actions { display: grid; gap: var(--space-6); }
    .card-actions button { width: 100%; }
    th[draggable='true'] { cursor: grab; }
    th.dragging { opacity: 0.5; }
    th:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .wrap { position: relative; }
    /* pointer-events: none alongside the dim: without it a click mid-fetch
       can land on a row that is about to be replaced, which reads as "I
       clicked and nothing happened" -- itself a "frozen" symptom -- rather
       than as the table simply being busy. */
    .wrap[aria-busy='true'] {
      opacity: 0.6;
      transition: opacity var(--transition);
      pointer-events: none;
    }
    /* See showSpinner's own comment for the delay this only appears after.
       Same visual language as ChartContainer's spinner (border-top accent
       colour, 700ms linear spin) -- one loading affordance across the app
       rather than two that look slightly different. */
    .loading-spinner {
      position: absolute;
      top: var(--space-8);
      right: var(--space-8);
      width: 14px;
      height: 14px;
      border: 2px solid var(--border-strong);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin 700ms linear infinite;
      z-index: 1;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    @media (prefers-reduced-motion: reduce) {
      .loading-spinner { animation-duration: 2.4s; }
    }

    /* NG54. Cells are white-space:nowrap by design — a wrapped price is
     * worse than a scroll — so a wide column set makes the table wider than
     * its column and something has to give. Without this it was the PAGE
     * that scrolled: with all 24 Trades columns picked the document went to
     * 1877px at a 1280px viewport, taking the sidebar and header off-screen
     * with it. Measured during A5's browser half; the geometry in A5 covers
     * the row EXPANSION, which fits, and says nothing about the table.
     *
     * Scrolling the table inside its own box keeps the chrome fixed. It sits
     * inside .wrap rather than on it so the pagination below stays put too.
     *
     * tabindex="0" because a scroll container that only a mouse can reach is
     * unreachable by keyboard; making it focusable is what lets arrow keys
     * scroll it. Chrome warns about exactly this otherwise. */
    .scroller { overflow-x: auto; }
    .scroller:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: var(--text-table);
    }
    /* Wrapping is the default now, and it is what keeps a wide column set
     * inside the workspace instead of behind a scrollbar.
     *
     * Everything here used to be white-space: nowrap, which made the table's
     * minimum width the sum of its longest cells -- so the scroller below
     * engaged on almost any column set, and its scrollbar sits at the BOTTOM
     * of the table, a page-scroll away from the header someone is trying to
     * line data up with. A scrollbar you have to leave the data to reach is
     * not a scrollbar you can use.
     *
     * Only multi-word cells actually wrap: a ticker, a price and a date are
     * single tokens and render exactly as before. What gives is the long
     * stuff -- status phrases, plan names, strategy labels -- which is width
     * the table did not need. The scroller stays as the backstop for the
     * genuinely un-shrinkable case. */
    th, td {
      padding: var(--space-6) var(--space-10);
      text-align: left;
      border-bottom: 1px solid var(--border);
      overflow-wrap: break-word;
    }
    /* Figures are the exception and have to be. A price broken across two
       lines stops reading as one number, and the right-alignment that makes
       a column of magnitudes scannable only works on a single line.
       The HEADER above them is deliberately not exempt: "Realized pnl
       amount" is three times the width of the numbers under it, and letting
       it wrap is most of what the change above buys back. */
    td.num { white-space: nowrap; }
    th {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    /* Digits line up down the column, so a magnitude is readable without
       reading the number. */
    .num { text-align: right; font-family: var(--font-mono); }
    .num.sort, th.num .sort { justify-content: flex-end; }

    .sort {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      width: 100%;
      padding: 0;
      background: none;
      border: 0;
      color: inherit;
      font: inherit;
      letter-spacing: inherit;
      text-transform: inherit;
      cursor: pointer;
    }
    .sort:hover { color: var(--text); }
    .sort:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    /* Reserved width, so cycling the sort does not shift the header row. */
    .arrow { display: inline-block; min-width: 0.7em; color: var(--accent); }

    .row:hover { background: var(--surface-raised); }
    tr.filler > td { background: var(--bg); border-bottom: 0; height: calc(1lh + 2 * var(--space-6)); }
    tfoot td { border-top: 1px solid var(--border-strong); border-bottom: 0; font-weight: 600; color: var(--text); }
    thead th { position: sticky; top: var(--header-h); z-index: 2; background: var(--surface); }

    /* A pulse, not a hard on/off flash: WCAG's flash-rate guidance exists
       for a reason, and an opacity/background fade reads as "attention"
       without the seizure risk of a true blink. Respects
       prefers-reduced-motion -- the row still needs telling apart, so it
       falls back to a steady tint rather than losing the signal entirely. */
    .blink { animation: sb-row-blink 1.6s ease-in-out infinite; }
    .blink:hover { animation-play-state: paused; }
    @keyframes sb-row-blink {
      0%, 100% { background: transparent; }
      50% { background: color-mix(in srgb, var(--warn) 16%, transparent); }
    }
    @media (prefers-reduced-motion: reduce) {
      .blink { animation: none; background: color-mix(in srgb, var(--warn) 10%, transparent); }
    }
    .expansion > td { background: var(--surface); white-space: normal; }

    .expander-cell { width: 1px; padding-right: 0; }
    .expander {
      padding: 0 var(--space-4);
      background: none;
      border: 0;
      color: var(--text-muted);
      cursor: pointer;
      font-size: var(--text-body);
    }
    .expander:hover { color: var(--text); }
    .expander:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }

    .sr-only {
      position: absolute;
      width: 1px; height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }
  `,
})
export class DataTable<T> {
  readonly rows = input.required<T[]>();
  /** The full set, in the order they are meant to render. */
  readonly columns = input.required<ColumnDef<T>[]>();
  /** Column keys. A set, not a sequence — see property 2. */
  readonly visible = input.required<string[]>();
  /** Stable identity per row: the `@for` track and the expansion key. */
  readonly rowKey = input.required<(row: T) => string>();
  /** An extra CSS class for the whole row (or card), or null for none --
   *  e.g. a blink animation on a row whose date is imminent. Optional and a
   *  no-op when unset, so the three other call sites are unaffected. */
  readonly rowClass = input<(row: T) => string | null>(() => null);

  readonly sort = input<SortSpec | null>(null);
  /** `null` means this data is not paginated: render every row, show no
   *  pager. See `PageSpec` for why this is one input rather than three. */
  readonly pagination = input<PageSpec | null>(null);
  readonly loading = input(false);
  readonly expansion = input<TemplateRef<RowContext<T>> | null>(null);
  readonly emptyState = input<EmptyState | null>(null);

  readonly sortChange = output<SortSpec>();
  readonly pageChange = output<number>();
  readonly visibleChange = output<string[]>();
  readonly rowActivate = output<T>();

  /** Columns the user may not move. Dragging one, or dropping onto one, is a
   *  no-op rather than a silently-refused gesture that looks broken. */
  readonly pinned = input<string[]>([]);
  /** Emitted with the full new order whenever a column is moved. */
  readonly reorder = output<string[]>();

  /** Forwarded to the pager. The table does not own paging policy —
   *  it renders the control and passes the choice back up. */
  readonly showPerPage = input(false);
  readonly perPageChange = output<number>();

  /** The key currently being dragged, or null. Signal rather than a field so
   *  the header can style itself while the drag is in flight. */
  protected readonly dragging = signal<string | null>(null);

  /**
   * True only once `loading` has stayed true for `SPINNER_DELAY_MS`.
   *
   * Every refetch -- an event-stream push, a Today/All days toggle, a sort
   * click -- keeps the previous `rows` on screen rather than clearing them
   * first (correct: a table that flashes empty on every poll is worse than
   * one that shows slightly stale data for a moment). But that leaves NO
   * feedback that anything is happening at all beyond a 40% opacity dim
   * (`.wrap[aria-busy]` below), which most local/event-driven fetches clear
   * in well under a human's reaction time -- so the dim reads as a flicker
   * or a rendering glitch rather than "updating", which is the "frozen"
   * complaint this exists to fix. Gating the spinner on a short delay is
   * what stops that flicker showing up as a SECOND flicker of its own: a
   * fetch that settles inside the delay never shows a spinner at all, and
   * one that takes longer gets an unambiguous "this is working" signal
   * instead of just a hair less contrast.
   */
  protected readonly showSpinner = signal(false);

  constructor() {
    effect((onCleanup) => {
      if (!this.loading()) {
        this.showSpinner.set(false);
        return;
      }
      const timer = setTimeout(() => this.showSpinner.set(true), SPINNER_DELAY_MS);
      onCleanup(() => clearTimeout(timer));
    });
  }

  /** Expanded rows, by `rowKey`. Keyed rather than indexed so a refetch that
   *  reorders or repages the rows does not leave a different row expanded. */
  private readonly expanded = signal<ReadonlySet<string>>(new Set());

  /** Order comes from `visible`, which SR14 made an ordered list.
   *
   *  Built by looking each key up rather than by filtering `columns`, because
   *  filtering would silently reimpose the declaration order and make a
   *  reorder look like it had not taken. Unknown keys are skipped: `visible`
   *  can arrive from a saved preference, and SR12's reader is tolerant for
   *  the same reason. */
  protected readonly renderedColumns = computed(() => {
    const byKey = new Map(this.columns().map((column) => [column.key, column]));
    return this.visible()
      .map((key) => byKey.get(key))
      .filter((column): column is ColumnDef<T> => column !== undefined);
  });

  /**
   * Cards instead of a table, below `sm` — spec v18 Decision 9.
   *
   * Driven by the viewport rather than by an input, so no call site has to
   * remember to ask for it. `cardsAt` exists only so a test can force the
   * mode without a layout engine: jsdom does not lay out, so asserting on
   * widths there would be theatre.
   */
  private readonly viewportService = inject(ViewportService);
  readonly cardsAt = input<boolean | null>(null);
  protected readonly cards = computed(
    () => this.cardsAt() ?? this.viewportService.isPhone(),
  );

  /** Ticker and direction: what identifies the row at a glance. Falls back to
   *  the first two visible columns for a table with neither. */
  protected readonly headlineColumns = computed(() => {
    const shown = this.renderedColumns();
    const preferred = shown.filter((c) => ['ticker', 'direction'].includes(c.key));
    return preferred.length ? preferred : shown.slice(0, 2);
  });

  /** Everything else in the visible set, as label/value pairs. */
  protected readonly bodyColumns = computed(() => {
    const headline = new Set(this.headlineColumns().map((c) => c.key));
    return this.renderedColumns().filter((c) => !headline.has(c.key));
  });

  /** Pinned columns become full-width controls under the card body. */
  protected readonly pinnedColumns = computed(() =>
    this.columns().filter((c) => this.pinnedSet().has(c.key)),
  );

  /** Keys the table pins in place — not draggable, not a drop target. */
  private readonly pinnedSet = computed(() => new Set(this.pinned()));

  protected isPinned(key: string): boolean {
    return this.pinnedSet().has(key);
  }

  /**
   * Move `key` so it sits where `target` is now.
   *
   * Splice-out-then-insert rather than a swap: a swap is only equivalent for
   * adjacent columns, and dragging one header across four others should land
   * it where it was dropped rather than trading places with whatever was
   * there.
   */
  private move(key: string, target: string): void {
    if (key === target || this.isPinned(key) || this.isPinned(target)) return;
    const order = this.visible().slice();
    const from = order.indexOf(key);
    const to = order.indexOf(target);
    if (from < 0 || to < 0) return;
    order.splice(from, 1);
    order.splice(to, 0, key);
    this.reorder.emit(order);
  }

  protected onDragStart(key: string, event: DragEvent): void {
    if (this.isPinned(key)) {
      event.preventDefault();
      return;
    }
    this.dragging.set(key);
    // Firefox ignores a drag that carries no data at all.
    event.dataTransfer?.setData('text/plain', key);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
  }

  protected onDragOver(key: string, event: DragEvent): void {
    // preventDefault is what marks a valid drop target; without it the
    // browser refuses the drop and the gesture looks broken.
    if (this.dragging() === null || this.isPinned(key)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
  }

  protected onDrop(key: string, event: DragEvent): void {
    event.preventDefault();
    const source = this.dragging() ?? event.dataTransfer?.getData('text/plain') ?? '';
    this.dragging.set(null);
    if (source) this.move(source, key);
  }

  protected onDragEnd(): void {
    this.dragging.set(null);
  }

  /**
   * Left/Right on a focused header moves that column one place.
   *
   * A mouse-only reorder is simply unavailable to a keyboard user, and this
   * table is the product's main surface -- so the drag has a keyboard
   * equivalent rather than an apology. Pinned columns are skipped over rather
   * than swapped with, so a move never lands a column somewhere the drag
   * could not have put it.
   */
  protected onHeaderKeydown(key: string, event: KeyboardEvent): void {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (step === 0 || this.isPinned(key)) return;

    const order = this.visible();
    let index = order.indexOf(key) + step;
    while (index >= 0 && index < order.length && this.isPinned(order[index])) index += step;
    if (index < 0 || index >= order.length) return;

    event.preventDefault();
    this.move(key, order[index]);
  }

  protected readonly colspan = computed(
    () => this.renderedColumns().length + (this.expansion() ? 1 : 0),
  );
  protected readonly fillerRows = computed<number[]>(() => {
    const page = this.pagination();
    if (!page || page.perPage <= 0 || this.cards()) return [];
    const missing = page.perPage - this.rows().length;
    return missing > 0 ? Array.from({ length: missing }, (_, i) => i) : [];
  });

  protected readonly hasFooter = computed(
    () => this.rows().length > 0 && this.renderedColumns().some((column) => column.footer),
  );

  protected footerText(column: ColumnDef<T>): string {
    const value = column.footer?.(this.rows());
    return value === null || value === undefined ? '' : String(value);
  }

  /** Not while loading: "No trades match this filter" under a spinner is a
   *  claim the table cannot yet make. */
  protected readonly showEmptyState = computed(() =>
    !this.loading() && this.rows().length === 0 ? this.emptyState() : null,
  );

  /** An em dash, not an empty cell: a value that has not been computed reads
   *  as missing, where blank reads as a rendering fault. */
  protected text(column: ColumnDef<T>, row: T): string {
    const value = column.value?.(row);
    return value === null || value === undefined || value === '' ? '—' : String(value);
  }

  protected ariaSort(column: ColumnDef<T>): 'ascending' | 'descending' | null {
    const sort = this.sort();
    if (!column.sortable || sort?.key !== column.key) return null;
    return sort.direction === 'asc' ? 'ascending' : 'descending';
  }

  protected arrow(column: ColumnDef<T>): string {
    const sort = this.sort();
    if (sort?.key !== column.key) return '';
    return sort.direction === 'asc' ? '↑' : '↓';
  }

  /** A new column starts ascending and repeat clicks toggle. There is no
   *  third "unsorted" state — the API always sorts by something, so a cycle
   *  back to none would emit a sort the server cannot express. */
  protected toggleSort(column: ColumnDef<T>): void {
    const sort = this.sort();
    const direction =
      sort?.key === column.key && sort.direction === 'asc' ? 'desc' : 'asc';
    this.sortChange.emit({ key: column.key, direction });
  }

  protected isExpanded(row: T): boolean {
    return this.expanded().has(this.rowKey()(row));
  }

  protected toggleExpanded(row: T): void {
    const key = this.rowKey()(row);
    this.expanded.update((current) => {
      const next = new Set(current);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  }

  /**
   * Row clicks activate the row, except when the click landed on something
   * that handles its own click — an action button, a link to the detail page.
   * Without this a workspace could not put a "close trade" button in a cell
   * without it also navigating away.
   *
   * Activation is mouse-only by design. A call site that needs the row
   * reachable by keyboard puts a real `<a>` or `<button>` in a cell (Trades
   * uses the `#` column); making every row focusable would put Risk's and
   * Watchlist's read-only rows into the tab order for nothing.
   */
  protected activate(row: T, event: Event): void {
    const target = event.target as HTMLElement | null;
    if (target?.closest('button, a, input, select, textarea, label')) return;
    this.rowActivate.emit(row);
  }
}
