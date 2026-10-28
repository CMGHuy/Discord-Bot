import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { PreferencesStore } from '../stores/preferences.store';
import { Hint } from './hint';
import { Sparkline } from './sparkline';
import { CountUp } from './motion/count-up';
import { formatFigureText, parseFigureText } from './motion/figure-text';

/**
 * The smallest sample a derived metric may be read from without a warning.
 *
 * 30 is not a law of statistics; it is the point below which this book's
 * per-strategy and per-horizon slices have historically flipped sign on one
 * more trade. R11-04 makes it a setting — until then it is a constant, so the
 * primitive can ship in wave 1 ahead of the control that tunes it.
 */
export const MIN_SAMPLE_N = 30;

export type StatTone = 'neutral' | 'pos' | 'neg';

/**
 * v194 B8 -- how every performance figure states its basis (spec hint copy
 * rule): paper fills, no costs modelled, before tax. One string, so the Risk
 * and Analytics tiles cannot drift apart.
 */
export const PERFORMANCE_CAVEAT =
  'Paper trades (simulated fills), gross of commissions and slippage, pre-tax.';

/**
 * One metric, its label, and its sample size — spec v85 D23.
 *
 * The sample size is not decoration and not a tooltip. A win rate of 68% over
 * seven trades and one over four hundred are different claims, and a tile that
 * renders them identically is the correctness bug this component exists to
 * prevent. Below `MIN_SAMPLE_N` the tile de-emphasises itself and says how many
 * more closed trades it needs — the figure is still shown, because hiding it
 * would stop you watching a young strategy develop.
 *
 * `value` is pre-formatted by the caller. This component never formats a
 * number: the pages that use it disagree about units (R, %, currency) and a
 * formatter here would have to learn all of them.
 */
@Component({
  selector: 'sb-stat-tile',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hint, Sparkline, CountUp],
  template: `
    <div class="tile sb-lift" [class.thin]="thin()" [class]="tone()">
      <div class="label-row">
        <div class="label sb-label">{{ label() }}</div>
        @if (about(); as text) { <sb-hint [text]="text" [label]="'About ' + label()" /> }
      </div>
      <div class="value" [sbCountUp]="countValue()" [countFormat]="countFormat()"
           [countKey]="'stat:' + label()" [countAbsent]="value() ?? '—'"></div>
      @if (secondary()) { <div class="secondary num">{{ secondary() }}</div> }
      @if (sample() !== null) {
        <div class="sample">
          N={{ sample() }}@if (thin()) {<span class="flag"> · thin sample, {{ shortfall() }} more needed</span>}
        </div>
      }
      @if (hint()) {
        <div class="hint">{{ hint() }}</div>
      }
      @if (trend(); as points) { <sb-sparkline [points]="points" [label]="label() + ' trend'" /> }
    </div>
  `,
  styles: `
    /* v179 §3.3 -- the one tile, everywhere: label, value, secondary, N=,
       hint, stacked and left-aligned. The host is a block that fills its
       grid cell: a custom element is inline by default, and an inline host
       never receives the row's stretched height, which is why two tiles in
       one row used to differ in height. min-width: 0 and overflow-wrap let
       a long label wrap instead of widening its grid track. No page
       restyles the inside of a tile -- workspace-consistency.spec.ts fails
       a ::ng-deep into sb-stat-tile. */
    :host {
      display: block;
      height: 100%;
      min-width: 0;
      /* v186 D3 -- inside an sb-stat-strip the strip sets --figure-rule: 1px
         and the tile draws a start-edge hairline (left, top) on its host, the
         sb-figure / sb-figure-strip mechanism; the strip clips the first
         row's and first column's. Outside a strip the width is 0px: no rule.
         border-box keeps the rule inside the grid cell. */
      box-sizing: border-box;
      border-left: var(--figure-rule, 0px) solid var(--border);
      border-top: var(--figure-rule, 0px) solid var(--border);
    }
    .tile {
      display: flex;
      flex-direction: column;
      gap: 2px;
      height: 100%;
      box-sizing: border-box;
      min-width: 0;
      padding: var(--space-14);
      text-align: start;
      /* v186 D3 -- a strip sets these to transparent / 0 / 0; the fallbacks
         are the tile's own surface, so a tile outside a strip is unchanged. */
      background: var(--tile-bg, var(--surface));
      border: var(--tile-border, 1px solid var(--border));
      border-radius: var(--tile-radius, var(--panel-radius));
    }
    /* v186 D3 -- typography is the global .sb-label on the element (mono
       caps, --text-muted): the one field-label style. Only wrapping is ours. */
    .label { overflow-wrap: anywhere; min-width: 0; }
    /* v194 B8 -- the definition hint sits on the label's line, never under
       the value: the label wraps first, the trigger keeps its size. */
    .label-row { display: flex; align-items: center; gap: var(--space-6, 6px); min-width: 0; }
    .label-row sb-hint { flex: none; }
    .value {
      font-family: var(--font-figure);
      font-weight: var(--figure-weight);
      letter-spacing: var(--figure-tracking);
      font-variant-numeric: tabular-nums;
      font-size: var(--text-metric);
      color: var(--text);
      overflow-wrap: anywhere;
    }
    .pos .value { color: var(--pos); }
    .neg .value { color: var(--neg); }
    .sample,
    .secondary,
    .hint {
      font-size: var(--text-micro);
      font-variant-numeric: tabular-nums;
      color: var(--text-muted);
      overflow-wrap: anywhere;
    }
    /* Figures in the numeric face; the hint is prose and stays in the UI font. */
    .sample, .secondary { font-family: var(--font-num); }
    .secondary { color: var(--text-secondary); }
    /* The second cue. Opacity alone would be a colour-only signal, which the
       plan forbids; the .flag span puts the same fact in words. */
    .thin .value { opacity: 0.62; }
    .thin .flag { font-style: italic; }
  `,
})
export class StatTile {
  private readonly preferences = inject(PreferencesStore);
  readonly label = input.required<string>();
  readonly value = input.required<string | null>();
  readonly sample = input<number | null>(null);
  readonly tone = input<StatTone>('neutral');
  readonly hint = input<string | undefined>(undefined);
  /** v194 B8 -- the tile's definition, population and caveat, behind an
   *  `sb-hint` beside the label. `hint` stays the always-visible line. */
  readonly about = input<string | undefined>(undefined);
  readonly secondary = input<string | null>(null);
  readonly trend = input<readonly number[] | null>(null);

  /**
   * v168 count-up. `value` arrives pre-formatted (this component never formats
   * a number, see the class comment), so the number is read back out of the
   * text and the text rebuilt around each counted value. Text with no number
   * in it has nothing to count and shows as it is, through `countAbsent`.
   */
  private readonly parsed = computed(() => parseFigureText(this.value()));
  protected readonly countValue = computed(() => this.parsed()?.value ?? null);
  protected readonly countFormat = computed(() => {
    const parts = this.parsed();
    return (value: number) => (parts ? formatFigureText(parts, value) : String(value));
  });

  protected readonly thin = computed(() => {
    const n = this.sample();
    return n !== null && n < this.minimumSample();
  });

  private readonly minimumSample = computed(() => {
    const value = this.preferences.values()['minSampleN'];
    return typeof value === 'number' && Number.isInteger(value) && value > 0
      ? value
      : MIN_SAMPLE_N;
  });

  /** v194 A3: how many more closed trades before the figure is worth
   *  reading -- printed inline beside "thin sample" (it used to hide in a
   *  native title a phone never shows). */
  protected readonly shortfall = computed(() => {
    const n = this.sample();
    return n === null ? 0 : Math.max(0, this.minimumSample() - n);
  });
}
