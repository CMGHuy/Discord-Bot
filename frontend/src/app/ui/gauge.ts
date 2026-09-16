import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * A half-dial for one bounded ratio — spec v85 D36.
 *
 * Used for portfolio heat utilisation, whose API value is intentionally not
 * clamped (`admin/api_v1/risk.py`: "Utilisation is NOT clamped … 130% is
 * exactly the situation the reader must see"). This component honours that:
 * the needle stops at the end of the arc because it has nowhere else to go,
 * but the readout always prints the real number and the whole gauge takes an
 * `over` treatment that is stated in words as well as in colour.
 *
 * Hand-authored SVG. The plan forbids a charting dependency, and a 180° arc is
 * two `path` elements.
 */
@Component({
  selector: 'sb-gauge',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="gauge"
      [class.over]="over()"
      role="meter"
      [attr.aria-label]="label()"
      [attr.aria-valuenow]="value()"
      [attr.aria-valuemin]="0"
      [attr.aria-valuemax]="max()"
    >
      <svg viewBox="0 0 120 66" width="100%" aria-hidden="true">
        <path class="track" d="M10 60 A50 50 0 0 1 110 60" fill="none" stroke-width="10" />
        @if (value() !== null) {
          <path
            class="needle"
            [attr.data-angle]="angle()"
            [attr.d]="needlePath()"
            fill="none"
            stroke-width="10"
            stroke-linecap="round"
          />
        }
      </svg>
      <div class="readout">
        @if (value() === null) {
          —
        } @else {
          {{ value() }}%@if (over()) {<span class="flag"> · over limit</span>}
        }
      </div>
      <div class="label">{{ label() }}</div>
      @if (caption()) { <div class="caption">{{ caption() }}</div> }
    </div>
  `,
  styles: `
    .gauge { display: flex; flex-direction: column; align-items: center; gap: 2px; }
    .track { stroke: var(--border); }
    .needle { stroke: var(--accent); }
    .over .needle { stroke: var(--neg); }
    .readout {
      font-size: var(--text-metric);
      font-variant-numeric: tabular-nums;
      color: var(--text);
    }
    .over .readout { color: var(--neg); }
    .flag { font-size: var(--text-micro); font-style: italic; }
    .label {
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-faint);
    }
    .caption { font-size: var(--text-micro); color: var(--text-faint); text-align: center; }
  `,
})
export class Gauge {
  readonly value = input.required<number | null>();
  readonly max = input<number>(100);
  readonly label = input.required<string>();
  readonly caption = input<string | undefined>(undefined);

  protected readonly over = computed(() => {
    const v = this.value();
    return v !== null && v > this.max();
  });

  /** Degrees along the 180° arc. Clamped — the arc ends; the number does not. */
  protected readonly angle = computed(() => {
    const v = this.value();
    if (v === null) return 0;
    const ratio = Math.min(Math.max(v / this.max(), 0), 1);
    return ratio * 180;
  });

  /** The filled portion of the arc, drawn from the left end to the needle. */
  protected readonly needlePath = computed(() => {
    const rad = (Math.PI * (180 - this.angle())) / 180;
    const x = 60 + 50 * Math.cos(rad);
    const y = 60 - 50 * Math.sin(rad);
    const large = this.angle() > 180 ? 1 : 0;
    return `M10 60 A50 50 0 ${large} 1 ${x.toFixed(2)} ${y.toFixed(2)}`;
  });
}
