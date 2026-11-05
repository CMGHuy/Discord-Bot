import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { ConnectionStore } from '../../stores/connection.store';
import { LiveStore } from '../../stores/live.store';
import { Button } from '../../ui/button';
import { CLOCK } from '../../ui/clock';
import { Icon } from '../../ui/icon';
import { LiveActivitySection } from './live-activity-section';
import { LiveAwaitingSection } from './live-awaiting-section';
import { LiveBotSection } from './live-bot-section';
import { LiveHeatSection } from './live-heat-section';

/**
 * The Live dock -- v203 (spec v202 §4). Four sections: Bot, Plans awaiting
 * order, Portfolio heat, Activity. It reads LiveStore (/live) and the root
 * ConnectionStore and nothing else: never the risk workspace store, never /risk. The same
 * component is the docked column (desktop) and the sheet's body (tablet,
 * phone); only the head's control differs.
 */
@Component({
  selector: 'sb-live-dock',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, Icon, LiveBotSection, LiveAwaitingSection, LiveHeatSection, LiveActivitySection],
  template: `
    <div class="dock">
      <div class="dock-head">
        <span class="dock-title">Live</span>
        @if (variant() === 'docked') {
          <button sb-button variant="icon" type="button" class="dock-close sb-hit"
                  aria-label="Collapse the live dock" (click)="close.emit()">
            <sb-icon name="collapse" />
          </button>
        } @else {
          <button sb-button variant="secondary" type="button" class="dock-close sb-hit" (click)="close.emit()">Close</button>
        }
      </div>
      <sb-live-bot
        [botAlive]="connection.botAlive()" [botHealthy]="connection.botHealthy()" [scanRunning]="connection.scanRunning()"
        [lastSuccess]="connection.botLastSuccess()" [lastSeen]="connection.botLastSeen()" [streamState]="connection.state()"
        [marketActive]="connection.marketActive()" [killswitch]="live.killswitch()" [now]="now()" />
      <sb-live-awaiting [awaiting]="live.awaiting()" [loading]="live.loading()" [now]="now()" />
      <sb-live-heat [heat]="live.heat()" [loading]="live.loading()" [currency]="connection.currency()" [now]="now()"
                    (retry)="live.retry()" />
      <sb-live-activity [events]="live.events()" [meta]="live.eventsMeta()" [loading]="live.loading()"
                        [lastSuccess]="connection.botLastSuccess()" [now]="now()" [currency]="connection.currency()"
                        (retry)="live.retry()" />
    </div>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .dock { display: flex; flex-direction: column; gap: var(--space-14); padding: var(--space-14); }
    .dock-head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-8); }
    .dock-title { color: var(--text); font-size: var(--text-body); font-weight: 600; }
    .dock > :not(.dock-head) { padding-top: var(--space-14); border-top: 1px solid var(--border); }
  `,
})
export class LiveDock {
  readonly variant = input<'docked' | 'sheet'>('docked');
  // `close` is the pinned interface name (V203-7b/8 bind it); the native-event lint does not apply to a component output.
  // eslint-disable-next-line @angular-eslint/no-output-native
  readonly close = output<void>();

  protected readonly live = inject(LiveStore);
  protected readonly connection = inject(ConnectionStore);
  private readonly clock = inject(CLOCK);
  /** One clock for every section, so their ages agree to the tick. */
  protected readonly now = computed(() => new Date(this.clock()));
}
