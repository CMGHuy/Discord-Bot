import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { NotificationHealth } from '../../api/models';
import { Panel } from '../../ui/layout';

function ageText(value: number | null): string {
  if (value === null) return 'Unknown';
  if (value < 60) return `${Math.floor(value)} sec`;
  return `${Math.floor(value / 60)} min`;
}

@Component({
  selector: 'sb-notification-health-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="Lifecycle notifications">
      <div class="content" [attr.role]="warning() ? 'alert' : 'status'" aria-atomic="true">
        @if (current(); as status) {
          @if (warning()) {
            <p class="warning">Delivery needs attention: notifications are blocked or have waited over 15 minutes.</p>
          } @else if (status.pending_count === 0) {
            <p>No pending notifications.</p>
          } @else {
            <p>Notifications are waiting for delivery.</p>
          }
          <dl>
            <div><dt>Pending</dt><dd class="num">{{ status.pending_count }}</dd></div>
            <div><dt>Blocked</dt><dd class="num">{{ status.blocked_count }}</dd></div>
            <div><dt>Oldest pending</dt><dd>{{ oldest() }}</dd></div>
          </dl>
        } @else {
          <p>Notification delivery status unavailable.</p>
        }
        <p class="explain">
          Close and cancel notices remain pending until delivery is recorded and retry automatically.
          A repeated Discord notice carries the same event ID in its footer.
        </p>
      </div>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .content { display: grid; gap: var(--space-10); font-size: var(--text-table); line-height: 1.5; }
    p { margin: 0; overflow-wrap: anywhere; }
    .warning { color: var(--neg); font-weight: 600; }
    .explain, dt { color: var(--text-secondary); }
    dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-10); margin: 0; }
    dl > div { min-width: 0; }
    dt, dd { margin: 0; overflow-wrap: anywhere; }
    @media (max-width: 639px) {
      dl { grid-template-columns: minmax(0, 1fr); }
      dl > div { display: flex; gap: var(--space-10); align-items: baseline; flex-wrap: wrap; }
    }
  `,
})
export class NotificationHealthPanel {
  readonly health = input<NotificationHealth | null>(null);
  readonly stale = input(false);
  protected readonly current = computed(() => this.stale() ? null : this.health());
  protected readonly warning = computed(() => {
    const value = this.current();
    return !!value && (value.blocked_count > 0 || (value.oldest_pending_age_seconds ?? 0) > 900);
  });
  protected readonly oldest = computed(() => {
    const value = this.current();
    if (!value || value.pending_count === 0) return 'None';
    return ageText(value.oldest_pending_age_seconds);
  });
}
