import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { AnalyticsUnit, BookScope } from '../../api/models';
import { RANGE_PRESETS, presetRange } from '../../stores/analytics.store';
import { ControlBar } from '../../ui/control-bar';
import { DateRange } from '../../ui/date-range';
import { Select } from '../../ui/form-controls';
import { Freshness } from '../../ui/freshness';
import { Segmented } from '../../ui/segmented';

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
  imports: [ControlBar, DateRange, Select, Segmented, Freshness],
  template: `
    <sb-control-bar [activeCount]="activeCount()" (cleared)="cleared.emit()">
      <!-- One ng-container per slot: an @if with several roots inside a
           projection slot silently drops every node but the first
           (NG8011), and a filter that vanishes is the failure this bar
           exists to prevent. -->
      <ng-container filters>
        @if (!tuning()) {
          <sb-select label="Range" [value]="preset()" [options]="presetOptions"
                     (valueChange)="onPreset($event)" />
          @if (preset() === 'custom') {
            <sb-date-range [from]="scope().from" [to]="scope().to"
                           (changed)="scopeChange.emit($event)" />
          }
          <sb-select label="Ledger" [value]="scope().ledger" [options]="ledgerOptions"
                     (valueChange)="scopeChange.emit({ ledger: $any($event) })" />
          <sb-select label="Strategy" placeholder="Any strategy" [value]="scope().strategy ?? ''"
                     [options]="options(strategies())" (valueChange)="scopeChange.emit({ strategy: $event || null })" />
          <sb-select label="Horizon" placeholder="Any horizon" [value]="scope().horizon ?? ''"
                     [options]="options(horizons())" (valueChange)="scopeChange.emit({ horizon: $event || null })" />
          <sb-select label="Direction" placeholder="Both" [value]="scope().direction ?? ''"
                     [options]="directionOptions" (valueChange)="scopeChange.emit({ direction: $event || null })" />
        }
      </ng-container>
      <!-- v179 §3.4: a box of its own on the text baseline -- sb-control-bar's
           .scope centres its children, which put the population text and the
           unit toggle's labels at two heights. -->
      <div scope class="scope-line">
        <sb-segmented label="Unit" [options]="unitOptions" [value]="unit()"
                      (valueChange)="unitChange.emit($any($event))" />
        @if (!tuning()) {
          <span class="population" [class.num]="hasSample()">{{ population() }}</span>
          @if (asOf()) { <sb-freshness [at]="asOf()!" /> }
          @if (allTimePanels() > 0) {
            <span class="all-time">{{ allTimePanels() }} panels all-time</span>
          }
        }
      </div>
    </sb-control-bar>
  `,
  styles: `
    .scope-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-10); min-width: 0; }
    .population { font-size: var(--text-chip); color: var(--text-secondary); }
    .all-time { font-size: var(--text-micro); text-transform: uppercase; letter-spacing: .06em; color: var(--warn); }
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
  readonly scopeChange = output<Partial<BookScope>>();
  readonly unitChange = output<AnalyticsUnit>();
  readonly cleared = output<void>();

  protected readonly presetOptions = [...RANGE_PRESETS.map((p) => ({ value: p.value, label: p.label })),
                                      { value: 'custom', label: 'Custom…' }];
  protected readonly ledgerOptions = [{ value: 'main', label: 'Main ledger' },
                                      { value: 'weak', label: 'WEAK ledger' },
                                      { value: 'both', label: 'Both ledgers' }];
  protected readonly directionOptions = [{ value: 'bullish', label: 'Long' }, { value: 'bearish', label: 'Short' }];
  protected readonly unitOptions = [{ value: 'r', label: 'R' }, { value: 'pct', label: '%' }, { value: 'money', label: '$' }];

  protected options(values: readonly string[]) { return values.map((v) => ({ value: v, label: v })); }

  protected readonly activeCount = computed(() => {
    const s = this.scope();
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
