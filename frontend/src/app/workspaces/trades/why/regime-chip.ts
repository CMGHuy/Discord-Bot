import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Chip, ChipTone } from '../../../ui/chip';

export interface RegimeChipView { label: string; tone: ChipTone; prefix: string }

/** v239: the engine's shadow action stamped on the plan at issue (spec § Plan-card chip). */
const CHIPS: Readonly<Record<string, RegimeChipView>> = {
  would_veto: { label: 'would skip', tone: 'bad', prefix: '×' },
  caution: { label: 'caution', tone: 'warn', prefix: '!' },
  pullback_watch: { label: 'pullback watch', tone: 'info', prefix: '↺' },
  aligned: { label: 'aligned', tone: 'neutral', prefix: '' },
};

/**
 * The chip for a plan's stamped `regime_action`, or null for a legacy plan,
 * `none`, or any value this table does not know (never guessed).
 */
export function regimeChip(ctx: Record<string, unknown> | null | undefined): RegimeChipView | null {
  const action = ctx?.['regime_action'];
  return typeof action === 'string' && Object.hasOwn(CHIPS, action) ? { ...CHIPS[action] } : null;
}

/**
 * v239: the regime a plan was issued under, read from its own entry_context
 * (never today's state). Shadow only: the words say it changed nothing, and
 * the text prefix keeps colour from being the only cue.
 */
@Component({
  selector: 'sb-regime-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip],
  template: `
    @if (chip(); as c) {
      <span class="regime-chip" [attr.title]="title()">
        <span class="sr">Regime when issued: </span>
        <sb-chip [label]="c.prefix ? c.prefix + ' ' + c.label : c.label" [tone]="c.tone" [caps]="false" />
      </span>
    }
  `,
  styles: `
    :host { display: inline-flex; flex: none; }
    .regime-chip { display: inline-flex; align-items: baseline; }
    .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
    @media (max-width: 639px) {
      :host { flex-basis: 100%; }
    }
  `,
})
export class RegimeChip {
  readonly context = input<Record<string, unknown> | null | undefined>(null);

  protected readonly chip = computed(() => regimeChip(this.context()));

  protected readonly title = computed(() => {
    const c = this.chip();
    return c ? `Regime when issued: ${c.label} (shadow, no effect on this plan)` : null;
  });
}
