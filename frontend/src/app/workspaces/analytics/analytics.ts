import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Params, Router } from '@angular/router';

import { AnalyticsUnit, BookScope } from '../../api/models';
import { AnalyticsStore } from '../../stores/analytics.store';
import { Tab, TabBar } from '../../ui/layout';
import { Page } from '../../ui/page';
import { ScopeBar, fxMissingOf } from './scope-bar';
import { scopeToQueryParams } from './scope-url';
import { AttributionTab } from './tabs/attribution';
import { EdgeTab } from './tabs/edge';
import { ExecutionTab } from './tabs/execution';
import { OverviewTab } from './tabs/overview';
import { PartialsTab } from './tabs/partials';
import { PipelineTab } from './tabs/pipeline';
import { TuningTab } from './tabs/tuning';

/** The ten swing horizons, mirrored from
 *  `swingbot/core/market/strategy_types.py::HORIZONS`. Only a fallback: the
 *  heat grid's own payload carries the axis the server actually aggregated,
 *  and that is preferred, so a horizon added on the Python side shows up here
 *  without this list being touched. */
const FALLBACK_HORIZONS = ['2w', '4w', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m'] as const;

/**
 * Analytics — seven tabs in the order a trader asks (spec v94 D1; v142 adds
 * Partials last), one scope
 * bar above them (D2). This file is a shell: the tab strip and the bar (the page's scope bar since v195), and a
 * switch. Every panel lives in `tabs/`, so no file here grows back into the
 * 2,233-line component v94 replaced.
 */
@Component({
  selector: 'sb-analytics',
  changeDetection: ChangeDetectionStrategy.OnPush,
  // v54 D1: this workspace's bulk is tables (breakdown rows, the heat grid,
  // the registry, grid results) -- tight rows, more per screen -- so it
  // defaults to the instrument register. On the host (a static class, not a
  // template wrapper) because :host is the ancestor the register's three
  // variables need to reach, and it has to be set here rather than per tab:
  // the tabs are projected into this host, and a register declared six times
  // is six chances for two tabs to disagree about their own density.
  host: { class: 'register-instrument' },
  imports: [Page, TabBar, ScopeBar, OverviewTab, AttributionTab, ExecutionTab, EdgeTab, PipelineTab, TuningTab, PartialsTab],
  template: `
    <!-- v195 Phase 4: the route title is the page's one h1. The tab strip
         and the one scope bar are the page's scope (filters and tabs only);
         the open tab is the primary panel and owns its own panels. -->
    <sb-page>
      <div page-scope class="scope">
        <sb-tab-bar [tabs]="tabs" [active]="store.tab()" (activeChange)="goToTab($event)" />
        <sb-scope-bar
          [scope]="store.scope()" [unit]="store.unit()" [n]="store.scopeN()"
          [allTimePanels]="store.allTimePanelCount()" [strategies]="strategyNames()"
          [horizons]="horizons()" [asOf]="store.asOf()" [fxMissing]="fxMissing()" [tuning]="store.tab() === 'tuning'"
          (scopeChange)="onScope($event)" (unitChange)="onUnit($event)" (cleared)="store.clearScope()" />
      </div>
      <div page-primary class="tab-body">
        @switch (store.tab()) {
          @case ('overview') { <sb-overview-tab /> }
          @case ('attribution') { <sb-attribution-tab /> }
          @case ('execution') { <sb-execution-tab /> }
          @case ('edge') { <sb-edge-tab /> }
          @case ('pipeline') { <sb-pipeline-tab /> }
          @case ('tuning') { <sb-tuning-tab /> }
          @case ('partials') { <sb-partials-tab /> }
        }
      </div>
    </sb-page>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .scope, .tab-body { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); min-width: 0; }
  `,
})
export class Analytics {
  protected readonly store = inject(AnalyticsStore);
  /** v194 B7: how many scoped closes the tab's money figures left out. */
  protected readonly fxMissing = computed(() =>
    fxMissingOf(this.store.performance(), this.store.equityCurve(), this.store.byDimension()));
  private readonly router = inject(Router);
  protected readonly tabs: Tab[] = [
    { id: 'overview', label: 'Overview' }, { id: 'attribution', label: 'Attribution' },
    { id: 'execution', label: 'Execution' }, { id: 'edge', label: 'Edge' },
    { id: 'pipeline', label: 'Pipeline' }, { id: 'tuning', label: 'Tuning' },
    { id: 'partials', label: 'Partials' },
  ];
  /** The axis the server actually aggregated, falling back to the mirrored
   *  keys before the first heat-grid response. */
  protected readonly horizons = computed<readonly string[]>(
    () => this.store.heatGrid()?.cols ?? FALLBACK_HORIZONS);
  protected readonly strategyNames = computed(() =>
    (this.store.strategies()?.strategies ?? [])
      .map((row) => {
        const entry = row as { strategy?: unknown; name?: unknown };
        return String(entry.strategy ?? entry.name ?? '');
      })
      .filter((name) => name !== '')
      .sort());

  protected goToTab(tab: string): void { this.navigate({ tab: tab === 'overview' ? null : tab }); }
  protected onScope(patch: Partial<BookScope>): void {
    this.store.setScope(patch);
    this.navigate(scopeToQueryParams(this.store.tab(), this.store.scope(), this.store.unit()));
  }
  protected onUnit(unit: AnalyticsUnit): void {
    this.store.setUnit(unit);
    this.navigate({ unit: unit === 'r' ? null : unit });
  }
  /** `merge` plus explicit nulls: the scope's own writer clears what it does
   *  not set, and nothing else in the query string is disturbed. */
  private navigate(queryParams: Params): void {
    this.router.navigate([], { queryParams, queryParamsHandling: 'merge', replaceUrl: true });
  }
}
