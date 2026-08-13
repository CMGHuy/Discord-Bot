import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  input,
  output,
  viewChild,
} from '@angular/core';

import { EmptyStateComponent } from './empty-state';

/**
 * The frame every chart is drawn into — spec v14 Decision 10.
 *
 * **This is the shell (NG40). NG45 mounts `lightweight-charts` 5.x into
 * `surface()` and adds the price lines.** It is deliberately split: the shell
 * is ordinary declarative Angular, while the chart itself is imperative canvas
 * state with a disposal contract, and keeping the loading/empty/error chrome
 * out of that file means the tricky part stays small.
 *
 * What the shell owns, so NG45 does not have to re-solve it per call site:
 *
 *  - **One host element with a stable size.** A chart library that measures a
 *    zero-height parent renders a zero-height chart, which is the single most
 *    common way this goes wrong.
 *  - **The three non-chart states.** Loading, error and no-data are chrome,
 *    not chart, and a half-initialised chart library rendering "no data" in
 *    its own house style would not match anything else in the UI.
 *  - **No colours of its own.** Everything is a token, so NG45's theme object
 *    can be built from the same tokens rather than from hardcoded hex — the
 *    requirement Decision 10 states outright.
 *
 * `OnPush` here means the surface element is never re-created, so the chart
 * instance projected into it outlives every re-render — which is exactly what
 * imperative canvas state needs.
 */
@Component({
  selector: 'sb-chart-container',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [EmptyStateComponent],
  template: `
    <figure class="frame" [style.height.px]="height()">
      @if (caption(); as text) {
        <figcaption>{{ text }}</figcaption>
      }

      <!-- Always present, never behind an @if: the chart library measures
           this element, and an element that appears a tick later measures as
           zero and renders as nothing. The chart is PROJECTED into it rather
           than mounted from outside, so the container owns the element's
           lifetime and the chart component owns the canvas. -->
      <div #surface class="surface" [class.hidden]="state() !== 'ready'">
        <ng-content />
      </div>

      @switch (state()) {
        @case ('loading') {
          <div class="overlay"><span class="spinner" aria-label="Loading chart"></span></div>
        }
        @case ('error') {
          <div class="overlay">
            <sb-empty-state
              [title]="error()!"
              [hint]="canRetry() ? '' : 'The chart will retry on the next update.'"
            />
            @if (canRetry()) {
              <!-- Inside the overlay rather than in the empty state, because the
                   empty state is used all over the app and none of the others
                   has an action. -->
              <button type="button" class="retry" (click)="retry.emit()">Retry</button>
            }
          </div>
        }
        @case ('empty') {
          <div class="overlay">
            <sb-empty-state title="No price history for this window" />
          </div>
        }
      }
    </figure>
  `,
  styles: `
    .frame {
      position: relative;
      display: flex;
      flex-direction: column;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
    }
    figcaption {
      padding: var(--space-8) var(--space-10);
      border-bottom: 1px solid var(--border);
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .surface {
      flex: 1;
      min-height: 0;
    }
    /* Hidden rather than removed, so the element keeps its measured size. */
    .hidden {
      visibility: hidden;
    }

    .overlay {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      align-content: center;
      gap: var(--space-10);
    }
    .retry {
      padding: var(--space-6) var(--space-14);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
      background: var(--surface-raised);
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      cursor: pointer;
    }
    .retry:hover {
      border-color: var(--accent);
      color: var(--accent);
    }
    .spinner {
      width: 18px;
      height: 18px;
      border: 2px solid var(--border-strong);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin 700ms linear infinite;
    }
    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .spinner {
        animation-duration: 2.4s;
      }
    }
  `,
})
export class ChartContainer {
  readonly loading = input(false);
  readonly error = input<string | null>(null);
  /** False when the series came back with no bars — distinct from an error,
   *  and from still loading. */
  readonly hasData = input(true);
  readonly height = input(320);
  readonly caption = input<string | null>(null);
  /** Whether the failure is worth offering a retry for. Opt-in, because not
   *  every store has one — `OhlcvStore` refetches on its own signals and has no
   *  retry method, and a button that does nothing is worse than no button. */
  readonly canRetry = input(false);

  /** Pressed retry. The container knows nothing about what failed, so the
   *  decision of what to re-issue stays with the store that issued it. */
  readonly retry = output<void>();

  /** Kept for anything that needs to measure the drawing area. The chart
   *  itself arrives by projection and does not need this. */
  readonly surface = viewChild.required<ElementRef<HTMLDivElement>>('surface');

  /** Error beats loading: a refetch that failed should say so rather than
   *  spin forever. */
  protected readonly state = computed<'loading' | 'error' | 'empty' | 'ready'>(() => {
    if (this.error()) return 'error';
    if (this.loading()) return 'loading';
    if (!this.hasData()) return 'empty';
    return 'ready';
  });
}
