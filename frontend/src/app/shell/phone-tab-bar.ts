import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, map } from 'rxjs';

import { HINT_HOVER_DELAY_MS, Hint } from '../ui/hint';
import { Icon } from '../ui/icon';
import { LongPress } from '../ui/long-press';
import { NAV_ENTRIES, phoneTabPathFor } from './nav';
import { TabBarPrefs } from './tab-bar-prefs';

/**
 * The phone's bottom tab bar -- v195 Phase 3, v240 §6.
 *
 * The pages come from TabBarPrefs: by default Home (the Dashboard) ·
 * Watchlist · Trades · Calendar, then More; the partner may keep 1 to 4
 * pages, the Dashboard always first. The current tab comes from the nav
 * model, not RouterLinkActive, so a plan detail lights Trades and a page
 * the bar does not hold lights More.
 *
 * The tabs share the width equally, 2 to 5 of them. The active tab shows
 * the --accent-soft pill behind an --accent icon, and its label steps to
 * full text: never colour alone.
 *
 * Press and hold (v240 §6): a 500ms touch on a tab opens its name above it
 * (sbLongPress -> sb-hint openPinned(), placement "above") and navigates
 * nowhere; it stays until the next touch or Escape. A mouse hovers instead,
 * after HINT_HOVER_DELAY_MS. The name is the rail's, so Home reads
 * "Dashboard" (Decision 9). More has no hint: its label is its name.
 *
 * Each glyph sits in an aria-hidden span: `sb-icon` names itself with a
 * native title, which would otherwise join the visible label in the tab's
 * accessible name ("Trades Trades").
 *
 * Fixed under the page at `z-index: 8`, below the toasts (10), which may
 * cover it while they show; the More sheet (30/31) covers both.
 */
@Component({
  selector: 'sb-phone-tab-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Icon, Hint, LongPress],
  template: `
    <nav class="tabs" aria-label="Main pages">
      @for (tab of tabs(); track tab.path) {
        <a
          #link
          class="tab"
          [routerLink]="tab.path"
          [class.active]="activePath() === tab.path"
          [attr.aria-current]="activePath() === tab.path ? 'page' : null"
          sbLongPress
          (longPress)="hint.openPinned()"
        >
          <span class="glyph" aria-hidden="true"><sb-icon [name]="tab.icon" [size]="24" /></span>
          <span class="tab-label">{{ tab.label }}</span>
        </a>
        <sb-hint #hint [anchor]="link" [text]="railLabelOf(tab.path)" placement="above" [openDelay]="hintDelay" />
      }
      <button
        type="button"
        class="tab more"
        [class.active]="moreActive()"
        aria-haspopup="dialog"
        [attr.aria-expanded]="moreOpen()"
        (click)="moreRequested.emit()"
      >
        <span class="glyph" aria-hidden="true"><sb-icon name="more" [size]="24" /></span>
        <span class="tab-label">More</span>
      </button>
    </nav>
  `,
  styles: `
    :host {
      position: fixed;
      inset: auto 0 0 0;
      z-index: 8;
      display: block;
    }
    /* One equal column per tab, 2 to 5 of them; five fit a 320px phone. */
    .tabs {
      display: grid;
      grid-auto-flow: column;
      grid-auto-columns: minmax(0, 1fr);
      box-sizing: border-box;
      height: calc(56px + env(safe-area-inset-bottom));
      padding-bottom: env(safe-area-inset-bottom);
      background: var(--surface);
      border-top: 1px solid var(--border);
    }
    .tab {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 2px;
      min-width: 0;
      min-height: var(--hit-min);
      margin: 0;
      padding: 0 var(--space-4);
      border: 0;
      background: none;
      color: var(--text-muted);
      font: inherit;
      text-decoration: none;
      cursor: pointer;
      transition: color var(--transition);
    }
    .tab.active { color: var(--text); }
    /* The pill the active tab fills: --accent-soft behind an --accent icon (v240 §6). */
    .glyph {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 48px;
      height: 28px;
      border-radius: var(--pill-radius);
      line-height: 0;
      transition: background var(--transition), color var(--transition);
    }
    .tab.active .glyph { background: var(--accent-soft); color: var(--accent); }
    /* The 12px floor (--text-micro, Decision 8) at weight 600; a long label
       truncates instead of widening its column. */
    .tab-label {
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: var(--text-micro);
      font-weight: 600;
    }
  `,
})
export class PhoneTabBar {
  /** Whether the shell's More sheet is open (it owns that state). */
  readonly moreOpen = input(false);
  readonly moreRequested = output<void>();

  protected readonly tabs = inject(TabBarPrefs).tabs;

  /** The hover delay the rail's hints use too (Decision 6). */
  protected readonly hintDelay = HINT_HOVER_DELAY_MS;

  /** A tab's tooltip is its page's rail name: the Home tab reads "Dashboard". */
  protected railLabelOf(path: string): string {
    return NAV_ENTRIES.find((entry) => entry.path === path)?.label ?? path;
  }

  private readonly router = inject(Router);
  private readonly url = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      map(() => this.router.url),
    ),
    { initialValue: this.router.url },
  );

  /** The tab the current page belongs to; null off the nav (the /ui gallery). */
  protected readonly activePath = computed(() => phoneTabPathFor(this.url(), this.tabs()));

  protected readonly moreActive = computed(() => {
    if (this.moreOpen()) return true;
    const path = this.activePath();
    return path !== null && !this.tabs().some((tab) => tab.path === path);
  });
}
