import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { LiveValuesStore } from '../stores/live-values.store';
import { marketAgeLabel } from './age-hint';
import { BREAKPOINTS } from './breakpoints';
import { CLOCK } from './clock';
import { Spinner } from './spinner';

/**
 * v201: a price (or any figure derived from one) with its age, a spinner
 * while a refresh is pending and "refresh failed" when it was not answered.
 * The projected content is the value; with no as-of the value slot is
 * hidden, so a never-priced cell is the spinner alone. The meta wraps under
 * the value on a phone and never widens its column.
 */
@Component({
  selector: 'sb-market-value',
  imports: [Spinner],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[class.mv-empty]': 'empty()' },
  template: `<span class="mv" [attr.data-tone]="tone()"><span class="mv-value" [hidden]="asOf() === null"><ng-content /></span><span class="mv-meta">@if (spinning()) {<sb-spinner label="Refreshing" />} @if (label().text; as t) {<span class="mv-age">{{ t }}</span>} @if (error()) {<span class="mv-err">refresh failed</span>}</span></span>`,
  styles: `
    :host { display: inline-block; max-width: 100%; }
    /* Nothing to show (no as-of, no spinner, no error): take no line, so a
       cell's other content (the Watchlist bar date) centres in its row
       instead of sitting under an empty line (layout audit, 9px low). */
    :host(.mv-empty) { display: none; }
    .mv { display: inline-flex; flex-wrap: wrap; align-items: baseline; column-gap: var(--space-4); max-width: 100%; }
    /* baseline + a centred spinner: the age text, not the textless spinner's
       bottom edge, gives the meta its baseline, so "12 s ago" sits on the
       price's baseline (layout audit, 3px off before). */
    .mv-meta sb-spinner { align-self: center; }
    .mv-meta { display: inline-flex; align-items: baseline; gap: var(--space-4); font-size: var(--text-micro); color: var(--text-faint); font-variant-numeric: tabular-nums; --spinner-size: 10px; }
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
  readonly refreshing = input(false);
  readonly error = input<string | null>(null);

  private readonly clock = inject(CLOCK);
  private readonly live = inject(LiveValuesStore);

  protected readonly label = computed(() => marketAgeLabel(this.asOf(), this.clock(), this.live.status()));
  protected readonly tone = computed(() => this.label().tone);
  protected readonly spinning = computed(() => this.refreshing() && !this.error());
  protected readonly empty = computed(() =>
    this.asOf() === null && !this.spinning() && !this.error() && !this.label().text);
}
