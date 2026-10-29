import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, map } from 'rxjs';

import { Icon } from '../ui/icon';
import { PHONE_TABS, navEntryFor } from './nav';

/**
 * The phone's bottom tab bar -- v195 Phase 3.
 *
 * Dashboard · Watchlist · Trades · Risk, then More. Risk is a tab so the
 * halt is two taps from anywhere: the killswitch chip in the top bar shows
 * the state, Risk's page header holds the control. The current tab comes
 * from the nav model, not RouterLinkActive, so a plan detail lights Trades
 * and a page the bar does not hold lights More.
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
  imports: [RouterLink, Icon],
  template: `
    <nav class="tabs" aria-label="Main pages">
      @for (tab of tabs; track tab.path) {
        <a
          class="tab"
          [routerLink]="tab.path"
          [class.active]="activePath() === tab.path"
          [attr.aria-current]="activePath() === tab.path ? 'page' : null"
        >
          <span class="glyph" aria-hidden="true"><sb-icon [name]="tab.icon" /></span>
          <span class="tab-label">{{ tab.label }}</span>
        </a>
      }
      <button
        type="button"
        class="tab more"
        [class.active]="moreActive()"
        aria-haspopup="dialog"
        [attr.aria-expanded]="moreOpen()"
        (click)="moreRequested.emit()"
      >
        <span class="glyph" aria-hidden="true"><sb-icon name="more" /></span>
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
    .tabs {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      box-sizing: border-box;
      height: calc(56px + env(safe-area-inset-bottom));
      padding-bottom: env(safe-area-inset-bottom);
      background: var(--surface);
      border-top: 1px solid var(--border);
    }
    /* A 2px top edge that the active tab fills with the accent: a bar plus
       the label stepping to full text, never colour alone. */
    .tab {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 2px;
      min-height: var(--hit-min);
      margin: 0;
      padding: 0;
      border: 0;
      border-top: 2px solid transparent;
      background: none;
      color: var(--text-muted);
      font: inherit;
      font-size: var(--text-micro);
      text-decoration: none;
      cursor: pointer;
      transition: color var(--transition), border-color var(--transition);
    }
    .tab.active { color: var(--text); border-top-color: var(--accent); }
    .glyph { display: inline-flex; line-height: 0; }
  `,
})
export class PhoneTabBar {
  /** Whether the shell's More sheet is open (it owns that state). */
  readonly moreOpen = input(false);
  readonly moreRequested = output<void>();

  protected readonly tabs = PHONE_TABS;

  private readonly router = inject(Router);
  private readonly url = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      map(() => this.router.url),
    ),
    { initialValue: this.router.url },
  );

  /** The tab the current page belongs to; null off the nav (the /ui gallery). */
  protected readonly activePath = computed(() => navEntryFor(this.url())?.entry.path ?? null);

  protected readonly moreActive = computed(() => {
    if (this.moreOpen()) return true;
    const path = this.activePath();
    return path !== null && !this.tabs.some((tab) => tab.path === path);
  });
}
