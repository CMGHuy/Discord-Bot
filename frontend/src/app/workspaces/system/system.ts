import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
} from '@angular/core';
import { Router } from '@angular/router';

import { SYSTEM_TABS, SystemStore, SystemTab } from '../../stores/system.store';
import { Tab, TabBar } from '../../ui/layout';
import { SectionHead } from '../../ui/section-head';
import { LogsTab } from './logs-tab';
import { ScanTab } from './scan-tab';
import { SettingsTab } from './settings-tab';

/** Settings · Logs · Scan — spec v14 Decision 8, in its order. */
const TABS: Tab[] = [
  { id: 'settings', label: 'Settings' },
  { id: 'logs', label: 'Logs' },
  { id: 'scan', label: 'Scan' },
];

const TAB_IDS = new Set<string>(SYSTEM_TABS);

/**
 * System — the administrative workspace: configuration, logs, scan control.
 *
 * A shell over three tab components that each read `SystemStore`. Split by
 * file rather than by store because they share one refetch story and one
 * `settings`/`scan`/`bot` event wiring; splitting the store as well would
 * mean three subscriptions to the same events.
 *
 * **The active tab is a query parameter**, as on Analytics and for the same
 * reason: a tab held in component state cannot be linked to, does not
 * survive a reload, and makes the back button skip the whole workspace.
 *
 * The tab bodies are rendered with `@switch` rather than kept alive hidden.
 * The one piece of state that must survive switching away is the settings
 * draft, and it lives in the store — which is what makes leaving the tab to
 * check a log safe mid-edit.
 */
@Component({
  selector: 'sb-system',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TabBar, SettingsTab, LogsTab, ScanTab, SectionHead],
  // v54 D1: the three tabs behind this shell (Settings, Logs, Scan) are all
  // dense operational surfaces -- tight rows, more per screen -- so it
  // defaults to the instrument register. On the host (a static class, not a
  // template wrapper) because :host is the ancestor the register's three
  // variables need to reach.
  host: { class: 'register-instrument' },
  providers: [SystemStore],
  template: `
    <sb-section-head heading="System">
      @if (store.dirty()) {
        <!-- Visible from every tab: the draft survives switching away, and
             unsaved configuration you have forgotten about is worse than
             the reminder. -->
        <span actions class="dirty" role="status">Unsaved settings</span>
      }
    </sb-section-head>

    <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="goToTab($event)" />

    @switch (activeTab()) {
      @case ('logs') {
        <sb-logs-tab />
      }
      @case ('scan') {
        <sb-scan-tab />
      }
      @default {
        <sb-settings-tab />
      }
    }
  `,
  styles: `
    /* minmax(0, 1fr), not the implicit auto track. An auto column is floored
       at its widest child's min-content, so one un-shrinkable panel stretched
       the workspace past the viewport and took the page sideways with it.
       Clamping the track is what makes the children's own overflow-x
       containers the thing that scrolls instead.
       No backticks in here: these styles live in a TS template literal. */
    /* v54 D1: --space-20 was this rule's own literal before the registers
       existed; --register-pad's instrument rung is --space-10, so the gap
       between the tab bar and the active tab's body shrinks. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--register-pad); }
    .dirty { color: var(--warn); font-size: var(--text-table); }
  `,
})
export class System {
  private readonly router = inject(Router);
  protected readonly store = inject(SystemStore);

  /** Arrives through `withComponentInputBinding`, so this component is
   *  testable without standing up a router. */
  readonly tab = input<string>();

  protected readonly tabs = TABS;

  /** An unknown or absent `?tab=` falls back to Settings rather than
   *  rendering nothing, so a hand-edited URL still shows something. */
  protected readonly activeTab = computed<SystemTab>(() => {
    const requested = this.tab();
    return requested && TAB_IDS.has(requested) ? (requested as SystemTab) : 'settings';
  });

  protected goToTab(tab: string): void {
    // Matching Analytics: `replaceUrl` so flipping tabs does not fill the
    // history, `merge` so nothing else in the URL is dropped, and the
    // default tab drops the parameter rather than pinning `?tab=settings`.
    void this.router.navigate([], {
      queryParams: { tab: tab === 'settings' ? null : tab },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
