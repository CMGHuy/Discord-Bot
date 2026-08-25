import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { money, num, pct, rMultiple, share } from './format';

/**
 * Entry, target and stop in one cell — spec v18 Decision 4.
 *
 * Always reads `entry → target / stop`, in that order, for both directions.
 * For a short the target is the LOWER number and the stop the higher one, so
 * the colours carry which is which, not the positions. Anything that inferred
 * role from magnitude would read correctly on every long and invert silently
 * on every short — which is the worst version of the bug, because the cell
 * still looks plausible.
 *
 * Three columns collapse into one here, so the tooltip spells the roles out:
 * the colour pair alone is not readable for everyone, and a bare `178.00 →
 * 195.00 / 170.00` does not say which number is the stop.
 */
@Component({
  selector: 'sb-plan-cell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="plan" [title]="tooltip()">
      <span class="entry" [class.pending]="showsTrigger()">{{ fmt(first()) }}</span>
      <span class="sep">{{ ' → ' }}</span>
      <span class="target">{{ fmt(target()) }}</span>
      <span class="sep">{{ ' / ' }}</span>
      <span class="stop">{{ fmt(stop()) }}</span>
    </span>
  `,
  styles: `
    /* nowrap is the TABLE rule -- three prices and two separators read as one
       plan, and a column has a scroller behind it. --cell-wrap is DataTable's
       card-mode override (see its .card-value block): undefined here, so a
       table keeps nowrap; set to normal inside a card, where the run has no
       column to align to and nothing to scroll and would otherwise be cut off
       at the edge of a phone. */
    .plan {
      font-family: var(--font-mono);
      font-size: var(--text-table);
      white-space: var(--cell-wrap, nowrap);
    }
    .entry  { color: var(--text-secondary); }
    /* A trigger is a price nothing has traded at yet. Dashed underline rather
       than a colour: the palette's hues all mean something already, and
       "provisional" is not one of them. */
    .entry.pending {
      color: var(--text-faint);
      border-bottom: 1px dashed currentColor;
    }
    .target { color: var(--pos); }
    .stop   { color: var(--neg); }
    /* Spacing lives in the TEXT, not in a margin. Angular strips whitespace
       between elements, so a margin-only gap renders correctly and leaves
       textContent as '178.00→195.00/170.00' -- which is what a screen reader
       announces and what anything reading the cell as a string gets. In a
       mono font the literal spaces are exactly one cell wide anyway.
       --sep-wrap is the card-mode counterpart of --cell-wrap above: pre-wrap
       there, so the run can break at a separator without the spacing
       collapsing and running the numbers together. */
    .sep    { color: var(--text-faint); white-space: var(--sep-wrap, pre); }
  `,
})
export class PlanCell {
  readonly entry = input<number | null>(null);
  readonly target = input<number | null>(null);
  readonly stop = input<number | null>(null);
  /**
   * The stop-entry price a plan is still waiting on — SR53.
   *
   * A PENDING plan has no `entry`: nothing has filled. Without this the cell
   * read `— → 195.00 / 170.00`, which says the two levels but not the price
   * that would put you in them, and the trigger was the actionable number the
   * old plans board led with.
   */
  readonly trigger = input<number | null>(null);

  /**
   * True once TP1 has banked and `stop`/`target` are the runner's own
   * working_stop/TP2 rather than the original plan levels. For a
   * short that working stop legitimately sits BELOW entry -- it protects
   * the profit TP1 already locked in, not the original risk -- which reads
   * as backwards (a short's stop "should" be on the far side of entry from
   * target) unless the tooltip says why.
   */
  readonly trailing = input<boolean>(false);

  /* -- v58: the banked TP1 leg, shown in the tooltip once PARTIAL -------- */

  /** Fraction of the position TP1 closed (0-1). Null until PARTIAL. */
  readonly bankedFraction = input<number | null>(null);
  /** The TP1 leg's own R-multiple. */
  readonly bankedR = input<number | null>(null);
  /** %-gain on the TP1 leg, from the position's ORIGINAL entry to the
   *  leg's own exit price -- not the same number as the R-multiple. */
  readonly bankedPct = input<number | null>(null);
  /** $-amount for the same leg. Null when size is unknown -- omitted
   *  rather than shown as zero. */
  readonly bankedAmount = input<number | null>(null);
  /** The TP1 leg's own fill price -- the runner's "entry" for display
   *  purposes, distinct from `entry` above (the original position entry). */
  readonly bankedEntry = input<number | null>(null);
  /** Needed to format `bankedAmount`; the caller's own currency symbol. */
  readonly currency = input<string | null>(null);

  /** True when the first number is a trigger rather than a fill. */
  protected readonly showsTrigger = computed(
    () => this.entry() === null && this.trigger() !== null,
  );

  protected readonly first = computed(() =>
    this.showsTrigger() ? this.trigger() : this.entry(),
  );

  protected readonly tooltip = computed(() => {
    // Names the role, because the styling difference alone does not: an
    // unfilled plan and a filled one are one glyph apart otherwise.
    const lead = this.showsTrigger()
      ? `Trigger ${this.fmt(this.trigger())} (not yet filled)`
      : `Entry ${this.fmt(this.entry())}`;
    const stopWord = this.trailing() ? 'Trailing stop' : 'Stop';
    let out = `${lead} · Target ${this.fmt(this.target())} · ${stopWord} ${this.fmt(this.stop())}`;
    const fraction = this.bankedFraction();
    const r = this.bankedR();
    const entry = this.bankedEntry();
    if (fraction !== null && r !== null && entry !== null) {
      const extras: string[] = [];
      const pctVal = this.bankedPct();
      if (pctVal !== null) extras.push(pct(pctVal));
      const amountVal = this.bankedAmount();
      const currencyVal = this.currency();
      if (amountVal !== null && currencyVal !== null) extras.push(money(amountVal, currencyVal));
      const extraText = extras.length ? ` (${extras.join(', ')})` : '';
      out += ` · ${share(fraction * 100)} banked ${rMultiple(r)}${extraText} @ ${this.fmt(entry)}`;
    }
    return out;
  });

  protected fmt(v: number | null): string {
    return num(v);
  }
}

/** %-gain on an already-banked leg, from the position's ORIGINAL entry to
 *  that leg's own fill price, signed by direction -- the number a trader
 *  means by "how much did that leg make", not the R-multiple alone. */
export function bankedLegPct(
  entry: number | null,
  bankedEntry: number | null,
  direction: string,
): number | null {
  if (entry === null || bankedEntry === null || entry === 0) return null;
  const raw = ((bankedEntry - entry) / entry) * 100;
  return direction === 'bearish' ? -raw : raw;
}

/** $-amount for the same leg -- the ORIGINAL share count times the fraction
 *  that leg closed, times the move from entry to its own fill price. Null
 *  when any input needed to compute it is unknown. */
export function bankedLegAmount(
  entry: number | null,
  bankedEntry: number | null,
  bankedFraction: number | null,
  shares: number | null,
  direction: string,
): number | null {
  if (entry === null || bankedEntry === null || bankedFraction === null || shares === null) {
    return null;
  }
  const raw = (bankedEntry - entry) * shares * bankedFraction;
  return direction === 'bearish' ? -raw : raw;
}
