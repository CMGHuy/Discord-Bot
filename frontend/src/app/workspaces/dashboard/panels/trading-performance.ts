import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { KPI_HELP, PANEL_HELP } from './panel-help';

import { ViewportService } from '../../../ui/breakpoints';
import { Button } from '../../../ui/button';
import { Select, SelectOption } from '../../../ui/form-controls';
import { ControlRow, Panel } from '../../../ui/layout';
import { MetricCard } from '../../../ui/metric-card';
import { Spinner } from '../../../ui/spinner';
import { PortfolioValue } from './portfolio-value';
import { amount, pct } from '../../../ui/format';
import {
  ChartTarget,
  TimeWindow,
  SCOPE_PRESETS,
  ScopePreset,
  ScopeSelection,
  breakevenPairTone,
  rangeChipLabel,
  showsNowLabel,
  signTone,
} from './equity-range.model';

/** The dropdown's value for a hand-picked range: never a preset, never persisted. */
const RANGE_OPTION = 'Range';

/**
 * The seven figures — v85 D9 (the Risk used card was dropped 2026-10-23).
 *
 * Win rate, expectancy and payoff ratio travel together on purpose: win rate
 * and payoff ratio decompose expectancy, so read as a triple they say why the
 * expectancy is what it is rather than only what it is.
 *
 * The scope control sits in this panel's header (D10) and is page-wide: it
 * also re-scopes the Closed tab below. v181 §1 widens it from Today / All
 * days to the presets 1D · 5D · 1M · 3M · 6M · YTD · 1Y · All, plus a Range
 * chip that a hand pan or zoom of the chart turns on. Below 640px the same
 * entries are one native dropdown.
 *
 * Portfolio Value merged in as this panel's first section rather than a
 * sibling card: both describe "how am I doing", and two bordered boxes side
 * by side that never disagree in that context read as one idea sliced in two.
 */
@Component({
  selector: 'sb-trading-performance',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, MetricCard, ControlRow, Button, PortfolioValue, Select, Spinner],
  template: `
    <sb-panel heading="Trading performance" [description]="about">
      <div panel-actions class="scope">
        @if (phone()) {
          <sb-select class="preset-select" ariaLabel="Date scope"
                     [options]="presetOptions()" [value]="selectValue()"
                     (valueChange)="onSelect($event)" />
        } @else {
          <sb-control-row role="group" aria-label="Date scope">
            @for (option of presets; track option) {
              <button
                sb-button
                type="button"
                [attr.data-preset]="option"
                [variant]="activePreset() === option ? 'secondary' : 'ghost'"
                [attr.aria-pressed]="activePreset() === option"
                (click)="presetChange.emit(option)"
              >{{ option }}</button>
            }
            @if (rangeLabel(); as label) {
              <span class="range-chip" aria-current="true"><span class="range-word">Range</span> {{ label }}</span>
            }
          </sb-control-row>
        }
      </div>

      @if (stale()) {
        <p class="stale-hint" role="status">Couldn't refresh for this range · showing the last figures</p>
      }

      <div class="combined">
        <sb-portfolio-value
          class="portfolio"
          [chartTarget]="chartTarget()"
          (chartRangeChange)="chartRangeChange.emit($event)"
          (viewReset)="viewReset.emit()"
          [balance]="balance()"
          [changePct]="changePct()"
          [points]="points()"
          [currency]="currency()"
        />

        <div class="grid" [class.stale]="stale()">
          <sb-metric-card label="Open P&L" [description]="help.openPnl" [value]="openPnlPct()" [tint]="openPnlTone()" unit="%" [sub]="openPnlSub()" [subPnl]="openPnlAmount()" />
          <sb-metric-card label="Win rate" [description]="help.winRate" [value]="winRate()" [tint]="winPairTone()" unit="%" [decimals]="1" [sub]="sample(winRateN())" [loading]="loading()" />
          <sb-metric-card label="Expectancy" [description]="help.expectancy" [value]="expectancyR()" [tint]="expectancyTone()" unit="R" [sub]="sample(expectancyN())" [loading]="loading()" />
          <sb-metric-card label="Payoff ratio" [description]="help.payoffRatio" [value]="payoffRatio()" [tint]="payoffTone()" [decimals]="2" [sub]="noCloseHint(payoffRatio())" [loading]="loading()" />
          <sb-metric-card [label]="realizedLabel()" [description]="help.realized" [value]="realizedAmount()" [tint]="realizedTone()"
                          [unit]="currencyUnit()" [sub]="noCloseHint(realizedAmount())" [loading]="loading()" />
          <sb-metric-card label="Open trades" [description]="help.openTrades" [value]="openTrades()" [decimals]="0" [sub]="openTradesSub()" />
          <sb-metric-card label="Avg confidence" [description]="help.avgConfidence" [value]="avgConfidence()" [decimals]="1" [loading]="loading()" />
        </div>
      </div>

      <!-- Phone (v172 section 5, reversing v85's hide-on-phone): the portfolio
           block above (figure, day change, equity candles) now shows, the
           eight-card grid does not. This summary carries the figures the grid
           would; its Portfolio and Today rows repeat the figure above on
           purpose, so the summary reads complete on its own. -->
      <div class="mobile-summary" [class.stale]="stale()" aria-label="Portfolio summary">
        <div><span>Portfolio</span><strong>{{ fmtAmount(balance()) }}</strong></div>
        <div [attr.data-tone]="tinted(changeTone())"><span>Today</span><strong>{{ fmtPct(changePct()) }}</strong></div>
        <div><span>Open{{ nowSuffix() }}</span><strong>{{ openTrades() }}</strong></div>
        <div [attr.data-tone]="tinted(winPairTone())" [class.busy]="loading()"><span>Win rate @if (loading()) { <sb-spinner label="Updating" /> }</span><strong>{{ fmtFigure(winRate(), '%', 1) }}</strong></div>
        <div [attr.data-tone]="tinted(expectancyTone())" [class.busy]="loading()"><span>Expectancy @if (loading()) { <sb-spinner label="Updating" /> }</span><strong>{{ fmtFigure(expectancyR(), 'R', 2) }}</strong></div>
        <div [attr.data-tone]="tinted(payoffTone())" [class.busy]="loading()"><span>Payoff @if (loading()) { <sb-spinner label="Updating" /> }</span><strong>{{ fmtFigure(payoffRatio(), '', 2) }}</strong></div>
        <div [attr.data-tone]="tinted(realizedTone())" [class.busy]="loading()"><span>{{ realizedLabel() }} @if (loading()) { <sb-spinner label="Updating" /> }</span><strong>{{ fmtFigure(realizedAmount(), currencyUnit(), 2) }}</strong></div>
      </div>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    /* One column at every width (v172): the equity candles need the panel's
       full width, so the portfolio block (figure, day change, candles) is a
       row of its own above the KPI grid instead of a ~240px side column that
       would leave the chart and its readout unreadable. */
    .combined {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: var(--space-14);
      align-items: start;
    }
    .portfolio { min-width: 0; width: 100%; }
    .scope { min-width: 0; max-width: 100%; }
    /* v181 §1: the phone dropdown is a 44px target; --control-h is 28px on a
       fine pointer and the select's own height reads it. */
    .preset-select { display: block; --control-h: 44px; }
    .range-chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      border: 1px solid var(--border-strong);
      border-radius: var(--control-radius);
      background: var(--surface-raised);
      color: var(--text);
      font-size: var(--text-chip);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .range-word { color: var(--text-secondary); }
    /* v181 §9: a failed range refetch keeps the last figures, dimmed. */
    .grid.stale, .mobile-summary.stale { opacity: 0.55; }
    .stale-hint { margin: 0 0 var(--space-10); font-size: var(--text-chip); color: var(--warn); }
    .mobile-summary { display: none; }
    /* A refetch in flight: the last figure stays, dimmed, beside its ring. */
    .mobile-summary .busy strong { opacity: 0.45; }
    .mobile-summary span { display: inline-flex; align-items: center; gap: var(--space-6); }
    /* A fixed 4 columns, not auto-fit: seven cards read as a row of four and a
       row of three (the last widened to fill), never an uneven 5+2 or 6+1
       split that auto-fit would produce at an in-between width. minmax with two lengths (not a bare 1fr) keeps
       this grid's own width computable when the ancestor asks for its
       content size (.combined's "auto" track above, and -- separately --
       any container that ends up shrink-to-fit sized), which a 1fr track
       cannot give under those conditions. The tracks stretch (1fr max), so the
       cards span the panel and share the chart's left and right edges. */
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 1fr));
      gap: var(--space-14);
    }
    /* Seven cards: the last one takes the rest of its row (two of four, or
       the whole two-up row on a tablet), so no hole is left beside it. */
    .grid > :last-child:nth-child(4n + 3) { grid-column: span 2; }
    /* The tablet band -- v95 A5.
       Between sm and md the 4-up KPI grid's 560px floor and the portfolio
       block cannot both fit: measured at 768px the portfolio column
       collapsed to ~40px and '997,291.88 EUR' rendered as four fragments.
       Two KPI columns and a full-width portfolio row is the narrowest
       arrangement where both are readable. Above md the original four-up
       returns untouched. Placed after the base rules deliberately -- a media
       query adds no specificity, so a base .grid declared below it would
       win. */
    @media (max-width: 1023px) {
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 639px) {
      .grid { display: none; }
      .combined { margin-bottom: var(--space-10); }
      .mobile-summary {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: var(--space-8);
      }
      .mobile-summary > div:last-child:nth-child(odd) { grid-column: 1 / -1; }
      .mobile-summary div { display: flex; justify-content: space-between; gap: var(--space-8); padding: var(--space-6); border-bottom: 1px solid var(--border); font-size: var(--text-table); }
      .mobile-summary span { color: var(--text-secondary); }
      .mobile-summary strong { font-family: var(--font-mono); }
      .mobile-summary [data-tone='pos'] { background: var(--pos-soft); }
      .mobile-summary [data-tone='neg'] { background: var(--neg-soft); }
      .mobile-summary [data-tone='pos'] strong { color: var(--pos); }
      .mobile-summary [data-tone='neg'] strong { color: var(--neg); }
      .mobile-summary [data-tone='warn'] strong { color: var(--warn); }
    }
  `,
})
export class TradingPerformance {
  protected readonly help = KPI_HELP;
  protected readonly about = PANEL_HELP.tradingPerformance;
  readonly balance = input<number | null>(null);
  readonly changePct = input<number | null>(null);
  readonly points = input<readonly number[]>([]);
  readonly openPnlPct = input<number | null>(null);
  /** Money equivalent of the open P&L %, shown beneath it. */
  readonly openPnlAmount = input<number | null>(null);
  readonly winRate = input<number | null>(null);
  readonly expectancyR = input<number | null>(null);
  readonly winRateN = input<number | null>(null);
  readonly expectancyN = input<number | null>(null);
  protected sample(n: number | null): string | null { return n === null ? null : `N=${n}`; }
  readonly avgConfidence = input<number | null>(null);
  readonly realizedAmount = input<number | null>(null);
  readonly realizedLabel = input('Realised today');
  readonly openTrades = input<number>(0);
  /** Mean winning R over the magnitude of mean losing R. Null, never 0, when
   *  either side has no outcomes yet — see payoff_ratio_from_rs. */
  readonly payoffRatio = input<number | null>(null);
  readonly currency = input('€');
  readonly selection = input<ScopeSelection>({ kind: 'preset', preset: '1D' });
  /** v181 §9: the last range refetch failed; the figures are the previous ones. */
  readonly stale = input(false);
  /** A scoped refetch is in flight: the window-scoped figures show a ring. */
  readonly loading = input(false);
  readonly presetChange = output<ScopePreset>();
  /** Pass the chart scope link through to PortfolioValue. */
  readonly chartTarget = input<ChartTarget | null>(null);
  readonly chartRangeChange = output<TimeWindow>();
  /** The chart's reset button was pressed: back to the scope's own window, ending now. */
  readonly viewReset = output<void>();

  /** Below 640px the presets are one native dropdown (v181 §1). */
  protected readonly phone = inject(ViewportService).isPhone;
  protected readonly presets = SCOPE_PRESETS;
  protected readonly activePreset = computed(() => {
    const selection = this.selection();
    return selection.kind === 'preset' ? selection.preset : null;
  });
  protected readonly rangeLabel = computed(() => {
    const selection = this.selection();
    return selection.kind === 'range' ? rangeChipLabel(selection.window) : null;
  });
  protected readonly presetOptions = computed<SelectOption[]>(() => {
    const options = SCOPE_PRESETS.map((value) => ({ value, label: value }));
    const label = this.rangeLabel();
    return label === null ? options : [...options, { value: RANGE_OPTION, label: `Range · ${label}` }];
  });
  protected readonly selectValue = computed(() => this.activePreset() ?? RANGE_OPTION);
  /** Only a preset leaves the dropdown; picking the Range entry changes nothing. */
  protected onSelect(value: string): void {
    const picked = SCOPE_PRESETS.find((option) => option === value);
    if (picked) this.presetChange.emit(picked);
  }

  /** v181 §5: open P&L and open trades are always "now"; outside
   *  1D a tinted card must not read as that window's exposure. */
  protected readonly nowLabel = computed(() => showsNowLabel(this.selection()));
  protected readonly nowSuffix = computed(() => (this.nowLabel() ? ' · now' : ''));
  protected readonly openTradesSub = computed(() => (this.nowLabel() ? 'now' : null));
  private withNow(text: string | null): string | null {
    if (!this.nowLabel()) return text;
    return text === null ? 'now' : `now · ${text}`;
  }

  protected readonly currencyUnit = computed(() => ` ${this.currency()}`);
  protected fmtAmount = (value: number | null) => amount(value, this.currency());
  protected fmtPct = pct;
  /** Same rule as MetricCard: no value is an em dash, never a zero. */
  protected fmtFigure(value: number | null, unit: string, decimals: number): string {
    return value === null ? '—' : `${value.toFixed(decimals)}${unit}`;
  }
  /** An em dash alone reads as broken: say why, in the scope's own words.
   *  All has no hint: nothing closed at all is its own answer. */
  protected noCloseHint(value: number | null): string | null {
    if (value !== null) return null;
    const active = this.activePreset();
    if (active === '1D') return 'none closed today';
    return active === 'All' ? null : 'none closed in range';
  }
  protected readonly openPnlSub = computed(() => {
    const value = this.openPnlAmount();
    return this.withNow(value === null ? null : amount(value, this.currency()));
  });
  protected readonly changeTone = computed(() => signTone(this.changePct()));
  protected readonly openPnlTone = computed(() => signTone(this.openPnlPct()));
  protected readonly expectancyTone = computed(() => signTone(this.expectancyR()));
  protected readonly realizedTone = computed(() => signTone(this.realizedAmount()));
  /** v181 §5: win rate and payoff are judged as a pair against break-even
   *  (100 / (1 + payoff)), never alone; neutral under 5 closes in scope. */
  protected readonly winPairTone = computed(() =>
    breakevenPairTone(this.winRate(), this.payoffRatio(), this.winRateN()));
  protected readonly payoffTone = computed(() => this.winPairTone());
  /** A summary row carries a tone attribute only when it is judged. */
  protected tinted(tone: string): string | null {
    return tone === 'neutral' ? null : tone;
  }
}
