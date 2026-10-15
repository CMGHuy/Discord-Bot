import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Router } from '@angular/router';

import { ReportTab, ReportsStore } from '../../stores/reports.store';
import { Async, asyncInputs } from '../../ui/async';
import { Freshness } from '../../ui/freshness';
import { Tab, TabBar } from '../../ui/layout';
import { SectionHead } from '../../ui/section-head';
import { AttributionTab } from './attribution-tab';
import { GatesTab } from './gates-tab';

export const DISCLAIMER = 'Historical measurement on paper trades; not a forecast or advice.';

/** The production run path, per report (`docs/deploy/DEPLOY_HETZNER.md`). */
const RUN_COMMAND: Record<ReportTab, string> = {
  attribution:
    'bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/expectancy_attribution.py"',
  gates:
    'bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/gate_counterfactual_report.py"',
};

/**
 * Reports — what the measurements say about entries and gates.
 *
 * A shell: the tab strip, the freshness marker, the not-yet-run state and
 * the fixed footer. Each tab is its own component and fetches only its own
 * report (the route resolver calls `ReportsStore.resolveTab`).
 *
 * "Not yet run" is a state, not an error: a report exists only after someone
 * runs its script on the VM, so the page says how rather than showing a zero
 * or an empty axis.
 */
@Component({
  selector: 'sb-reports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Async, AttributionTab, Freshness, GatesTab, SectionHead, TabBar],
  host: { class: 'register-instrument' },
  template: `
    <sb-section-head>
      <!-- A report has no cadence, so it is never flagged stale: the
           timestamp itself is the information. -->
      <sb-freshness actions [at]="store.generatedAt()" [staleAfterSec]="neverStale" />
    </sb-section-head>

    <sb-tab-bar [tabs]="tabs" [active]="store.tab()" (activeChange)="goToTab($event)" />

    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="no-data-yet"
      emptyTitle="Not yet run"
      [emptyHint]="runHint()"
      [skeletonRows]="8"
      [skeletonCols]="5"
      (retry)="store.load()"
    >
      @switch (store.tab()) {
        @case ('gates') { <sb-gates-tab /> }
        @default { <sb-expectancy-attribution-tab /> }
      }
    </sb-async>

    <p class="disclaimer">{{ disclaimer }}</p>
  `,
  styles: `
    :host { display: grid; gap: var(--space-14); }
    .disclaimer { margin: 0; color: var(--text-faint); font-size: var(--text-micro); }
  `,
})
export class Reports {
  protected readonly store = inject(ReportsStore);
  private readonly router = inject(Router);

  protected readonly disclaimer = DISCLAIMER;
  protected readonly neverStale = Number.MAX_SAFE_INTEGER;
  protected readonly tabs: Tab[] = [
    { id: 'attribution', label: 'Expectancy attribution' },
    { id: 'gates', label: 'Gate counterfactual' },
  ];

  protected readonly async = computed(() =>
    asyncInputs(this.store, { isEmpty: (envelope) => envelope.status === 'not_run' }),
  );

  protected readonly runHint = computed(
    () => `Run it on the VM: ${RUN_COMMAND[this.store.tab()]}`,
  );

  /** The default tab leaves no `?tab=` behind. */
  protected goToTab(tab: string): void {
    this.router.navigate([], {
      queryParams: { tab: tab === 'attribution' ? null : tab },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
