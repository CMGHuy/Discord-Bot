import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Panel } from '../../../ui/layout';
import { Icon, IconName, STATUS_ICON } from '../../../ui/icon';
import { DirectionArrow } from '../../../ui/direction-arrow';
import { dateTime } from '../../../ui/format';
import { ActivityEvent } from './activity';

/** The word behind each STATUS_ICON glyph — same five statuses, human
 *  words instead of icon names ('opened' the glyph reads as "Open" the
 *  status, not literally the word "opened"). */
const STATUS_LABEL: Record<string, string> = {
  PENDING: 'Pending',
  ACTIVE: 'Open',
  PARTIAL: 'Partial',
  CLOSED: 'Closed',
  CANCELLED: 'Cancelled',
  EXPIRED: 'Cancelled',
};

/** What just happened, from the trade records themselves — v85 D15. */
@Component({
  selector: 'sb-recent-activity',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Icon, DirectionArrow, RouterLink],
  template: `
    <sb-panel heading="Recent activity">
      <a panel-actions class="all-link sb-hit" routerLink="/trades">View all</a>

      @if (events().length) {
        <ul class="feed">
          @for (event of events(); track event.id) {
            <li [class]="'event ' + event.kind">
              <!-- A native button supplies keyboard activation and focus. -->
              <button type="button" class="event-hit" aria-haspopup="dialog"
                      (click)="eventActivate.emit(event)">
                <sb-icon [name]="icon(event)" [title]="statusLabel(event)"
                         [attr.aria-label]="statusLabel(event)" />
                <sb-direction-arrow [direction]="event.direction" />
                <span class="ticker">{{ event.ticker }}</span>
                <span class="detail" [class.pos]="(event.r ?? 0) > 0" [class.neg]="(event.r ?? 0) < 0">{{ event.detail }}</span>
                <time class="at" [attr.datetime]="event.at">{{ fmt(event.at) }}</time>
              </button>
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
    .event { display: block; }
    /* Mixed text faces share a baseline; glyphs centre independently.
       --control-h reaches 44px on touch devices and below 1024px. */
    .event-hit {
      display: grid;
      grid-template-columns: auto auto auto 1fr auto;
      align-items: baseline;
      gap: var(--space-8);
      width: 100%;
      min-height: var(--control-h);
      padding: 0;
      background: none;
      border: 0;
      border-radius: var(--radius-sm);
      color: inherit;
      font: inherit;
      font-size: var(--text-table);
      text-align: left;
      cursor: pointer;
    }
    .event-hit sb-icon { align-self: center; }
    .event-hit sb-direction-arrow { align-self: center; }
    .event-hit:hover .ticker { text-decoration: underline; }
    .event-hit:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    /* Neutral on purpose (2026-09-14): the icon's SHAPE is the status now
       (pending/opened/partial/closed/cancelled -- see icon.ts's
       STATUS_ICON), not a kind-coloured up/down arrow. Colour stays out of
       it so this cannot drift back into implying win/loss, which a plan
       simply having opened or closed is not. */
    sb-icon { color: var(--text-muted); cursor: inherit; }
    .ticker { font-family: var(--font-mono); color: var(--text); font-weight: 600; }
    /* 1fr with no min-width: 0 is a min-content floor -- a long detail string
       widens the row instead of ellipsising inside it (v95 A4). */
    .detail {
      color: var(--text-secondary);
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .detail.pos { color: var(--pos); }
    .detail.neg { color: var(--neg); }
    .at { color: var(--text-faint); font-variant-numeric: tabular-nums; white-space: nowrap; }
    .empty { margin: 0; color: var(--text-faint); font-size: var(--text-chip); }
    .all-link { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .all-link:hover { text-decoration: underline; }
  `,
})
export class RecentActivity {
  readonly events = input<readonly ActivityEvent[]>([]);
  /** Dashboard opens its drawer from the event's tradeId; this panel emits only. */
  readonly eventActivate = output<ActivityEvent>();
  protected fmt = dateTime;

  /** Falls back to `opened` for any status outside the five known ones,
   *  rather than rendering nothing -- a row IS a plan, and the closest
   *  reading of "unrecognised state" is still "something is live". */
  protected icon(event: ActivityEvent): IconName {
    return STATUS_ICON[event.status.toUpperCase()] ?? 'opened';
  }

  /** Matches `icon()`'s own fallback -- an unrecognised status still gets
   *  a word, not an empty tooltip. */
  protected statusLabel(event: ActivityEvent): string {
    return STATUS_LABEL[event.status.toUpperCase()] ?? 'Open';
  }
}
