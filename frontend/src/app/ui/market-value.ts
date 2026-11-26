import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { MarketStatus } from '../api/models';
import { LiveValuesStore } from '../stores/live-values.store';
import { marketAgeLabel } from './age-hint';
import { BREAKPOINTS } from './breakpoints';
import { CLOCK } from './clock';
import { Spinner } from './spinner';

export const ERROR_TEXT_MAX = 60;

/** True when the failure is not older than the price it would explain. */
export function errorIsCurrent(errorAt: string | null, asOf: string | null): boolean {
  return errorAt === null || asOf === null || Date.parse(errorAt) >= Date.parse(asOf);
}

function shortError(error: string): string {
  return error.length <= ERROR_TEXT_MAX ? error : error.slice(0, ERROR_TEXT_MAX - 1) + '…';
}

function priceErrorVisible(
  asOf: string | null, errorAt: string | null, nowMs: number, status: MarketStatus | null,
): boolean {
  if (status?.session !== 'regular') return false;
  const limit = status.stale_price_s;
  const stale = asOf === null || (limit !== null && (nowMs - Date.parse(asOf)) / 1000 > limit);
  return stale && errorIsCurrent(errorAt, asOf);
}

/**
 * v201: a price (or any figure derived from one) with its age, a spinner
 * while a refresh is pending and, in the regular session only, `refresh failed: <error>` when the shown
 * price is stale or missing and the failure is newer than it (v248 § 1b).
 * The value slot stays hidden until a quote has an as-of time or a snapshot
 * has a build time. The meta wraps under
 * the value on a phone and never widens its column.
 */
@Component({
  selector: 'sb-market-value',
  imports: [Spinner],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[class.mv-empty]': 'empty()', '[class.mv-err-only]': 'errorOnly()', '[class.mv-has-err]': 'showError()' },
  template: `<span class="mv" [attr.data-tone]="tone()"><span class="mv-value" [hidden]="valueHidden()"><ng-content /></span><span class="mv-meta">@if (spinning()) {<sb-spinner label="Refreshing" />} @if (label().text; as t) {<span class="mv-age">{{ t }}</span>} @if (showError()) {<span class="mv-err" [attr.title]="error()">{{ errorText() }}</span>}</span></span>`,
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
    .mv-meta { display: inline-flex; align-items: baseline; gap: var(--space-4); font-size: var(--text-micro); color: var(--text-muted); font-variant-numeric: tabular-nums; --spinner-size: 10px; }
    [data-tone=stale] .mv-age, [data-tone=stalled] .mv-age { color: var(--warn); }
    [data-tone=failed] .mv-age { color: var(--neg); }
    .mv-err { color: var(--neg); }
    @media (max-width: ${BREAKPOINTS.sm - 1}px) {
      .mv { flex-direction: column; align-items: flex-start; }
      .mv-meta { white-space: normal; overflow-wrap: anywhere; }
      /* The error-only host sits in a nowrap compact line beside a figure: a full-width
         basis puts it on its own line, where the error wraps instead of running off-screen. */
      :host(.mv-err-only), :host(.mv-has-err) { display: block; flex: 1 1 100%; min-width: 0; white-space: normal; }
      :host(.mv-err-only) .mv, :host(.mv-has-err) .mv { white-space: normal; }
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
  readonly errorAt = input<string | null>(null);
  /** v248: show only a current refresh error, never the age line (a phone P&L cell). */
  readonly errorOnly = input(false);

  private readonly clock = inject(CLOCK);
  private readonly live = inject(LiveValuesStore);

  protected readonly label = computed(() => this.errorOnly() ? { text: null, tone: 'fresh' as const } : marketAgeLabel(this.asOf(), this.clock(), this.live.status(), {
    kind: this.kind(), staleInputs: this.staleInputs(), computedAt: this.computedAt(),
  }));
  protected readonly valueHidden = computed(() => this.errorOnly() || (this.kind() === 'snapshot' ? this.computedAt() : this.asOf()) === null);
  protected readonly showError = computed(() => this.error() !== null
    && (this.kind() === 'snapshot' || priceErrorVisible(this.asOf(), this.errorAt(), this.clock(), this.live.status())));
  protected readonly errorText = computed(() => {
    const error = this.error();
    if (this.kind() === 'snapshot' || error === null) return 'refresh failed';
    return (this.label().text ? '· ' : '') + 'refresh failed: ' + shortError(error);
  });
  protected readonly tone = computed(() => (this.showError() && this.kind() === 'price' ? 'failed' : this.label().tone));
  protected readonly spinning = computed(() => this.refreshing() && !this.showError());
  protected readonly empty = computed(() =>
    this.valueHidden() && !this.spinning() && !this.showError() && !this.label().text);
}
