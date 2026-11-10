import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { TapeShock } from '../api/models';
import { shockSummary } from './tape/tape';

/**
 * v210: the market-shock state in the phone top bar. Below 640px the shell
 * hides the tape strip and with it the tape's badge (V210-3b), so a phone
 * reads SHOCK / RECOVERY here. NORMAL and "no reading" render nothing: the
 * bar spends no width on a calm market. A status, never a control -- the
 * numbers are in its accessible name; the Discord notice carries the rest.
 */
@Component({
  selector: 'sb-shock-pill',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (shown(); as s) {
      <span class="shock-pill" role="status" [attr.data-label]="s.label"
            [attr.aria-label]="summary()" [attr.title]="summary()">{{ s.label }}</span>
    }
  `,
  styles: `
    :host { display: inline-flex; }
    .shock-pill { display: inline-flex; align-items: center; flex: none; height: 24px;
                  padding: 0 var(--space-6); border: 1px solid currentColor;
                  border-radius: var(--chip-radius); font-size: var(--text-chip);
                  font-weight: 650; letter-spacing: .06em; white-space: nowrap; }
    .shock-pill[data-label='SHOCK'] { color: var(--neg); background: var(--neg-soft); }
    .shock-pill[data-label='RECOVERY'] { color: var(--warn); background: var(--warn-soft); }
    @media (min-width: 640px) {
      :host { display: none; }
    }
  `,
})
export class ShockPill {
  readonly shock = input<TapeShock | null>(null);
  protected readonly shown = computed(() => {
    const s = this.shock();
    return s && s.label !== 'NORMAL' ? s : null;
  });
  protected readonly summary = computed(() => {
    const s = this.shown();
    return s ? shockSummary(s) : null;
  });
}
