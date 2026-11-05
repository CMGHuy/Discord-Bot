import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { LiveValuesStore } from '../stores/live-values.store';
import { marketAgeLabel } from './age-hint';
import { BREAKPOINTS } from './breakpoints';
import { CLOCK } from './clock';
import { Spinner } from './spinner';

/**
 * v201: a price (or any figure derived from one) with its age, a spinner
 * while a refresh is pending and "refresh failed" when it was not answered.
 * The value slot stays hidden until a quote has an as-of time or a snapshot
 * has a build time. The meta wraps under
 * the value on a phone and never widens its column.
 */
@Component({
  selector: 'sb-market-value',
  imports: [Spinner],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="mv" [attr.data-tone]="tone()"><span class="mv-value" [hidden]="valueHidden()"><ng-content /></span><span class="mv-meta">@if (spinning()) {<sb-spinner label="Refreshing" />} @if (label().text; as t) {<span class="mv-age">{{ t }}</span>} @if (error()) {<span class="mv-err">refresh failed</span>}</span></span>`,
  styles: `
    :host { display: inline-block; max-width: 100%; }
    .mv { display: inline-flex; flex-wrap: wrap; align-items: baseline; column-gap: var(--space-4); max-width: 100%; }
    .mv-meta { display: inline-flex; gap: var(--space-4); font-size: var(--text-micro); color: var(--text-faint); font-variant-numeric: tabular-nums; --spinner-size: 10px; }
    [data-tone=stale] .mv-age, [data-tone=stalled] .mv-age { color: var(--warn); }
    .mv-err { color: var(--neg); }
    @media (max-width: ${BREAKPOINTS.sm - 1}px) {
      .mv { flex-direction: column; align-items: flex-start; }
      .mv-meta { white-space: normal; overflow-wrap: anywhere; }
    }
  `,
})
export class MarketValue {
  readonly asOf = input<string | null>(null);
  readonly kind = input<'price' | 'snapshot'>('price');
  readonly staleInputs = input(false);
  readonly computedAt = input<string | null>(null);
  readonly refreshing = input(false);
  readonly error = input<string | null>(null);

  private readonly clock = inject(CLOCK);
  private readonly live = inject(LiveValuesStore);

  protected readonly label = computed(() => marketAgeLabel(this.asOf(), this.clock(), this.live.status(), {
    kind: this.kind(), staleInputs: this.staleInputs(), computedAt: this.computedAt(),
  }));
  protected readonly valueHidden = computed(() => (this.kind() === 'snapshot' ? this.computedAt() : this.asOf()) === null);
  protected readonly tone = computed(() => this.label().tone);
  protected readonly spinning = computed(() => this.refreshing() && !this.error());
}
