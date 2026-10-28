import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';

import { LogSource, SystemStore, SystemTab, systemTabFrom } from '../../stores/system.store';
import { Button } from '../../ui/button';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { Tab, TabBar } from '../../ui/layout';
import { Page } from '../../ui/page';
import { LogsTab } from './logs-tab';
import { ProvidersTab } from './providers-tab';
import { ScanTab } from './scan-tab';
import { SettingsTab } from './settings-tab';

/** Scan · Providers · Settings · Logs — v195 §5.1, the order of
 *  `SYSTEM_TABS`. Settings stays the landing tab (correction 4). */
const TABS: Tab[] = [
  { id: 'scan', label: 'Scan' },
  { id: 'providers', label: 'Providers' },
  { id: 'settings', label: 'Settings' },
  { id: 'logs', label: 'Logs' },
];

/** The destructive commands the System tabs offer, each in the page header. */
export type SystemAction = 'restart' | 'clear-log' | 'discard';

/** v195 Phase 4: the one header command that belongs to each tab. Providers
 *  is a readout and has none. */
export const TAB_ACTION: Readonly<Record<SystemTab, SystemAction | null>> = {
  scan: 'restart',
  providers: null,
  settings: 'discard',
  logs: 'clear-log',
};

/** Names the file, because "are you sure?" is answered yes reflexively and
 *  these two logs are the only record of what the bot did. Moved from
 *  logs-tab.ts with the button (v195 Phase 4). */
export function clearLogConsequence(path: string | null | undefined, source: LogSource): string {
  return `${path ?? `the ${source} log`} will be emptied. Its contents are not backed up and cannot be recovered.`;
}

/**
 * System — the administrative workspace: configuration, logs, scan control,
 * provider health.
 *
 * A shell over four tab components that each read `SystemStore`. Split by
 * file rather than by store because they share one refetch story and one
 * `settings`/`scan`/`bot` event wiring; splitting the store as well would
 * mean several subscriptions to the same events.
 *
 * **On `sb-page` (v195 Phase 4).** The page title is the one `h1`, the tab
 * bar is the scope bar, the open tab is the primary slot. The tab's one
 * destructive command -- restart the bot, clear the log, discard the
 * settings draft -- sits in the header's actions slot, `danger-quiet`,
 * behind its confirm dialog: never inside a tab body, so a housekeeping
 * command is always in the same place and never beside a routine one.
 * Each keeps the condition it had in its tab: Restart only where the
 * deployment can restart, Discard only while there is a draft to lose.
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
  imports: [Page, TabBar, Button, ConfirmDialog, SettingsTab, LogsTab, ScanTab, ProvidersTab],
  // v54 D1: the tabs behind this shell are dense operational surfaces --
  // tight rows, more per screen -- so it defaults to the instrument
  // register. On the host (a static class, not a template wrapper) because
  // :host is the ancestor the register's three variables need to reach.
  host: { class: 'register-instrument' },
  template: `
    <sb-page>
      <div page-actions class="page-actions">
        @if (store.dirty()) {
          <!-- Visible from every tab: the draft survives switching away, and
               unsaved configuration you have forgotten about is worse than
               the reminder. -->
          <span class="dirty" role="status">Unsaved settings</span>
        }
        @switch (action()) {
          @case ('restart') {
            <button
              sb-button
              variant="danger-quiet"
              type="button"
              data-action="restart"
              [loading]="store.restarting()"
              (click)="asking.set('restart')"
            >
              Restart bot
            </button>
          }
          @case ('clear-log') {
            <button
              sb-button
              variant="danger-quiet"
              type="button"
              data-action="clear-log"
              (click)="asking.set('clear-log')"
            >
              Clear log
            </button>
          }
          @case ('discard') {
            <button
              sb-button
              variant="danger-quiet"
              type="button"
              data-action="discard"
              [disabled]="store.saving()"
              (click)="asking.set('discard')"
            >
              Discard changes
            </button>
          }
        }
      </div>

      <sb-tab-bar page-scope [tabs]="tabs" [active]="activeTab()" (activeChange)="goToTab($event)" />

      <div page-primary class="tab-body">
        @switch (activeTab()) {
          @case ('scan') {
            <sb-scan-tab />
          }
          @case ('providers') {
            <sb-providers-tab />
          }
          @case ('logs') {
            <sb-logs-tab />
          }
          @default {
            <sb-settings-tab />
          }
        }
      </div>

      <sb-confirm-dialog
        [open]="asking() === 'restart'"
        title="Restart the bot"
        consequence="The bot container will stop and start again. Any scan in progress is abandoned, and alerts are not delivered until it is back."
        confirmLabel="Restart"
        dangerVariant="danger-quiet"
        [working]="store.restarting()"
        (confirmed)="confirm('restart')"
        (cancelled)="asking.set(null)"
      />
      <sb-confirm-dialog
        [open]="asking() === 'clear-log'"
        title="Clear the log"
        [consequence]="clearConsequence()"
        confirmLabel="Clear"
        dangerVariant="danger-quiet"
        (confirmed)="confirm('clear-log')"
        (cancelled)="asking.set(null)"
      />
      <sb-confirm-dialog
        [open]="asking() === 'discard'"
        title="Discard unsaved settings?"
        consequence="Every unsaved setting change in this form will be lost."
        confirmLabel="Discard changes"
        dangerVariant="danger-quiet"
        (confirmed)="confirm('discard')"
        (cancelled)="asking.set(null)"
      />
    </sb-page>
  `,
  styles: `
    /* sb-page lays out the header, scope bar and primary slot and their
       gaps; this host only carries the register.
       No backticks in here: these styles live in a TS template literal. */
    :host { display: block; }
    .page-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: flex-end;
      gap: var(--space-8);
    }
    .dirty { color: var(--warn); font-size: var(--text-table); }
    /* minmax(0, 1fr), not the implicit auto track: one un-shrinkable panel in
       a tab must not stretch the workspace past the viewport. */
    .tab-body { display: grid; grid-template-columns: minmax(0, 1fr); }
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
  protected readonly activeTab = computed<SystemTab>(() => systemTabFrom(this.tab()));

  /** The dialog showing, if any. Only ever set from a header button, so no
   *  confirmation shows for a command nobody asked for. */
  protected readonly asking = signal<SystemAction | null>(null);

  /** The open tab's header command, under the condition its tab used:
   *  no Restart where the deployment cannot restart (the Bot process panel
   *  says why), no Discard without a draft. */
  protected readonly action = computed<SystemAction | null>(() => {
    const action = TAB_ACTION[this.activeTab()];
    if (action === 'restart' && !this.store.restartAvailable()) return null;
    if (action === 'discard' && !this.store.dirty()) return null;
    return action;
  });

  protected readonly clearConsequence = computed(() =>
    clearLogConsequence(this.store.logs()?.path, this.store.logSource()),
  );

  private readonly run: Record<SystemAction, () => void> = {
    restart: () => this.store.restartBot(),
    'clear-log': () => this.store.clearLogs(),
    discard: () => this.store.resetDraft(),
  };

  protected confirm(action: SystemAction): void {
    this.run[action]();
    this.asking.set(null);
  }

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
