import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { KPI_HELP, PANEL_HELP } from './panel-help';

import { ViewportService } from '../../../ui/breakpoints';
import { Button } from '../../../ui/button';
import { Select, SelectOption } from '../../../ui/form-controls';
import { ControlRow, Panel } from '../../../ui/layout';
import { MetricCard } from '../../../ui/metric-card';
import { Spinner } from '../../../ui/spinner';
import { StatStrip } from '../../../ui/stat-strip';
import { PortfolioValue } from './portfolio-value';
import { MINUS, amount, pct } from '../../../ui/format';
import { Realized } from '../../../stores/dashboard.store';
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

/** The Realised today sub-line when today's fetch failed and nothing
 *  earlier landed: an em dash alone would read as "nothing closed". */
const TODAY_UNAVAILABLE = "couldn't load today's figures";

/** The dropdown's value for a hand-picked range: never a preset, never persisted. */
const RANGE_OPTION = 'Range';

/** 1D is the page's default mode, so it reads as the word, not the code. */
export function presetLabel(preset: ScopePreset): string {
  return preset === '1D' ? 'Today' : preset;
}

/**
 * The KPI cards — v85 D9 (the Risk used card was dropped 2026-10-23).
 *
 * Two modes. **Today** (1D, the default on every visit) shows today's
 * figures: seven cards. **Period** (any wider preset, or a Range the chart
 * was dragged to) re-scopes win rate, expectancy, payoff and confidence to
 * that window and adds a Realised in period card: eight. Realised today is
 * today's in both modes -- it replaced the separate Realised P&L panel.
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
  imports: [Panel, MetricCard, ControlRow, Button, PortfolioValue, Select, Spinner, StatStrip],
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
              >{{ label(option) }}</button>
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

        <sb-stat-strip class="grid" [class.stale]="stale()" [cols]="4" [colsMd]="2" [fillLast]="true">
          <sb-metric-card label="Open P&L" [description]="help.openPnl" [value]="openPnlPct()" [tint]="openPnlTone()" unit="%" [sub]="openPnlSub()" [subPnl]="openPnlAmount()" />
          <sb-metric-card label="Win rate" [description]="help.winRate" [value]="winRate()" [tint]="winPairTone()" unit="%" [decimals]="1" [sub]="sample(winRateN())" [loading]="loading()" />
          <sb-metric-card label="Expectancy" [description]="help.expectancy" [value]="expectancyR()" [tint]="expectancyTone()" unit="R" [sub]="sample(expectancyN())" [loading]="loading()" />
          <sb-metric-card label="Payoff ratio" [description]="help.payoffRatio" [value]="payoffRatio()" [tint]="payoffTone()" [decimals]="2" [sub]="noCloseHint(payoffRatio())" [loading]="loading()" />
          <sb-metric-card label="Realised today" [description]="help.realizedToday" [value]="todayAmount()" [tint]="todayTone()"
                          [unit]="currencyUnit()" [sub]="todaySub()" [loading]="todayBusy()" />
          @if (inPeriod()) {
            <sb-metric-card label="Realised in period" [description]="help.realized" [value]="realizedAmount()" [tint]="realizedTone()"
                            [unit]="currencyUnit()" [sub]="periodSub()" [loading]="loading()" />
          }
          <sb-metric-card label="Open trades" [description]="help.openTrades" [value]="openTrades()" [decimals]="0" [sub]="openTradesSub()" />
          <sb-metric-card label="Avg confidence" [description]="help.avgConfidence" [value]="avgConfidence()" [decimals]="1" [loading]="loading()" />
        </sb-stat-strip>
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
        <div [attr.data-tone]="tinted(todayTone())" [class.busy]="todayBusy()"><span>Realised today @if (todayBusy()) { <sb-spinner label="Updating" /> }</span><strong>{{ todayUnavailable() ? todayUnavailableText : fmtFigure(todayAmount(), currencyUnit(), 2) }}</strong></div>
        @if (inPeriod()) {
          <div [attr.data-tone]="tinted(realizedTone())" [class.busy]="loading()"><span>Realised in period @if (loading()) { <sb-spinner label="Updating" /> }</span><strong>{{ fmtFigure(realizedAmount(), currencyUnit(), 2) }}</strong></div>
        }
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
    /* v186 D3: the KPI cards sit in one sb-stat-strip, ruled by hairlines
       instead of framed boxes. The strip owns the columns: 4 from md, 2 in
       the tablet band (v95 A5: the 4-up floor starved the portfolio block at
       768px) and 2 below sm, where this panel hides it for .mobile-summary.
       Fixed counts, not auto-fit, so the cards never split unevenly at an
       in-between width. The class stays .grid so the stale dim and the phone
       hide below keep applying to the strip host. */
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
  /** The period's realised amount; shown only in Period mode. */
  readonly realizedAmount = input<number | null>(null);
  /** Today's realised block, in both modes. Null until a response lands. */
  readonly todayRealized = input<Realized | null>(null);
  /** The today-only fetch is in flight (Period mode; under 1D the scoped
   *  fetch is today's, so `loading` covers it). */
  readonly todayLoading = input(false);
  /** Today's fetch failed (`DashboardStore.todayError`); the card says so. */
  readonly todayError = input<string | null>(null);
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
    const options = SCOPE_PRESETS.map((value) => ({ value, label: presetLabel(value) }));
    const label = this.rangeLabel();
    return label === null ? options : [...options, { value: RANGE_OPTION, label: `Range · ${label}` }];
  });
  protected readonly selectValue = computed(() => this.activePreset() ?? RANGE_OPTION);
  protected readonly label = presetLabel;
  /** Only a preset leaves the dropdown; picking the Range entry changes nothing. */
  protected onSelect(value: string): void {
    const picked = SCOPE_PRESETS.find((option) => option === value);
    if (picked) this.presetChange.emit(picked);
  }

  /** v181 §5: open P&L and open trades are always "now"; outside
   *  1D a tinted card must not read as that window's exposure. */
  protected readonly nowLabel = computed(() => showsNowLabel(this.selection()));
  /** Period mode: anything but 1D. The same test as the "now" labels. */
  protected readonly inPeriod = this.nowLabel;
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
    if (value === null) return '—';
    // v195 §1.1: a negative ExpR carries a true minus; positives unchanged.
    return `${value < 0 ? MINUS : ''}${Math.abs(value).toFixed(decimals)}${unit}`;
  }
  /** An em dash alone reads as broken: say why, in the scope's own words.
   *  All has no hint: nothing closed at all is its own answer. */
  protected noCloseHint(value: number | null): string | null {
    if (value !== null) return null;
    const active = this.activePreset();
    if (active === '1D') return 'none closed today';
    return active === 'All' ? null : 'none closed in range';
  }
  protected readonly todayAmount = computed(() => this.todayRealized()?.amount ?? null);
  protected readonly todayTone = computed(() => signTone(this.todayAmount()));
  protected readonly todayBusy = computed(() => (this.inPeriod() ? this.todayLoading() : this.loading()));
  /** "+0.40% · 3 closed · 2W 1L"; the % is left out when the server has none. */
  /** The phone summary has no sub-line: it swaps the dash for the failure text. */
  protected readonly todayUnavailableText = TODAY_UNAVAILABLE;
  protected readonly todayUnavailable = computed(() => this.todayAmount() === null && this.todayError() !== null);

  protected readonly todaySub = computed(() => {
    const today = this.todayRealized();
    if (today === null) return this.todayError() === null ? null : TODAY_UNAVAILABLE;
    if (today.n === 0) return 'none closed today';
    const counts = `${today.n} closed · ${today.wins}W ${today.losses}L`;
    return today.pct === null ? counts : `${pct(today.pct)} · ${counts}`;
  });
  /** Which window the period card covers, with the no-close hint after it. */
  protected readonly periodSub = computed(() => {
    const selection = this.selection();
    const window = selection.kind === 'range'
      ? rangeChipLabel(selection.window)
      : (selection.preset === 'All' ? 'All days' : selection.preset);
    const hint = this.noCloseHint(this.realizedAmount());
    return hint === null ? window : `${window} · ${hint}`;
  });
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
