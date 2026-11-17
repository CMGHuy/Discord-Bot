import { ChangeDetectionStrategy, Component } from '@angular/core';

import { Hint } from './hint';

/**
 * v228 -- the marker for an MFE/MAE figure measured on daily bars for a
 * trade held under two days. The daily bar's range includes price before the
 * fill and after the exit, so the figure may be overstated (measured on
 * production 2026-11-14: median loser MFE 1.24R stored vs 0.31R on 5-minute
 * bars). One rule everywhere -- this file, exit_quality.is_daily_estimate on
 * the server and the Discord chart suffix.
 *
 * The visible text carries the meaning, so nothing depends on hover; the
 * explanation sits in an sb-hint, whose trigger is a real button (Tab, tap)
 * named by its aria-label.
 */
export const EXCURSION_EST_LABEL = 'est. (daily bars)';
export const EXCURSION_EST_EXPLANATION =
  'Held under 2 days, intraday bars unavailable, the range may be overstated.';

/** Holds this long or longer are trusted even on daily bars
 *  (exit_quality.TRUSTED_MIN_HOLD_DAYS). */
const TRUSTED_MIN_HOLD_DAYS = 2;

/** True when a figure came from daily bars on a hold under two days. An
 *  unknown hold (null, undefined, NaN) on daily bars counts as short, as on
 *  the server: every daily figure is either trusted or marked. */
export function isDailyEstimate(
  source: string | null | undefined,
  heldDays: number | null | undefined,
): boolean {
  if (source !== 'daily') return false;
  if (heldDays === null || heldDays === undefined || Number.isNaN(heldDays)) return true;
  return heldDays < TRUSTED_MIN_HOLD_DAYS;
}

@Component({
  selector: 'sb-excursion-est',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hint],
  template: `<span class="est">{{ label }}</span><sb-hint [text]="explanation" label="About this estimate" align="left" />`,
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      color: var(--warn);
      font-size: var(--text-micro);
      white-space: nowrap;
    }
  `,
})
export class ExcursionEstimate {
  protected readonly label = EXCURSION_EST_LABEL;
  protected readonly explanation = EXCURSION_EST_EXPLANATION;
}
