import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * Where price sits between the stop and the target, as a fraction.
 *
 * `null` when it cannot be known — no price yet, or a plan whose stop and
 * target are equal. Null is not zero: zero means "sitting on the stop", which
 * is the worst a live trade can be, and showing that for a trade we simply
 * have no quote for would be a lie in the alarming direction.
 *
 * Works for both directions without a branch. On a short, `target < stop`, so
 * both numerator and denominator flip sign and the ratio still runs 0 at the
 * stop to 1 at the target.
 */
export function slToTpProgress(
  current: number | null | undefined,
  stop: number | null | undefined,
  target: number | null | undefined,
): number | null {
  if (current === null || current === undefined) return null;
  if (stop === null || stop === undefined) return null;
  if (target === null || target === undefined) return null;
  if (target === stop) return null;

  const fraction = (current - stop) / (target - stop);
  return Math.min(1, Math.max(0, fraction));
}

/**
 * A trade's state at a glance: a status dot, and for open trades the SL→TP
 * progress bar spec 3 asks for.
 *
 * Colour discipline is the whole point of this component. The dot is green or
 * red ONLY for a settled win or loss, because those are money. An open trade,
 * a cancelled plan and an expired one are states rather than outcomes, so they
 * take greyscale — an open trade shown in green would claim a profit it has
 * not made. The bar's fill is coloured by whether price is above or below the
 * entry, which IS P&L direction and so may be green or red.
 */
@Component({
  selector: 'sb-status-indicator',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="wrap">
      <span class="dot" [class]="dotClass()" [attr.aria-hidden]="true"></span>
      <span class="label">{{ status() }}</span>

      @if (progress(); as fraction) {
        <span
          class="track"
          role="progressbar"
          aria-label="Progress from stop toward target"
          [attr.aria-valuenow]="Math.round(fraction * 100)"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <span class="fill" [class]="fillClass()" [style.width.%]="fraction * 100"></span>
        </span>
      }
    </span>
  `,
  styles: `
    .wrap { display: inline-flex; align-items: center; gap: var(--space-6); }

    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--text-muted);
      flex: none;
    }
    .win { background: var(--pos); }
    .loss { background: var(--neg); }
    /* The blink survives from the old UI (spec 3 keeps it); it is the one
       motion that carries meaning -- this trade is live right now. */
    .open { background: var(--text); animation: pulse 2.2s ease-in-out infinite; }
    .inert { background: var(--text-faint); }

    @keyframes pulse { 50% { opacity: 0.35; } }
    @media (prefers-reduced-motion: reduce) {
      .open { animation: none; }
    }

    .label { font-size: var(--text-table); color: var(--text-secondary); }

    .track {
      position: relative;
      width: 48px;
      height: 3px;
      border-radius: 2px;
      background: var(--border-strong);
      overflow: hidden;
    }
    .fill { position: absolute; inset: 0 auto 0 0; background: var(--text-muted); }
    .fill.pos { background: var(--pos); }
    .fill.neg { background: var(--neg); }
  `,
})
export class StatusIndicator {
  readonly status = input.required<string>();
  readonly current = input<number | null>(null);
  readonly entry = input<number | null>(null);
  readonly stop = input<number | null>(null);
  readonly target = input<number | null>(null);

  protected readonly Math = Math;

  protected readonly dotClass = computed(() => {
    switch (this.status().toLowerCase()) {
      case 'win':
        return 'win';
      case 'loss':
        return 'loss';
      case 'open':
        return 'open';
      case 'cancelled':
      case 'canceled':
      case 'expired':
        return 'inert';
      default:
        return '';
    }
  });

  /** Only on open trades. On a closed one the bar would be a frozen snapshot
   *  of a position that no longer exists. */
  protected readonly progress = computed(() =>
    this.status().toLowerCase() === 'open'
      ? slToTpProgress(this.current(), this.stop(), this.target())
      : null,
  );

  protected readonly fillClass = computed(() => {
    const current = this.current();
    const entry = this.entry();
    if (current === null || entry === null) return '';
    if (current > entry) return 'pos';
    if (current < entry) return 'neg';
    return '';
  });
}
