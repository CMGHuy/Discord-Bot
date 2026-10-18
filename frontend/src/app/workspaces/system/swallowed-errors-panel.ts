import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { SwallowedRow, SystemHealth } from '../../api/models';
import { ABSENT, age, dateTime, num } from '../../ui/format';
import { Panel } from '../../ui/layout';

export interface SwallowedLine {
  process: string;
  tag: string;
  count: string;
  lastSeen: string;
  /** Full timestamp, for the cell's tooltip. */
  lastSeenAt: string;
  lastError: string;
}

const byCount = (a: SwallowedRow, b: SwallowedRow): number =>
  b.count - a.count || a.process.localeCompare(b.process) || a.tag.localeCompare(b.tag);

function lastSeen(iso: string | null, now: number): string {
  const ago = age(iso, now);
  return ago === ABSENT ? ABSENT : `${ago} ago`;
}

/** Highest count first; ties by process, then tag, so a refresh never
 *  reshuffles equal rows. */
export function swallowedLines(health: SystemHealth | null, now = Date.now()): SwallowedLine[] {
  if (!health) return [];
  return [...health.swallowed].sort(byCount).map((row) => ({
    process: row.process,
    tag: row.tag,
    count: num(row.count, 0),
    lastSeen: lastSeen(row.last_at, now),
    lastSeenAt: dateTime(row.last_at),
    lastError: row.last_error ?? ABSENT,
  }));
}

/**
 * v148 — errors the bot and the admin caught and carried on from, per call
 * site. A non-zero count is not an outage. It is the place a silent
 * failure (the 2026-09-14 lxml outage sat inside one of these) becomes
 * visible before anything downstream looks wrong.
 */
@Component({
  selector: 'sb-swallowed-errors-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="Swallowed errors">
      <p class="explain">
        Errors the bot and the admin caught and carried on from, counted per call site. Counts start at zero when a process starts.
        {{ sinceText() }}
      </p>
      @if (lines().length) {
        <div class="scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Process</th>
                <th scope="col">Call site</th>
                <th scope="col" class="right">Count</th>
                <th scope="col">Last seen</th>
                <th scope="col">Last error</th>
              </tr>
            </thead>
            <tbody>
              @for (line of lines(); track line.process + ':' + line.tag) {
                <tr>
                  <td>{{ line.process }}</td>
                  <td class="num">{{ line.tag }}</td>
                  <td class="num right">{{ line.count }}</td>
                  <td [attr.title]="line.lastSeenAt">{{ line.lastSeen }}</td>
                  <td class="last-error">{{ line.lastError }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p class="explain">None since the processes started.</p>
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .explain {
      max-width: 72ch;
      margin: 0 0 var(--space-10);
      color: var(--text-secondary);
      font-size: var(--text-table);
      line-height: 1.5;
    }
    .scroll { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    th {
      padding: var(--space-6) var(--space-8);
      border-bottom: 1px solid var(--border);
      color: var(--text-secondary);
      font-weight: 500;
      text-align: left;
      white-space: nowrap;
    }
    td {
      padding: var(--space-6) var(--space-8);
      border-bottom: 1px solid var(--border);
      color: var(--text);
      white-space: nowrap;
    }
    .right { text-align: right; }
    .last-error { min-width: 24ch; color: var(--text-secondary); white-space: normal; }
  `,
})
export class SwallowedErrorsPanel {
  readonly health = input<SystemHealth | null>(null);

  protected readonly lines = computed(() => swallowedLines(this.health()));
  protected readonly sinceText = computed(() => {
    const since = this.health()?.bot_counts_since;
    return since
      ? `Bot counts since ${dateTime(since)}.`
      : 'The bot has not reported its counts yet.';
  });
}
