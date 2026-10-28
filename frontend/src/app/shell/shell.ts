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
import { MotionMode, MotionService } from '../ui/motion/motion.service';
import { CLOCK } from '../ui/clock';
import { ViewportService } from '../ui/breakpoints';
import { Button } from '../ui/button';
import { DensityService } from '../ui/density.service';
import { Hint } from '../ui/hint';
import { Icon } from '../ui/icon';
import { NavIndicator } from './nav-indicator';
import { ProfileMenu } from './profile-menu';
import { RouteLoadingService } from '../routing/route-loading.service';
import { RouteRefreshService } from '../routing/route-refresh.service';
import { SessionStore } from '../stores/session.store';
import { Breadcrumb } from './breadcrumb';
import { FreshnessChip } from './freshness-chip';
import { KillswitchChip } from './killswitch-chip';
import { MoreSheet } from './more-sheet';
import { CommandPalette, isPaletteShortcut, shortcutLabel } from './palette/command-palette';
import { PhoneTabBar } from './phone-tab-bar';
import { ConnectionStatus } from './connection-status';
import { NAV_GROUPS } from './nav';
import { ScanProgressStrip } from './scan-progress';
import { Tape } from './tape/tape';
import { ToastHost } from './toast-host';

/**
 * Icon rail, top bar, connection status, toast host, outlet -- v195 Phase 3.
 *
 * Rendered by App instead of the login form -- it is not itself routed, so
 * there is no state in which the shell exists without a session.
 *
 * **One rail state.** The rail is always 48px and always icons: there is no
 * expanded sidebar, no overlay and no stored collapse choice. The server's
 * pre-v195 sidebar preference is left in place (an older image reads it
 * again on rollback) and is never read or written here.
 *
 * **Scan and bot status live here and nowhere else.** They were on the old
 * Dashboard as well as the header, which meant two renderings of one fact
 * that could disagree; the design system moves them to the shell precisely
 * so a workspace cannot own a second copy. Do not add them to Dashboard.
 *
 * **No heading.** The top bar leads with `sb-breadcrumb`, a labelled list;
 * the page's one `<h1>` is `sb-page`'s (correction 9).
 */
/** The zoom steps the control offers, as root-font percentages. A closed
 *  set so a stored value can be validated against it. */
const ZOOM_CHOICES = [90, 100, 110, 125] as const;
const ZOOM_DEFAULT = 100;

@Component({
  selector: 'sb-shell',
  imports: [
    RouterOutlet, RouterLink, RouterLinkActive, ConnectionStatus, ToastHost,
    ScanProgressStrip, Icon, Hint, Breadcrumb, KillswitchChip, FreshnessChip, ProfileMenu, NavIndicator, Tape,
    Button, PhoneTabBar, MoreSheet, CommandPalette,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './shell.html',
  styleUrl: './shell.css',
  host: { '(document:keydown)': 'onGlobalKeydown($event)' },
})
export class Shell {
  private readonly api = inject(ApiClient);
  private readonly events = inject(EventStream);
  protected readonly session = inject(SessionStore);
  protected readonly connection = inject(ConnectionStore);
  private readonly preferences = inject(PreferencesStore);
  protected readonly routeLoading = inject(RouteLoadingService);
  private readonly routeRefresh = inject(RouteRefreshService);
  private readonly tape = inject(TapeStore);
  private readonly marketIndex = inject(MarketIndexStore);
  protected readonly clock = inject(CLOCK);

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
   * The four rail groups (v195 §5.1), from the one nav model the phone bar,
   * the More sheet, the palette and the breadcrumb also read. The /ui
   * gallery is deliberately absent: a developer surface, reachable by URL.
   */
  protected readonly navGroups = NAV_GROUPS;

  /** The rail foot's version hint: the words the old footer block showed,
   *  on one line. Empty until the first /health answer; the template
   *  renders no hint until then. */
  protected readonly versionText = computed(() => {
    const versions = this.connection.versions();
    if (!versions) return '';
    const updated = this.connection.lastUpdated();
    return `ui ${versions.ui} · bot ${versions.bot}${updated ? ` · updated ${updated}` : ''}`;
  });

  /* -- v195 Phase 3: the phone shell ---------------------------------- */

  /** Below 640px the rail gives way to the bottom tab bar and More sheet. */
  protected readonly isPhone = inject(ViewportService).isPhone;

  /** The More sheet's open state. The shell owns it: the tab bar asks, the
   *  sheet reports a close, and a wider window forgets it. */
  protected readonly moreOpen = signal(false);

  /** A sheet left open on a phone must not reappear when the window is
   *  narrowed again later: leaving phone width closes it. */
  private readonly closeMoreOffPhone = effect(() => {
    if (!this.isPhone()) untracked(() => this.moreOpen.set(false));
  });

  protected toggleMore(): void {
    this.moreOpen.update((open) => !open);
  }

  protected closeMore(): void {
    this.moreOpen.set(false);
  }

  /**
   * The phone's search icon and the More sheet's search field both land
   * here (V195-18); both open the command palette, which closes the sheet
   * first.
   */
  protected onSearchRequested(): void {
    this.openPalette();
  }

  /* -- v195 §3.1: the command palette --------------------------------- */

  /** The palette's open state; the shell owns it, like the More sheet's. */
  protected readonly paletteOpen = signal(false);

  /** The trigger's shortcut hint for this platform. */
  protected readonly paletteShortcut = shortcutLabel(typeof navigator === 'undefined' ? '' : navigator.platform);

  /**
   * Every entry point lands here: the top-bar trigger, Ctrl/⌘K, `/`, and
   * through onSearchRequested() the phone's search icon and the More
   * sheet's field. The sheet closes first, so the palette never opens under
   * it; shell.html mounts the palette after the sheet, so the sheet hands
   * focus back before the palette records where to return it.
   */
  protected openPalette(): void {
    this.closeMore();
    this.paletteOpen.set(true);
  }

  protected closePalette(): void {
    this.paletteOpen.set(false);
  }

  /** Ctrl/⌘K and `/` (spec §3.1). Ignored while the palette is already
   *  open, and while a native dialog owns the top layer (a confirm dialog or
   *  drawer makes the page behind it inert). */
  protected onGlobalKeydown(event: KeyboardEvent): void {
    if (this.paletteOpen() || !isPaletteShortcut(event)) return;
    if (document.querySelector('dialog[open]')) return;
    event.preventDefault();
    this.openPalette();
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

  /* -- v168: Motion preference --------------------------------------- */

  /**
   * The one TS source of the Motion mode (spec v168 §1). Persisted through
   * `PreferencesStore` under `shell.motion` by `MotionService.set`, never
   * `localStorage` -- the same plan v21 Global Constraint as `shell.zoom`.
   * The OS reduced-motion setting is deliberately not read (spec D2).
   */
  protected readonly motion = inject(MotionService);

  /** Narrowed for the profile menu: `pending` is a load state, not a choice,
   *  so the control shows the default (On) until preferences arrive. */
  protected readonly motionMode = computed<MotionMode>(() => {
    const mode = this.motion.mode();
    return mode === 'pending' ? 'on' : mode;
  });

  /**
   * Written to `<html>` for the same reason as `--text-scale` above: dialogs,
   * the drawer and the toast host sit outside this component. CSS reads only
   * this attribute; TS reads only `MotionService`.
   */
  private readonly applyMotion = effect(() => {
    document.documentElement.dataset['motion'] = this.motion.mode();
  });

  /** Row density for this device (v195 §1.4): read by the profile menu,
   *  written through DensityService, which owns `ui.density` and the
   *  `data-density` attribute on <html>. */
  protected readonly density = inject(DensityService);

  protected setMotion(mode: MotionMode): void {
    this.motion.set(mode);
  }

  /**
   * Killswitch state, owned by the shell rather than by RiskStore.
   *
   * The spec requires it to be visible from every workspace, and RiskStore
   * is provided on the /risk route -- it does not exist while you are
   * looking at Trades. This is one boolean re-read on a `risk` event, not a
   * second copy of the risk workspace's state.
   *
   * Three-valued (v195): `null` until the first answer, so the top bar's
   * killswitch chip says nothing rather than a guessed "Armed".
   */
  protected readonly killswitchOn = signal<boolean | null>(null);

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
    this.api.killswitch().subscribe({
      next: (result) => this.killswitchOn.set(result.killswitch.on),
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
