import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { ConnectionStore } from '../stores/connection.store';
import { PreferencesStore } from '../stores/preferences.store';
import { ViewportService } from '../ui/breakpoints';
import { Button } from '../ui/button';
import { Select, SelectOption } from '../ui/form-controls';
import { Icon, IconName } from '../ui/icon';
import { ProfileMenu } from './profile-menu';
import { SessionStore } from '../stores/session.store';
import { ConnectionStatus } from './connection-status';
import { ToastHost } from './toast-host';

interface NavEntry {
  path: string;
  label: string;
  icon: IconName;
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
 * so a workspace cannot own a second copy. Do not add them to Dashboard.
 */
/** The zoom steps the control offers, as root-font percentages. A closed
 *  set so a stored value can be validated against it. */
const ZOOM_CHOICES = [90, 100, 110, 125] as const;
const ZOOM_DEFAULT = 100;

@Component({
  selector: 'sb-shell',
  imports: [
    RouterOutlet, RouterLink, RouterLinkActive, ConnectionStatus, ToastHost,
    Button, Icon, ProfileMenu, Select,
  ],
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
  private readonly viewport = inject(ViewportService);

  /** The seven workspaces, in the IA's order: what is true now, then the
   *  entities, then the two analysis views, then the two administrative
   *  ones. */
  protected readonly nav: NavEntry[] = [
    { path: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
    { path: '/trades', label: 'Trades', icon: 'trades' },
    { path: '/analytics', label: 'Analytics', icon: 'analytics' },
    { path: '/calendar', label: 'Calendar', icon: 'calendar' },
    { path: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
    { path: '/risk', label: 'Risk', icon: 'risk' },
    { path: '/system', label: 'System', icon: 'system' },
    { path: '/versions', label: 'Versions', icon: 'versions' },
  ];

  /**
   * Whether the sidebar is collapsed to its icon rail — spec v18 Decision 8.
   *
   * Two things decide this and they compose rather than compete: the viewport
   * forces the rail below `md`, and the user's toggle wins WITHIN a
   * breakpoint. Crossing a boundary re-applies the automatic state, which is
   * why the stored value is a preference and not the answer.
   */
  private readonly userCollapsed = signal<boolean | null>(null);

  protected readonly railed = computed(
    () => this.viewport.isNarrow() || (this.userCollapsed() ?? false),
  );

  /** Below `sm` the rail becomes an overlay that a navigation dismisses. */
  protected readonly overlay = computed(() => this.viewport.isPhone());
  protected readonly overlayOpen = signal(false);

  protected toggleSidebar(): void {
    // The new state is the opposite of what is on screen now. Written even
    // when the viewport is currently forcing the rail: the choice is about
    // how the user wants it, and it should be waiting for them when they
    // widen the window again.
    const collapsed = !this.railed();
    this.userCollapsed.set(collapsed);
    this.preferences.update((prefs) => ({
      ...prefs,
      'shell.sidebar': collapsed ? 'rail' : 'expanded',
    }));
  }

  protected openOverlay(): void {
    this.overlayOpen.set(true);
  }

  /** Any navigation closes the overlay — leaving it over the page someone
   *  just chose is the classic mobile-nav bug. */
  protected closeOverlay(): void {
    this.overlayOpen.set(false);
  }

  /* -- SR58: font zoom ------------------------------------------------ */

  /**
   * Root font scale, as a percentage.
   *
   * **Persisted through `PreferencesStore`, never `localStorage`** -- a
   * Global Constraint of plan v21. The Jinja version used `localStorage`
   * because it had no alternative; here that would make a setting follow the
   * browser rather than the account, so the same person on a second machine
   * gets a size they never chose and cannot find where it came from.
   */
  protected readonly zoom = signal(ZOOM_DEFAULT);

  /** `sb-select`'s options, string-valued -- `SelectOption` has no numeric
   *  form, and the zoom percent is the value itself, not just a label. */
  protected readonly zoomOptions: SelectOption[] = ZOOM_CHOICES.map((choice) => ({
    value: String(choice),
    label: `${choice}%`,
  }));

  /**
   * Applied to `<html>` rather than to a shell element, so it also reaches
   * anything rendered into a portal outside this component -- dialogs, the
   * drawer, the toast host.
   *
   * **`--text-scale`, not `font-size`.** This used to set the root font size
   * on the belief that the design tokens were `rem`-based. They are not:
   * every `--text-*` in `styles/tokens.css` is an absolute px, so the root
   * font size reached nothing and the control was inert -- you could pick
   * 125% and watch the page not move. The tokens now multiply through this
   * custom property, which is the thing that actually resizes the type.
   */
  private readonly applyZoom = effect(() => {
    document.documentElement.style.setProperty(
      '--text-scale',
      String(this.zoom() / 100),
    );
  });

  protected setZoom(percent: number): void {
    this.zoom.set(percent);
    this.preferences.update((prefs) => ({ ...prefs, 'shell.zoom': percent }));
  }

  private readonly applyStoredZoom = effect(() => {
    if (!this.preferences.isLoaded()) return;
    const stored = this.preferences.values()['shell.zoom'];
    untracked(() => {
      // Validated, not trusted: a stale or hand-edited preference must fall
      // back to 100% rather than set the root font to `NaN%` and collapse
      // every rem-based size in the app at once.
      if (typeof stored === 'number' && ZOOM_CHOICES.includes(stored as never)) {
        this.zoom.set(stored);
      }
    });
  });

  private readonly applyStoredSidebar = effect(() => {
    if (!this.preferences.isLoaded()) return;
    const stored = this.preferences.values()['shell.sidebar'];
    untracked(() => {
      if (stored === 'rail') this.userCollapsed.set(true);
      else if (stored === 'expanded') this.userCollapsed.set(false);
    });
  });

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
