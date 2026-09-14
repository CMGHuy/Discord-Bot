import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Panel } from '../../../ui/layout';
import { Icon, IconName } from '../../../ui/icon';
import { DirectionArrow } from '../../../ui/direction-arrow';
import { dateTime } from '../../../ui/format';
import { ActivityEvent } from './activity';

/** One icon per event kind, shared with the Open Positions panel's status
 *  icons (`status-cell.ts`) so the two panels read as one vocabulary rather
 *  than each inventing its own. */
const KIND_ICON: Record<ActivityEvent['kind'], IconName> = {
  opened: 'opened',
  closed: 'closed',
  cancelled: 'cancelled',
};

/** What just happened, from the trade records themselves — v85 D15. */
@Component({
  selector: 'sb-recent-activity',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Icon, DirectionArrow, RouterLink],
  template: `
    <sb-panel heading="Recent activity">
      <a panel-actions class="all-link" routerLink="/trades">View all</a>

      @if (events().length) {
        <ul class="feed">
          @for (event of events(); track event.id) {
            <li [class]="'event ' + event.kind">
              <sb-icon [name]="icon(event)" />
              <sb-direction-arrow [direction]="event.direction" />
              <span class="ticker">{{ event.ticker }}</span>
              <span class="detail">{{ event.detail }}</span>
              <time class="at" [attr.datetime]="event.at">{{ fmt(event.at) }}</time>
            </li>
          }
        </ul>
      } @else {
        <p class="empty">No activity yet — it fills as plans open and close.</p>
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .feed { margin: 0; padding: 0; list-style: none; display: grid; gap: var(--space-8); }
    .event {
      display: grid;
      grid-template-columns: auto auto auto 1fr auto;
      align-items: baseline;
      gap: var(--space-8);
      font-size: var(--text-table);
    }
    /* The icon carries the kind as a shape; colour is the second cue, never
       the only one. */
    .event.opened sb-icon { color: var(--accent); }
    .event.closed sb-icon { color: var(--pos); }
    .event.cancelled sb-icon { color: var(--text-faint); }
    .ticker { font-family: var(--font-mono); color: var(--text); font-weight: 600; }
    .detail { color: var(--text-secondary); }
    .at { color: var(--text-faint); font-variant-numeric: tabular-nums; white-space: nowrap; }
    .empty { margin: 0; color: var(--text-faint); font-size: var(--text-chip); }
    .all-link { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .all-link:hover { text-decoration: underline; }
  `,
})
export class RecentActivity {
  readonly events = input<readonly ActivityEvent[]>([]);
  protected fmt = dateTime;
  protected icon(event: ActivityEvent): IconName {
    return KIND_ICON[event.kind];
  }
}
