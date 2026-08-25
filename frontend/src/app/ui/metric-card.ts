import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** How a value should be coloured. `pnl` is the ONLY one that may go green
 *  or red -- those two colours mean P&L direction and nothing else. */
export type MetricTone = 'plain' | 'pnl' | 'caution';

/**
 * One large number with a label. The Dashboard's primary tier.
 *
 * Hierarchy comes from size rather than from culling (design system
 * Decision 2): nine equal cards is what made the old dashboard unreadable,
 * so three of these carry the daily numbers and six compact chips carry the
 * rest.
 */
@Component({
  selector: 'sb-metric-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="card">
      <span class="label">{{ label() }}</span>
      <span class="value num" [class]="valueClass()">
        {{ display() }}
      </span>
      @if (sub(); as subtext) {
        <span class="sub num">{{ subtext }}</span>
      }
    </div>
  `,
  styles: `
    /* A custom element has no display of its own by default (the browser
       treats it as inline), so a row that stretches this host to match its
       tallest sibling (flex/grid's own align-items: stretch) would stretch
       an invisible box while .card -- which carries the actual border and
       background -- stayed sized to its own content. block + height: 100%
       is what makes the visible card, not just the host, fill that
       stretched row height. */
    :host { display: block; height: 100%; }
    .card {
      display: flex;
      flex-direction: column;
      gap: var(--space-6);
      padding: var(--space-14) var(--space-20);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      height: 100%;
      box-sizing: border-box;
    }
    .label {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .value {
      /* v54 D1: the register class on an ancestor panel/workspace sets
         --register-figure to the rung its density picked; the fallback is
         what this card rendered before the registers existed, so a card with
         no register ancestor (not yet migrated, or deliberately opted out)
         is unchanged. */
      font-size: var(--register-figure, var(--text-metric));
      font-weight: 700;
      line-height: 1.1;
      /* No transition on the value: with push, numbers change whenever the
         bot moves, and an animated number is unreadable at a glance --
         which is the only way this card is ever read. */
    }
    .sub {
      color: var(--text-muted);
      font-size: var(--register-label, var(--text-table));
    }
    .pos { color: var(--pos); }
    .neg { color: var(--neg); }
    .warn { color: var(--warn); }
    .absent { color: var(--text-faint); }
  `,
})
export class MetricCard {
  readonly label = input.required<string>();
  readonly value = input.required<number | null>();
  readonly tone = input<MetricTone>('plain');
  /** Rendered after the number: '%', ' €', and so on. Money units come from
   *  `ConnectionStore.currency()` — never a literal, see its note. */
  readonly unit = input('');
  readonly sub = input<string | null>(null);
  readonly decimals = input(2);

  /** An em dash, not "0" or "—%": a metric with no value yet is not a
   *  metric that is zero, and on a balance those differ by everything. */
  protected readonly display = computed(() => {
    const value = this.value();
    if (value === null) return '—';
    return `${value.toFixed(this.decimals())}${this.unit()}`;
  });

  protected readonly valueClass = computed(() => {
    const value = this.value();
    if (value === null) return 'absent';
    if (this.tone() === 'caution') return 'warn';
    if (this.tone() !== 'pnl') return '';
    // Exactly zero is neither a profit nor a loss, and colouring it green
    // would overstate a flat position.
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  });
}
