import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { AnalyticsUnit, BookScope } from '../../api/models';
import { RANGE_PRESETS, presetRange } from '../../stores/analytics.store';
import { ConnectionStore } from '../../stores/connection.store';
import { ControlBar } from '../../ui/control-bar';
import { DateRange } from '../../ui/date-range';
import { Field } from '../../ui/field';
import { Select } from '../../ui/form-controls';
import { Freshness } from '../../ui/freshness';
import { Segmented } from '../../ui/segmented';

export const ACCOUNT_WIDE_NOTE = 'Equity is account-wide: ledger, strategy, horizon and direction filters do not apply.';

/**
 * One bar, every panel below it (spec v94 D2). It also REPORTS: the
 * closed-trade count the scope produced, when the figures were built, and
 * how many panels on this tab ignore it. A screen that hides how scoped its
 * data is has a correctness bug -- that is what this component exists to fix.
 *
 * It owns no state. Every control emits and the workspace decides; the bar
 * must not become a second copy of the truth about what is filtered.
 */
@Component({
  selector: 'sb-scope-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ControlBar, DateRange, Field, Select, Segmented, Freshness],
  template: `
    <sb-control-bar [activeCount]="activeCount()" (cleared)="cleared.emit()">
      <!-- One ng-container per slot: an @if with several roots inside a
           projection slot silently drops every node but the first
           (NG8011), and a filter that vanishes is the failure this bar
           exists to prevent.
           v246 §A2: each control sits in one sb-field, which draws the one
           caption and names the control; the bar lines the field bottoms
           up. S a short select, M a date or a longer option. -->
      <ng-container filters>
        @if (benchmark()) {
          <sb-field class="range-field" label="Range" size="auto" [fullRow]="true">
            <sb-date-range [from]="scope().from" [to]="scope().to" (changed)="scopeChange.emit($event)" />
          </sb-field>
        } @else if (!tuning()) {
          <sb-field label="Range" size="m">
            <sb-select [value]="preset()" [options]="presetOptions" (valueChange)="onPreset($event)" />
          </sb-field>
          @if (preset() === 'custom') {
            <!-- No caption: "Range" sits on the preset select just left of
                 it. The empty line keeps its bottom edge level with the
                 selects; on a phone it drops and the dates take a row. -->
            <sb-field class="range-field" size="auto" [fullRow]="true">
              <sb-date-range [from]="scope().from" [to]="scope().to"
                             (changed)="scopeChange.emit($event)" />
            </sb-field>
          }
          <sb-field label="Ledger" size="m">
            <sb-select [value]="scope().ledger" [options]="ledgerOptions"
                       (valueChange)="scopeChange.emit({ ledger: $any($event) })" />
          </sb-field>
          <sb-field label="Strategy" size="m">
            <sb-select placeholder="Any strategy" [value]="scope().strategy ?? ''"
                       [options]="options(strategies())" (valueChange)="scopeChange.emit({ strategy: $event || null })" />
          </sb-field>
          <sb-field label="Horizon" size="s">
            <sb-select placeholder="Any horizon" [value]="scope().horizon ?? ''"
                       [options]="options(horizons())" (valueChange)="scopeChange.emit({ horizon: $event || null })" />
          </sb-field>
          <sb-field label="Direction" size="s">
            <sb-select placeholder="Both" [value]="scope().direction ?? ''"
                       [options]="directionOptions" (valueChange)="scopeChange.emit({ direction: $event || null })" />
          </sb-field>
        }
      </ng-container>
      <!-- v179 §3.4: a box of its own, its items on one text line. v246 §A2:
           last baseline -- the Units field's first line is its caption, its
           last the buttons' text, where the population and freshness sit. -->
      <div ngProjectAs="[scope]" class="scope-line">
        @if (benchmark()) {
          <span class="account-wide" role="note">{{ accountWideNote }}</span>
        } @else {
        <sb-field label="Units" size="auto" [fullRow]="true">
          <sb-segmented label="Units" [options]="unitOptions()" [value]="unit()"
                        (valueChange)="unitChange.emit($any($event))" />
        </sb-field>
        @if (!tuning()) {
          <span class="population" [class.num]="hasSample()">{{ population() }}</span>
          @if (asOf()) { <sb-freshness [at]="asOf()!" /> }
          @if (allTimePanels() > 0) {
            <span class="all-time">{{ allTimePanels() }} panels all-time</span>
          }
          @if (fxMissing() > 0) {
            <span class="fx-caveat" role="note">{{ fxText() }}</span>
          }
        }
        }
      </div>
    </sb-control-bar>
  `,
  styles: `
    .scope-line { display: flex; flex-wrap: wrap; align-items: last baseline; gap: var(--space-10); min-width: 0; }
    /* v246 §A2: the date range takes a whole row where sb-control-bar's
       .filters is a grid (two columns below 640px); fullRow covers a flex
       row. On the field, which carries this component's style scope. */
    .range-field { grid-column: 1 / -1; }
    .account-wide { font-size: var(--text-chip); color: var(--text-secondary); min-width: 0; overflow-wrap: anywhere; }
    .population { font-size: var(--text-chip); color: var(--text-secondary); }
    .fx-caveat { font-size: var(--text-micro); color: var(--warn); min-width: 0; overflow-wrap: anywhere; }
    .all-time { font-size: var(--text-micro); text-transform: uppercase; letter-spacing: .06em; color: var(--warn); }
    /* v246 §A2: on a phone the scope line is the bar's full width, so the
       full-row Units field fills the row and its segments split it evenly. */
    @media (max-width: 639px) {
      .scope-line { flex: 1 1 100%; }
    }
  `,
})
export class ScopeBar {
  readonly scope = input.required<BookScope>();
  readonly unit = input.required<AnalyticsUnit>();
  readonly n = input<number | null>(null);
  readonly allTimePanels = input(0);
  readonly strategies = input<readonly string[]>([]);
  readonly horizons = input<readonly string[]>([]);
  readonly asOf = input<string | null>(null);
  /** Tuning has no scoped population of its own, so the bar collapses to the
   *  unit toggle there rather than offering filters nothing below obeys. */
  readonly tuning = input(false);
  /** v208: equity is account-wide; only the dates apply. */
  readonly benchmark = input(false);
  protected readonly accountWideNote = ACCOUNT_WIDE_NOTE;
  /** v194 B7: closed trades the money figures left out for want of an
   *  exchange rate (the payloads' `fx_missing_count`). */
  readonly fxMissing = input(0);
  private readonly connection = inject(ConnectionStore);
  readonly scopeChange = output<Partial<BookScope>>();
  readonly unitChange = output<AnalyticsUnit>();
  readonly cleared = output<void>();

  protected readonly presetOptions = [...RANGE_PRESETS.map((p) => ({ value: p.value, label: p.label })),
                                      { value: 'custom', label: 'Custom…' }];
  protected readonly ledgerOptions = [{ value: 'main', label: 'Main ledger' },
                                      { value: 'weak', label: 'WEAK ledger' },
                                      { value: 'both', label: 'Both ledgers' }];
  protected readonly directionOptions = [{ value: 'bullish', label: 'Long' }, { value: 'bearish', label: 'Short' }];
  /** The money side carries the account's own symbol (v194 B7): the server
   *  converts every money figure to the account currency. The value key
   *  stays `'money'`, so saved preferences survive. Mirrors Calendar's
   *  `metrics`. */
  protected readonly unitOptions = computed(() => [
    { value: 'r', label: 'R' }, { value: 'pct', label: '%' },
    { value: 'money', label: this.connection.currency() },
  ]);
  protected readonly fxText = computed(() => fxMissingText(this.fxMissing()));

  protected options(values: readonly string[]) { return values.map((v) => ({ value: v, label: v })); }

  protected readonly activeCount = computed(() => {
    const s = this.scope();
    if (this.benchmark()) return (['from', 'to'] as const).filter((k) => s[k]).length;
    return (['from', 'to', 'strategy', 'horizon', 'direction'] as const).filter((k) => s[k]).length
      + (s.ledger === 'main' ? 0 : 1);
  });

  /** Spec §3.4: an empty sample reads as "no data", never a dash beside a
   *  value. Zero closed trades is the same answer as none. */
  protected readonly hasSample = computed(() => (this.n() ?? 0) > 0);
  protected readonly population = computed(() =>
    this.hasSample() ? `N=${this.n()} closed` : 'no closed trades');

  /** Which preset the current bounds correspond to, or `custom`. */
  protected readonly preset = computed(() => {
    const s = this.scope();
    if (!s.from && !s.to) return 'all';
    for (const p of RANGE_PRESETS) {
      const r = presetRange(p.value, new Date());
      if (r.from === s.from && r.to === s.to) return p.value;
    }
    return 'custom';
  });

  protected onPreset(value: string): void {
    if (value === 'custom') { this.scopeChange.emit({}); return; }
    this.scopeChange.emit(presetRange(value, new Date()));
  }
}

/** v194 B7: the caveat when money figures left closed trades out for want
 *  of an exchange rate on their exit date; '' for none. Calendar uses it too. */
export function fxMissingText(n: number): string {
  if (!(n > 0)) return '';
  return n === 1
    ? '1 closed trade left out of money figures: no exchange rate for its exit date'
    : `${n} closed trades left out of money figures: no exchange rate for their exit dates`;
}

/** The largest left-out count among the scoped payloads a tab fetched. They
 *  answer one scope, so they count the same population; 0 when none says. */
export function fxMissingOf(...payloads: ({ fx_missing_count?: number } | null | undefined)[]): number {
  return Math.max(0, ...payloads.map((p) => p?.fx_missing_count ?? 0));
}
