import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { SystemStore } from '../../stores/system.store';
import { Button } from '../../ui/button';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { dateTime } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { Freshness } from '../../ui/freshness';
import { Toolbar, ToolbarControl } from '../../ui/toolbar';

/**
 * Three short commands, nothing to demote. `sb-control-row` force-stacks
 * into a full-width column below 640px, which turns "Scan now" into the
 * first of three screen-wide blocks; `sb-toolbar`'s inline row wraps them
 * instead, at whatever width the buttons actually need. All `'xs'`: unlike
 * Trades' filters, there is no lower-priority subset here to send to a
 * sheet -- everything on this tab is the thing the tab is for.
 */
export const SCAN_CONTROLS: ToolbarControl[] = [
  { id: 'run', label: 'Scan now', inlineFrom: 'xs' },
  { id: 'stop', label: 'Stop current scan', inlineFrom: 'xs' },
  { id: 'pause', label: 'Pause or resume automatic scanning', inlineFrom: 'xs' },
];

/**
 * Scan control and bot restart.
 *
 * Every command here is cooperative: the admin writes a flag file and the
 * bot picks it up on its next poll. That is why each button reports what the
 * server said rather than flipping a switch — "queued" and "done" are
 * genuinely different, and a UI that showed the second when it meant the
 * first would have someone waiting on a scan that had not started.
 *
 * **Restart degrades honestly.** The Docker socket mount is optional, so a
 * deployment can be unable to restart the bot at all. `restart_available`
 * says so ahead of time and hides the button; a 503 says so after the fact
 * and is shown verbatim. Neither is reported as "the restart failed".
 */
@Component({
  selector: 'sb-scan-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Button, ConfirmDialog, Toolbar, Freshness],
  template: `
    <sb-panel heading="Scan">
      <div class="states">
        <span class="state" [class.on]="store.scanRunning()">
          {{ store.scanRunning() ? 'Scanning now' : 'Idle' }}
        </span>
        @if (store.scanQueued()) {
          <span class="state warn">Scan queued</span>
        }
        @if (store.scanPaused()) {
          <span class="state warn">Automatic scanning paused</span>
        }
        <span class="state" [class.warn]="!store.botAlive()">
          {{ store.botAlive() ? 'Bot alive' : 'Bot not reporting' }}
        </span>
      </div>

      @if (lastSeen(); as seen) {
        <p class="meta">Bot last seen {{ seen }}</p>
      }
      <sb-freshness [at]="store.scan()?.bot_last_seen ?? null" />

      <sb-toolbar class="commands" [controls]="controls">
        <button
          slot="run"
          sb-button
          variant="primary"
          type="button"
          [loading]="store.scanPending() === 'trigger'"
          (click)="store.runScanCommand('trigger')"
        >
          Scan now
        </button>
        <button
          slot="stop"
          sb-button
          variant="secondary"
          type="button"
          [loading]="store.scanPending() === 'stop'"
          [disabled]="!store.scanRunning()"
          (click)="store.runScanCommand('stop')"
        >
          Stop current scan
        </button>
        <!-- Pause and resume are one control in two states rather than two
             buttons, one of which is always a no-op. The div, not the
             button, is what sb-toolbar reparents -- its docstring rules out
             putting a slotted element directly inside a host-side @if/@for,
             and this @if/@else is exactly that; wrapping it in a stable
             slot="pause" element keeps only the *content* swapping. -->
        <div slot="pause">
          @if (store.scanPaused()) {
            <button
              sb-button
              variant="secondary"
              type="button"
              [loading]="store.scanPending() === 'resume'"
              (click)="store.runScanCommand('resume')"
            >
              Resume automatic scanning
            </button>
          } @else {
            <button
              sb-button
              variant="secondary"
              type="button"
              [loading]="store.scanPending() === 'pause'"
              (click)="store.runScanCommand('pause')"
            >
              Pause automatic scanning
            </button>
          }
        </div>
      </sb-toolbar>

      @if (store.scanMessage(); as message) {
        <!-- The server's own words: "queued -- the bot picks it up within 30
             seconds" is a promise about a poll, and paraphrasing it into
             "started" would be a different, wrong promise. -->
        <p class="message" role="status">{{ message }}</p>
      }
      @if (store.scanError(); as message) {
        <p class="error" role="alert">{{ message }}</p>
      }
    </sb-panel>

    <sb-panel heading="Bot process">
      @if (store.restartAvailable()) {
        <p class="explain">
          Restarts the bot container. Open positions are unaffected — they
          live in the data files, not in the process.
        </p>
        <button
          sb-button
          variant="danger"
          type="button"
          [loading]="store.restarting()"
          (click)="asking.set(true)"
        >
          Restart bot
        </button>
      } @else {
        <!-- Not a failure and not a disabled button with no explanation:
             this deployment has no Docker socket mounted, so restarting is
             something it cannot do rather than something that went wrong. -->
        <p class="explain">
          Restarting is unavailable in this deployment — the admin container
          has no Docker socket mounted. Restart manually with
          <code>docker compose restart bot</code>.
        </p>
      }

      @if (store.restartMessage(); as message) {
        <p [class]="store.restartUnavailable() ? 'error' : 'message'" role="status">
          {{ message }}
        </p>
      }
    </sb-panel>

    <sb-confirm-dialog
      [open]="asking()"
      title="Restart the bot"
      consequence="The bot container will stop and start again. Any scan in progress is abandoned, and alerts are not delivered until it is back."
      confirmLabel="Restart"
      [working]="store.restarting()"
      (confirmed)="restart()"
      (cancelled)="asking.set(false)"
    />
  `,
  styles: `
    /* minmax(0, 1fr), not the implicit auto track. An auto column is floored
       at its widest child's min-content, so one un-shrinkable panel stretched
       the workspace past the viewport and took the page sideways with it.
       Clamping the track is what makes the children's own overflow-x
       containers the thing that scrolls instead.
       No backticks in here: these styles live in a TS template literal. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }

    .states { display: flex; flex-wrap: wrap; gap: var(--space-8); }
    .state {
      padding: 1px var(--space-6);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .state.on { color: var(--text); border-color: var(--border-strong); }
    .state.warn { color: var(--warn); border-color: var(--warn); }

    .meta { margin-top: var(--space-8); color: var(--text-faint); font-size: var(--text-chip); }
    .commands { margin-top: var(--space-14); }
    .explain {
      max-width: 60ch;
      margin-bottom: var(--space-10);
      color: var(--text-secondary);
      font-size: var(--text-table);
      line-height: 1.5;
    }
    code { font-family: var(--font-mono); color: var(--text); }
    .message { margin-top: var(--space-10); color: var(--text-secondary); font-size: var(--text-table); }
    .error { margin-top: var(--space-10); color: var(--neg); font-size: var(--text-table); }
  `,
})
export class ScanTab {
  protected readonly store = inject(SystemStore);
  protected readonly controls = SCAN_CONTROLS;

  protected readonly asking = signal(false);

  protected readonly lastSeen = computed(() => {
    const seen = this.store.scan()?.bot_last_seen;
    return seen ? dateTime(seen) : null;
  });

  protected restart(): void {
    this.store.restartBot();
    this.asking.set(false);
  }
}
