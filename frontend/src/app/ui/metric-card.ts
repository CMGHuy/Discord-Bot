import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Hint } from './hint';
import { CountUp } from './motion/count-up';
import { Spinner } from './spinner';

/** Legacy figure colouring, used when no judged tint is supplied. */
export type MetricTone = 'plain' | 'pnl' | 'caution';

/** v181 §5: how a figure is judged — the same union as `PnlTone` in
 *  `equity-range.model.ts` (ui/ does not import from workspaces/; the two
 *  are structurally one type). pos/neg tint the card, warn colours only. */
export type CardTint = 'pos' | 'neg' | 'warn' | 'neutral';

const TINT_CLASS: Record<CardTint, string> = { pos: 'pos', neg: 'neg', warn: 'warn', neutral: '' };

/** The v80 rule, used when no tint is given. */
function toneClass(tone: MetricTone, value: number): string {
  if (tone === 'caution') return 'warn';
  if (tone !== 'pnl') return '';
  // Exactly zero is neither a profit nor a loss, and colouring it green
  // would overstate a flat position.
  if (value > 0) return 'pos';
  if (value < 0) return 'neg';
  return '';
}


/**
 * Deprecated (v80 D4): use `sb-figure` inside an `sb-figure-strip`.
 *
 * One large number with a label. The Dashboard's primary tier.
 *
 * Hierarchy comes from size rather than from culling (design system
 * Decision 2): nine equal cards is what made the old dashboard unreadable,
 * so three of these carry the daily numbers and six compact chips carry the
 * rest.
 *
 * v195 Phase 2: the same KPI cell as sb-stat-tile (one gap, one padding),
 * and no fill. A good or bad figure is still marked on the host
 * (tint-pos / tint-neg) and coloured on the value; the colour and the sign
 * carry the valence, never a tinted block.
 */
@Component({
  selector: 'sb-metric-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CountUp, Spinner, Hint],
  host: {
    '[class.tint-pos]': "cardTint() === 'pos'",
    '[class.tint-neg]': "cardTint() === 'neg'",
    '[class.loading]': 'loading()',
    '[attr.aria-busy]': 'loading() || null',
  },

  template: `
    <div class="card">
      <span class="label-row">
        <span class="label sb-label">{{ label() }}</span>
        @if (description(); as about) {
          <sb-hint [text]="about" [label]="'About ' + label()" align="left" />
        }
      </span>
      @if (loading()) {
        <sb-spinner class="busy" label="Updating" />
      }
      <span class="value" [class]="valueClass()" [sbCountUp]="value()"
            [countFormat]="format()" [countKey]="'metric:' + label()"></span>
      @if (sub(); as subtext) {
        <span class="sub num" [class]="subClass()">{{ subtext }}</span>
      }
    </div>
  `,
  styles: `
    .label-row { display: flex; align-items: center; gap: var(--space-4); min-width: 0; }
    /* A custom element has no display of its own by default (the browser
       treats it as inline), so a row that stretches this host to match its
       tallest sibling (flex/grid's own align-items: stretch) would stretch
       an invisible box while .card -- which carries the actual border and
       background -- stayed sized to its own content. block + height: 100%
       is what makes the visible card, not just the host, fill that
       stretched row height. */
    :host {
      display: block;
      height: 100%;
      /* v186 D3 -- the strip hairline, as in sb-stat-tile: start edges only,
         0px outside a strip, inside the grid cell. */
      box-sizing: border-box;
      border-left: var(--figure-rule, 0px) solid var(--border);
      border-top: var(--figure-rule, 0px) solid var(--border);
    }
    .card {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: var(--space-4);
      padding: var(--space-10) var(--panel-pad);
      background: var(--tile-bg, var(--surface));
      border: var(--tile-border, 1px solid var(--border));
      border-radius: var(--tile-radius, var(--panel-radius));
      height: 100%;
      box-sizing: border-box;
    }
    .value {
      font-family: var(--font-figure);
      font-weight: var(--figure-weight);
      letter-spacing: var(--figure-tracking);
      font-variant-numeric: tabular-nums;
      /* v54 D1: the register class on an ancestor panel/workspace sets
         --register-figure to the rung its density picked; the fallback is
         what this card rendered before the registers existed, so a card with
         no register ancestor (not yet migrated, or deliberately opted out)
         is unchanged. v186 D4: Inter 600 like every display figure (was 700
         in the code face). */
      font-size: var(--register-figure, var(--text-metric));
      line-height: 1.1;
      /* v168: the number counts up once when the route is entered, and eases
         to a new value when a push changes it -- 900ms, scoped to this one
         number, and only under Motion = On (CountUp). It never re-counts on a
         refetch, so a glance still reads a settled number. */
    }
    .sub {
      color: var(--text-muted);
      font-size: var(--register-label, var(--text-table));
    }
    /* A refetch in flight: the last figure stays, dimmed, with the ring in the
       card's top-right corner (it has no layout of its own, so nothing moves). */
    .busy { position: absolute; top: var(--space-10); right: var(--panel-pad); }
    :host(.loading) .value, :host(.loading) .sub { opacity: 0.45; }
    .pos { color: var(--pos); }
    .neg { color: var(--neg); }
    .warn { color: var(--warn); }
    .absent { color: var(--text-muted); }
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
  /** When set, the sub line takes the P&L colour of this number's sign (same
   *  rule as the main value). Leave null for a plain muted sub line. */
  readonly subPnl = input<number | null>(null);
  /** The figure is being refetched: a ring appears in the card and the last
   *  value dims. Never hides the value (a failed refetch keeps it). */
  readonly loading = input(false);
  /** What the figure means, as a tooltip over the whole card. */
  readonly description = input<string | null>(null);

  /** The value's text for any number. `null` is CountUp's em dash, not "0"
   *  or "—%": a metric with no value yet is not a metric that is zero, and on
   *  a balance those differ by everything. */
  protected readonly format = computed(() => {
    const decimals = this.decimals();
    const unit = this.unit();
    return (value: number) => `${value.toFixed(decimals)}${unit}`;
  });

  protected readonly subClass = computed(() => {
    const value = this.subPnl();
    if (value === null) return '';
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  });

  /** v181 §5: the judged tone of the figure (see `CardTint`). Wins over
   *  `tone`; null keeps the v80 `tone` rule. */
  readonly tint = input<CardTint | null>(null);

  /** Only a present figure judged good or bad tints its card. */
  protected readonly cardTint = computed(() => {
    const tint = this.tint();
    return this.value() !== null && (tint === 'pos' || tint === 'neg') ? tint : null;
  });

  protected readonly valueClass = computed(() => {
    const value = this.value();
    if (value === null) return 'absent';
    const tint = this.tint();
    return tint !== null ? TINT_CLASS[tint] : toneClass(this.tone(), value);
  });
}
