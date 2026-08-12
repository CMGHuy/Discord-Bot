import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ApiClient } from '../api/api-client';
import { SessionStore } from '../stores/session.store';
import { ConnectionStatus, StreamState } from './connection-status';
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
  protected readonly session = inject(SessionStore);

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

  // Wired to ConnectionStore in NG31. Until then the indicator renders its
  // initial state honestly rather than claiming to be live.
  protected readonly streamState = signal<StreamState>('connecting');
  protected readonly botAlive = signal<boolean | null>(null);

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
    this.refreshKillswitch();
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
