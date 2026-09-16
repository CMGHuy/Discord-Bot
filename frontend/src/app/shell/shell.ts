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
import { MarketIndexStore } from '../stores/market-index.store';
import { PreferencesStore } from '../stores/preferences.store';
import { TapeStore } from '../stores/tape.store';
import { ViewportService } from '../ui/breakpoints';
import { Button } from '../ui/button';
import { CLOCK } from '../ui/clock';
import { Icon, IconName } from '../ui/icon';
import { ProfileMenu } from './profile-menu';
import { RouteLoadingService } from '../routing/route-loading.service';
import { RouteRefreshService } from '../routing/route-refresh.service';
import { RouteTitleService } from '../routing/route-title.service';
import { SessionStore } from '../stores/session.store';
import { ConnectionStatus } from './connection-status';
import { ScanProgressStrip } from './scan-progress';
import { Tape } from './tape/tape';
import { ToastHost } from './toast-host';

interface NavEntry {
  path: string;
  label: string;
  icon: IconName;
}

interface NavGroup {
  id: string;
  label: string;
  entries: NavEntry[];
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
    ScanProgressStrip,
    Button, Icon, ProfileMenu, Tape,
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
  protected readonly routeLoading = inject(RouteLoadingService);
  private readonly routeRefresh = inject(RouteRefreshService);
  protected readonly titles = inject(RouteTitleService);
  private readonly tape = inject(TapeStore);
  private readonly marketIndex = inject(MarketIndexStore);
  private readonly clock = inject(CLOCK);

  /** `Thu, Sep 11, 2026 16:58` -- one string, so the bar cannot render a date
   *  and a time from two different reads of the clock. Locale pinned to
   *  `en-US` rather than left to the host's default -- the same build
   *  otherwise renders "11 Sept 2026" on a machine set to en-GB, and a
   *  monitoring surface should not reformat itself by viewer. 24-hour and
   *  zero-padded via hourCycle: 4:58 next to a 16:58 market close reads as
   *  an error. */
  protected readonly now = computed(() => {
    const at = new Date(this.clock());
    const date = at.toLocaleDateString('en-US', {
      weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
    });
    const time = at.toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    });
    return `${date} ${time}`;
  });

  /**
   * Three groups, because eight flat entries stopped communicating.
   *
   * The split is by QUESTION, not by data type:
   *   MONITOR  what is happening right now
   *   REVIEW   what already happened
   *   SYSTEM   what the bot itself is doing
   *
   * The /ui gallery is deliberately absent — it is a developer surface,
   * reachable by URL.
   */
  protected readonly navGroups: NavGroup[] = [
    {
      id: 'nav-monitor',
      label: 'MONITOR',
      entries: [
        { path: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
        { path: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
        { path: '/risk', label: 'Risk', icon: 'risk' },
      ],
    },
    {
      id: 'nav-review',
      label: 'REVIEW',
      entries: [
        { path: '/trades', label: 'Trades', icon: 'trades' },
        { path: '/calendar', label: 'Calendar', icon: 'calendar' },
        { path: '/analytics', label: 'Analytics', icon: 'analytics' },
        { path: '/research', label: 'Research', icon: 'research' },
        { path: '/reports', label: 'Reports', icon: 'reports' },
      ],
    },
    {
      id: 'nav-system',
      label: 'SYSTEM',
      entries: [
        { path: '/system', label: 'System', icon: 'system' },
        { path: '/versions', label: 'Versions', icon: 'versions' },
      ],
    },
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

  /** One button, not a field -- SR76. Steps through `ZOOM_CHOICES` in
   *  order and wraps from the last back to the first, so repeatedly
   *  clicking cycles the whole set rather than needing a picker. */
  protected cycleZoom(): void {
    const index = ZOOM_CHOICES.indexOf(this.zoom() as (typeof ZOOM_CHOICES)[number]);
    const next = ZOOM_CHOICES[(index + 1) % ZOOM_CHOICES.length];
    this.setZoom(next);
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

    // Populates the tape before the first scan tick. `TapeStore` itself owns
    // the `scan` refetch (`withHooks` in `tape.store.ts`) -- this is not a
    // second subscription, just the initial load so Lane B is not empty on
    // first paint.
    this.tape.load();
    // Same reasoning for Lane A (`MarketIndexStore` owns its own `scan`
    // refetch) -- it now prices real indices through `/market/tape` rather
    // than rendering a third-party iframe, so it needs the same "don't wait
    // for the first scan tick" initial load Lane B always has.
    this.marketIndex.load();

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
