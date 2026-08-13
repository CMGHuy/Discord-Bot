import { ChangeDetectionStrategy, Component, effect, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { ConnectionStore } from '../stores/connection.store';
import { PreferencesStore } from '../stores/preferences.store';
import { SessionStore } from '../stores/session.store';
import { ConnectionStatus } from './connection-status';
import { ToastHost } from './toast-host';

interface NavEntry {
  path: string;
  label: string;
}

/**
 * Sidebar, workspace header, connection status, toast host, outlet.
 *
 * Rendered by App instead of the login form -- it is not itself routed, so
 * there is no state in which the shell exists without a session.
 *
 * **Scan and bot status live here and nowhere else.** They were on the old
 * Dashboard as well as the header, which meant two renderings of one fact
 * that could disagree; the design system moves them to the shell precisely
 * so a workspace cannot own a second copy. Do not add them to Cockpit.
 */
@Component({
  selector: 'sb-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ConnectionStatus, ToastHost],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './shell.html',
  styleUrl: './shell.css',
})
export class Shell {
  private readonly api = inject(ApiClient);
  private readonly events = inject(EventStream);
  protected readonly session = inject(SessionStore);
  protected readonly connection = inject(ConnectionStore);
  private readonly preferences = inject(PreferencesStore);

  /** The six workspaces, in the IA's order: what is true now, then the
   *  entities, then the analysis, then the two administrative ones. */
  protected readonly nav: NavEntry[] = [
    { path: '/cockpit', label: 'Cockpit' },
    { path: '/trades', label: 'Trades' },
    { path: '/analytics', label: 'Analytics' },
    { path: '/universe', label: 'Universe' },
    { path: '/risk', label: 'Risk' },
    { path: '/system', label: 'System' },
  ];

  /**
   * Killswitch state, owned by the shell rather than by RiskStore.
   *
   * The spec requires it to be visible from every workspace, and RiskStore
   * is provided on the /risk route -- it does not exist while you are
   * looking at Trades. This is one boolean re-read on a `risk` event, not a
   * second copy of the risk workspace's state.
   */
  protected readonly killswitchOn = signal(false);

  constructor() {
    // Read once, here rather than in an app initializer: preferences are
    // only meaningful once authenticated, and the shell is the thing that
    // exists exactly when that is true.
    this.preferences.load();

    // Reading the counter inside the effect is the subscription. The first
    // run is also the initial load, so the load path and the refetch path
    // are the same code and cannot drift apart.
    const risk = this.events.changes('risk');
    effect(() => {
      risk();
      this.refreshKillswitch();
    });
  }

  protected refreshKillswitch(): void {
    this.api.risk().subscribe({
      next: (risk) => this.killswitchOn.set(risk.killswitch.on),
      // Silent: a failure here means the risk endpoint is unhappy, which
      // the Risk workspace will report properly. A toast on every shell
      // load would be noise on top of an error that is already visible.
      error: () => undefined,
    });
  }

  protected logout(): void {
    void this.session.logout();
  }
}
