import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { FreshRequestService } from '../api/fresh-request.service';
import { EmptyStateComponent } from './empty-state';

/** Which empty this is. Not optional -- see the class comment. */
export type AsyncEmptyReason = 'no-data-yet' | 'measured-zero';

/** The placeholder's outline: a table (default), a panel, one figure, or a
 *  row of stat tiles on the strip grid (v186 D5). */
export type SkeletonShape = 'table' | 'panel' | 'figure' | 'tiles';

/** The shapes drawn as rows of cells. `'tiles'` has its own template branch. */
export type GridShape = Exclude<SkeletonShape, 'tiles'>;

/**
 * Rows of cell modifier classes for each grid shape (`''` is a plain cell).
 * Every cell keeps the table-row height (`--control-h`), so whatever
 * replaces the skeleton lands in the space it held and nothing reflows.
 */
const SKELETON_SHAPES: Record<GridShape, (rows: number, cols: number) => string[][]> = {
  table: (rows, cols) => Array.from({ length: rows }, () => Array.from({ length: cols }, () => '')),
  panel: (rows) => [['head'], ...Array.from({ length: Math.max(rows - 1, 0) }, () => [''])],
  figure: () => [['label'], ['value']],
};

export function skeletonGrid(shape: GridShape, rows: number, cols: number): string[][] {
  return SKELETON_SHAPES[shape](rows, cols);
}

/**
 * Bar widths by column index (v186 D5), repeating. A fixed sequence rather
 * than a random one, so a 4- and a 6-column skeleton are both deterministic
 * and a ragged right edge still reads as text, not as a progress bar.
 */
export const BAR_WIDTHS = ['40%', '65%', '30%', '55%'] as const;

export function barWidth(col: number): string {
  return BAR_WIDTHS[col % BAR_WIDTHS.length];
}

/**
 * The four states every fetch-backed region can be in, in one place.
 *
 * Before this, six of seven workspaces rendered nothing at all while
 * fetching, and an empty table looked identical whether the request failed,
 * the data had not arrived, or the answer was genuinely zero.
 *
 * emptyReason is required. known-traps.md records that this repo
 * contains empty tables which are measured answers rather than stubs. A table
 * showing no confluence setups because the scan found none is a RESULT;
 * rendering it like a failed fetch tells the reader the opposite of the
 * truth. Making the reason required means a call site that has not thought
 * about it does not compile.
 *
 * The loading branch is a SHAPED skeleton, not a spinner: it occupies the
 * geometry the loaded content will, so nothing reflows at the moment the
 * reader starts reading. A spinner swapped for a table moves every element on
 * the page. `shape` picks the outline (a table by default, a panel, a
 * single figure, or a row of stat tiles); thin bars pulsing quietly mark it
 * as loading (spec v186 D5, after v168 §3 #4's shimmer), still under
 * Motion = Reduced or Off (styles/motion.css).
 *
 * Branch order is error > loading > empty > content, so a refetch that fails
 * reports the failure rather than spinning forever.
 */
@Component({
  selector: 'sb-async',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [EmptyStateComponent],
  host: { '[attr.aria-busy]': 'loading() ? "true" : null' },
  template: `
    <!-- One region per sb-async, and therefore one per fetch-backed surface.
         Per-CELL live regions on a push-driven UI announce continuously,
         which is unusable — worse than silence. The caller supplies a
         summary ("3 trades updated"), not a running commentary. -->
    <span class="sr-only" aria-live="polite" aria-atomic="true">{{ announce() }}</span>
    @if (error(); as message) {
      <div class="failed" role="alert">
        <p class="failed-text">{{ message }}</p>
        <button class="retry" type="button" (click)="onRetry()">Retry</button>
      </div>
    } @else if (loading()) {
      @if (shape() === 'tiles') {
        <div class="skeleton shape-tiles" aria-hidden="true">
          <div class="sb-strip-grid sb-strip-fixed" [style.--strip-cols]="skeletonCols()">
            @for (tile of tiles(); track $index) {
              <div class="skeleton-tile">
                <span class="skeleton-bar label"></span>
                <span class="skeleton-bar value"></span>
              </div>
            }
          </div>
        </div>
      } @else {
        <div class="skeleton" [class]="'shape-' + shape()" aria-hidden="true">
          @for (row of grid(); track $index) {
            <div class="skeleton-row">
              @for (cell of row; track $index) {
                <span class="skeleton-cell" [class]="cell" [style.--bar-w]="barWidth($index)"></span>
              }
            </div>
          }
        </div>
      }
    } @else if (empty()) {
      <div class="empty-wrap">
        <span class="reason" [class]="emptyReason()">
          {{ emptyReason() === 'measured-zero' ? 'result: 0' : 'awaiting data' }}
        </span>
        <sb-empty-state [title]="emptyTitle()" [hint]="emptyHint()" />
      </div>
    } @else {
      @if (staleAsOf(); as at) {
        <span class="stale-badge">as of {{ at }}</span>
      }
      <div class="content" [class.stale]="staleAsOf() !== null">
        <ng-content />
      </div>
    }
  `,
  styles: `
    :host { display: block; position: relative; }

    .sr-only {
      position: absolute;
      width: 1px; height: 1px;
      margin: -1px; padding: 0;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }

    .failed { padding: var(--space-14); text-align: center; }
    .failed-text { color: var(--neg); font-size: var(--text-table); }
    .retry {
      margin-top: var(--space-8);
      min-height: var(--control-h);
      padding: 0 var(--space-14);
      border: 1px solid var(--border-strong);
      border-radius: var(--control-radius);
      background: var(--surface-raised);
      color: var(--text);
      font-family: var(--font-sans);
      font-size: var(--text-table);
      cursor: pointer;
    }

    .skeleton { display: flex; flex-direction: column; gap: var(--space-6); }
    .skeleton-row { display: flex; gap: var(--space-10); }
    /* The cell is a table row's height so the swap costs no layout shift; it
       paints nothing itself and centres a thin bar (spec v186 D5). */
    .skeleton-cell {
      flex: 1;
      display: flex;
      align-items: center;
      min-width: 0;
      height: var(--control-h);
    }
    .skeleton-cell.head { flex: 0 0 40%; }
    .skeleton-cell.label { flex: 0 0 35%; }
    .skeleton-cell.value { flex: 0 0 65%; }
    /* One quiet bar: an opacity pulse only, so no layout or neighbour paint.
       Under Motion = Reduced or Off the animation is dropped
       (styles/motion.css) and the bar rests at the base opacity. */
    .skeleton-cell::before,
    .skeleton-bar {
      content: '';
      display: block;
      height: 8px;
      border-radius: var(--radius-sm);
      background: color-mix(in srgb, var(--surface-raised) 55%, var(--border-strong));
      opacity: 0.7;
      animation: sb-skeleton-pulse calc(1800ms * var(--motion-scale)) ease-in-out infinite;
    }
    .skeleton-cell::before { width: var(--bar-w, 60%); }
    /* The shaped cells already carry their width in flex-basis. */
    .skeleton-cell.head::before,
    .skeleton-cell.label::before,
    .skeleton-cell.value::before { width: 100%; }

    /* 'tiles': the strip's own grid (styles.css .sb-strip-grid), so the
       placeholder breaks at the same widths the tiles will. The wrapper clips
       the grid's -1px start-edge offset, as sb-stat-strip does. */
    .shape-tiles { overflow: hidden; }
    .skeleton-tile {
      display: flex;
      flex-direction: column;
      gap: var(--space-10);
      min-width: 0;
      padding: var(--space-14);
    }
    .skeleton-bar.label { width: 35%; }
    .skeleton-bar.value { width: 60%; }

    .empty-wrap { text-align: center; }
    .reason {
      display: inline-block;
      padding: var(--space-4) var(--space-8);
      border-radius: var(--chip-radius);
      font-family: var(--font-mono);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    /* A measured zero is a NEUTRAL fact; missing data is a CAUTION. The two
       tokens are the whole visible difference and they are the point. */
    .reason.measured-zero { background: var(--info-soft); color: var(--info); }
    .reason.no-data-yet { background: var(--warn-soft); color: var(--warn); }

    .stale-badge {
      position: absolute;
      top: 0;
      right: 0;
      padding: var(--space-4) var(--space-6);
      border-radius: var(--chip-radius);
      background: var(--warn-soft);
      color: var(--warn);
      font-family: var(--font-mono);
      font-size: var(--text-micro);
    }
    .content.stale { color: var(--text-secondary); }
  `,
})
export class Async {
  readonly loading = input(false);
  readonly error = input<string | null>(null);
  readonly empty = input(false);
  /** Required: this input IS acceptance gate G2. */
  readonly emptyReason = input.required<AsyncEmptyReason>();
  readonly emptyTitle = input.required<string>();
  readonly emptyHint = input<string | undefined>(undefined);
  /** 'HH:MM', or null when the data is fresh. */
  readonly staleAsOf = input<string | null>(null);
  readonly skeletonRows = input(6);
  readonly skeletonCols = input(4);
  /** The placeholder's outline while loading (v168 §3 #4). */
  readonly shape = input<SkeletonShape>('table');
  /** A short summary of what just changed, or null. Announced politely. */
  readonly announce = input<string | null>(null);

  readonly retry = output<void>();

  private readonly fresh = inject(FreshRequestService);

  /** v171 D2: Retry is each page's own refresh control, so the reload it
   *  triggers fetches fresh market data instead of reusing the cache. The
   *  parent's handler runs synchronously inside emit(). */
  protected onRetry(): void {
    this.fresh.markFresh(() => this.retry.emit());
  }

  protected readonly grid = computed(() => {
    const shape = this.shape();
    return shape === 'tiles' ? [] : skeletonGrid(shape, this.skeletonRows(), this.skeletonCols());
  });

  /** 'tiles': skeletonRows rows of skeletonCols tiles (v186 D5). */
  protected readonly tiles = computed(() =>
    Array.from({ length: Math.max(this.skeletonRows(), 1) * Math.max(this.skeletonCols(), 1) }, (_, i) => i),
  );

  protected readonly barWidth = barWidth;
}

export interface AsyncSource<T> {
  data: () => T | null;
  loading: () => boolean;
  error: () => string | null;
}

export interface AsyncInputs {
  loading: boolean;
  error: string | null;
  empty: boolean;
  staleAsOf: string | null;
}

/**
 * Maps a store slice onto sb-async's inputs, preserving the v13 refetch rule.
 *
 * dashboard.store.ts records it: a refetch failure keeps the previous data
 * on screen, because replacing nine live numbers with an error panel over one
 * failed poll is worse than showing slightly stale numbers next to a warning.
 * Binding [error]="store.error()" straight through would break that on every
 * screen at once, so the mapping lives here and every call site uses it.
 *
 *   nothing on screen + error   -> error   ("there is nothing to show, and why")
 *   data on screen    + error   -> stale   ("these numbers stopped updating")
 *   nothing on screen + loading -> loading (skeleton)
 *   data on screen    + loading -> neither (a background refresh must not blank
 *                                           a screen the reader is reading)
 */
export function asyncInputs<T>(
  source: AsyncSource<T>,
  opts: { isEmpty: (data: T) => boolean; now?: () => Date },
): AsyncInputs {
  const data = source.data();
  const error = source.error();
  const has = data !== null;

  if (!has) {
    return {
      loading: source.loading(),
      error: source.loading() ? null : error,
      empty: false,
      staleAsOf: null,
    };
  }

  const clock = opts.now ?? (() => new Date());
  const stamp = clock();
  const staleAsOf = error
    ? `${String(stamp.getHours()).padStart(2, '0')}:${String(stamp.getMinutes()).padStart(2, '0')}`
    : null;

  return { loading: false, error: null, empty: opts.isEmpty(data), staleAsOf };
}
