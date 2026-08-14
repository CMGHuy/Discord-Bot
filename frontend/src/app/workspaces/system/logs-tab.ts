import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  inject,
  signal,
  untracked,
  viewChild,
} from '@angular/core';

import {
  LOG_LEVELS,
  LOG_LINE_CHOICES,
  LogSource,
  SystemStore,
} from '../../stores/system.store';
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

      <!-- SR57. The tail migrated as text; the tools for reading it did not.
           Level checkboxes filter what is already here; the line count
           refetches, because filtering a 500-line response cannot show line
           501. -->
      <div class="triage">
        <div class="levels" role="group" aria-label="Log levels">
          @for (level of levels; track level) {
            <label class="level" [class]="'level-' + level.toLowerCase()">
              <input
                type="checkbox"
                [checked]="store.logLevels()[level]"
                (change)="store.setLogLevel(level, $any($event.target).checked)"
              />
              {{ level }}
            </label>
          }
        </div>

        <label class="count">
          Lines
          <select
            [value]="store.logLines()"
            (change)="store.setLogLines(+$any($event.target).value)"
          >
            @for (choice of lineChoices; track choice) {
              <option [value]="choice">{{ choice }}</option>
            }
          </select>
        </label>

        @if (store.hiddenLogLines(); as hidden) {
          <!-- Said out loud: a filter that silently removes most of a log is
               indistinguishable from a log that is nearly empty. -->
          <span class="hidden-count">{{ hidden }} lines hidden by filter</span>
        }
      </div>

      @if (store.logs(); as logs) {
        @if (logs.content) {
          <!-- A <pre>, not a table: log lines are already formatted and any
               attempt to structure them here would be guessing at a format
               the bot is free to change. -->
          <!-- SR63. Whole lines carry the level class, matching
               logs.html:80-113: colouring only the [ERROR] token leaves the
               message that matters indistinguishable at a glance. -->
          <pre class="log" #logBox (scroll)="onLogScroll()">@for (line of store.visibleLogLines(); track $index) {<span
              class="log-line"
              [class]="line.level ? 'lvl-' + line.level.toLowerCase() : ''"
            >{{ line.text }}
</span>}</pre>
          @if (!store.visibleLog()) {
            <p class="none">Every line is filtered out. Check a level above.</p>
          }
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

    /* -- SR57: triage controls --------------------------------------- */
    .triage {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-10);
      margin-bottom: var(--space-8);
      font-size: var(--text-chip);
    }
    .levels { display: flex; flex-wrap: wrap; gap: var(--space-8); }
    .level { display: flex; align-items: center; gap: var(--space-4); }
    /* ERROR and WARNING are the only two hues here, per the colour rule --
       INFO and DEBUG stay secondary text rather than earning a colour. */
    .level-error { color: var(--neg); }
    .level-warning { color: var(--warn); }
    .level-info, .level-debug { color: var(--text-secondary); }
    .count { display: flex; align-items: center; gap: var(--space-4); color: var(--text-secondary); }
    .hidden-count {
      margin-left: auto;
      color: var(--text-faint);
      font-variant-numeric: tabular-nums;
    }

    /* -- SR63: per-level line colour ---------------------------------- */
    .log-line { display: block; }
    /* ERROR and WARNING only, per the colour rule. INFO and DEBUG inherit the
       pre's own colour rather than each spending a hue on being ordinary. */
    .lvl-error { color: var(--neg); }
    .lvl-warning { color: var(--warn); }
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

  /** SR57 — driven off the store's constants, so the filter can never offer
   *  a level the parser does not recognise. */
  protected readonly levels = LOG_LEVELS;
  protected readonly lineChoices = LOG_LINE_CHOICES;

  private readonly logBox = viewChild<ElementRef<HTMLElement>>('logBox');

  /**
   * SR63 — open at the newest lines, and stay there across a refresh.
   *
   * `logs.html:143-146`'s rule, kept: only auto-scroll when the reader was
   * ALREADY within 60px of the bottom. Someone who has scrolled up to read a
   * traceback is reading it, and yanking them back down on the next refresh
   * is how a log viewer becomes unusable at exactly the moment it matters.
   *
   * The first render always scrolls, because there is no scroll position to
   * preserve yet and the tail is what a log is for.
   */
  private wasAtBottom = true;

  private readonly keepAtBottom = effect(() => {
    this.store.visibleLogLines();          // re-run whenever the tail changes
    const box = untracked(() => this.logBox()?.nativeElement);
    if (!box) return;
    if (this.wasAtBottom) box.scrollTop = box.scrollHeight;
  });

  protected onLogScroll(): void {
    const box = this.logBox()?.nativeElement;
    if (!box) return;
    this.wasAtBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 60;
  }

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
