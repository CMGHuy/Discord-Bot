import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { ConnectionStore } from '../stores/connection.store';

/** The D2 windows as the SPA sees them. The server's `.env` knobs are not
 *  served to the SPA; changing one moves what is fetched, and only these
 *  decide when the hint appears. */
export const DASHBOARD_PRICE_WINDOW_S = 15;
export const PAGE_PRICE_WINDOW_S = 60;
export const TAPE_WINDOW_S = 60;

export function ageText(ageS: number | null): string | null {
  if (ageS === null || Number.isNaN(ageS) || ageS < 0) return null;
  if (ageS < 60) return `${Math.round(ageS)} s ago`;
  if (ageS < 3600) return `${Math.floor(ageS / 60)} min ago`;
  return `${Math.floor(ageS / 3600)} h ago`;
}

/**
 * v171 D2: "12 s ago" beside a price older than its page's window, and
 * nothing otherwise. Prices render at once from the shared cache; this is
 * the only sign that one is older than the page promises (no spinner, no
 * veil, no colour). It does not tick: the page's own refetch moves it,
 * as with sb-freshness.
 */
@Component({
  selector: 'sb-age-hint',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (text(); as t) {
      <span class="age-hint" [attr.title]="'Price is ' + t.replace(' ago', '') + ' old'">{{ t }}</span>
    }
  `,
  styles: `
    :host { display: inline; }
    .age-hint {
      font-size: var(--text-micro);
      color: var(--text-faint);
      white-space: nowrap;
      margin-inline-start: var(--space-4);
      font-variant-numeric: tabular-nums;
    }
  `,
})
export class AgeHint {
  readonly ageS = input<number | null>(null);
  readonly windowS = input.required<number>();
  private readonly connection = inject(ConnectionStore);

  /** Market closed (or not known yet): every quote is "old", so say nothing. */
  protected readonly text = computed(() => {
    const age = this.ageS();
    if (this.connection.marketActive() !== true) return null;
    return age !== null && age > this.windowS() ? ageText(age) : null;
  });
}
