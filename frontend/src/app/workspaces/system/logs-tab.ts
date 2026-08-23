import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
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
import { asyncInputs, Async } from '../../ui/async';
import { Button } from '../../ui/button';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { Checkbox, Select, SelectOption } from '../../ui/form-controls';
import { ControlRow, Panel } from '../../ui/layout';

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
  imports: [Panel, Button, Checkbox, ConfirmDialog, ControlRow, Select, Async],
  template: `
    <sb-panel [heading]="store.logs()?.path ?? 'Log'">
      <sb-control-row panel-actions class="actions">
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
      </sb-control-row>

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
            <sb-checkbox
              [label]="level"
              [checked]="store.logLevels()[level]"
              (checkedChange)="store.setLogLevel(level, $event)"
            />
          }
        </div>

        <sb-select
          class="count"
          label="Lines"
          [options]="lineOptions"
          [value]="store.logLines().toString()"
          (valueChange)="store.setLogLines(+$event)"
        />

        @if (store.hiddenLogLines(); as hidden) {
          <!-- Said out loud: a filter that silently removes most of a log is
               indistinguishable from a log that is nearly empty. -->
          <span class="hidden-count">{{ hidden }} lines hidden by filter</span>
        }
      </div>

      <sb-async
        [loading]="logsAsync().loading"
        [error]="logsAsync().error"
        [empty]="logsAsync().empty"
        [staleAsOf]="logsAsync().staleAsOf"
        emptyReason="no-data-yet"
        emptyTitle="This log is empty"
        [skeletonRows]="15"
        [skeletonCols]="1"
        (retry)="store.loadLogs()"
      >
        @if (store.logs(); as logs) {
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
        }
      </sb-async>
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
    /* .actions keeps its class as a marker only -- sb-control-row supplies
       display, alignment, wrap and gap.
       .triage, .levels and .level below are NOT converted: .level is a
       <label> element whose native checkbox association depends on staying
       a label, and .triage/.levels only group them. .count moved to
       sb-select (v54) -- it wraps its own select in a label internally,
       so the same association survives one layer of encapsulation deeper. */

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
    /* v54: the level checkboxes lost their per-level label colour (ERROR
       red, WARNING amber) migrating to sb-checkbox -- its .field rule sets
       an explicit color: var(--text), which blocks inheritance from any
       class applied to the host. The level name is still spelled out in
       the label text, so the information survives; only the colour cue
       does not. Not fixable without a Checkbox tint input, out of scope
       for a call-site migration. */
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
    .message { color: var(--text-secondary); font-size: var(--text-table); }
  `,
})
export class LogsTab {
  protected readonly store = inject(SystemStore);

  protected readonly logsAsync = computed(() =>
    asyncInputs(
      { data: this.store.logs, loading: this.store.logsLoading, error: this.store.logsError },
      { isEmpty: (logs) => !logs.content },
    ),
  );

  protected readonly sources: LogSource[] = ['bot', 'admin'];

  /** SR57 — driven off the store's constants, so the filter can never offer
   *  a level the parser does not recognise. */
  protected readonly levels = LOG_LEVELS;
  /** `sb-select`'s options, string-valued -- the line count is the value
   *  itself, not just a label. */
  protected readonly lineOptions: SelectOption[] = LOG_LINE_CHOICES.map((choice) => ({
    value: String(choice),
    label: String(choice),
  }));

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
