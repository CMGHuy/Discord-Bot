import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { LogSource, SystemStore } from '../../stores/system.store';
import { Button } from '../../ui/button';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { Panel } from '../../ui/layout';

/**
 * The log tail — bot or admin, with a raw view and a clear action.
 *
 * **No auto-refresh timer.** The Jinja page reloaded itself; here the
 * refresh is a button, because a log that updates on a timer looks live
 * without being live, and the moment that matters is when someone is
 * reading a traceback that a reload would scroll away.
 */
@Component({
  selector: 'sb-logs-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Button, ConfirmDialog],
  template: `
    <sb-panel [heading]="store.logs()?.path ?? 'Log'">
      <div panel-actions class="actions">
        @for (source of sources; track source) {
          <button
            sb-button
            [variant]="store.logSource() === source ? 'secondary' : 'ghost'"
            type="button"
            [attr.aria-pressed]="store.logSource() === source"
            (click)="store.setLogSource(source)"
          >
            {{ source }}
          </button>
        }
        <button
          sb-button
          variant="ghost"
          type="button"
          [loading]="store.logsLoading()"
          (click)="store.loadLogs()"
        >
          Refresh
        </button>
        <!-- A real link: the raw endpoint is text/plain and the browser
             renders it better than any viewer built here would. -->
        <a class="raw" [href]="rawUrl()" target="_blank" rel="noopener">Raw</a>
        <button sb-button variant="danger" type="button" (click)="asking.set(true)">
          Clear
        </button>
      </div>

      @if (store.logsError(); as message) {
        <p class="error" role="status">{{ message }}</p>
      }
      @if (store.logsMessage(); as message) {
        <p class="message" role="status">{{ message }}</p>
      }

      @if (store.logs(); as logs) {
        @if (logs.content) {
          <!-- A <pre>, not a table: log lines are already formatted and any
               attempt to structure them here would be guessing at a format
               the bot is free to change. -->
          <pre class="log">{{ logs.content }}</pre>
          <p class="meta">Last {{ logs.lines }} lines · {{ logs.path }}</p>
        } @else {
          <p class="none">This log is empty.</p>
        }
      } @else if (!store.logsLoading()) {
        <p class="none">No log loaded.</p>
      }
    </sb-panel>

    <sb-confirm-dialog
      [open]="asking()"
      title="Clear the log"
      [consequence]="consequence()"
      confirmLabel="Clear"
      (confirmed)="clear()"
      (cancelled)="asking.set(false)"
    />
  `,
  styles: `
    .actions { display: flex; align-items: center; gap: var(--space-6); }
    .raw {
      color: var(--accent);
      font-size: var(--text-table);
      text-decoration: none;
      padding: 0 var(--space-6);
    }
    .raw:hover { text-decoration: underline; }

    .log {
      max-height: 60vh;
      overflow: auto;
      padding: var(--space-10);
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text-secondary);
      font-family: var(--font-mono);
      font-size: var(--text-chip);
      line-height: 1.5;
      /* Lines are pre-formatted; wrapping them keeps a long traceback
         readable without a horizontal scrollbar under 60vh of text. */
      white-space: pre-wrap;
      word-break: break-word;
    }
    .meta { margin-top: var(--space-6); color: var(--text-faint); font-size: var(--text-chip); }
    .none { color: var(--text-faint); font-size: var(--text-table); }
    .error { color: var(--neg); font-size: var(--text-table); }
    .message { color: var(--text-secondary); font-size: var(--text-table); }
  `,
})
export class LogsTab {
  protected readonly store = inject(SystemStore);

  protected readonly sources: LogSource[] = ['bot', 'admin'];

  protected readonly asking = signal(false);

  protected rawUrl(): string {
    return this.store.rawLogUrl(this.store.logSource());
  }

  /** Names the file, because "are you sure?" is answered yes reflexively
   *  and these two logs are the only record of what the bot did. */
  protected consequence(): string {
    const path = this.store.logs()?.path ?? `the ${this.store.logSource()} log`;
    return `${path} will be emptied. Its contents are not backed up and cannot be recovered.`;
  }

  protected clear(): void {
    this.store.clearLogs();
    this.asking.set(false);
  }
}
