import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';

import { FocusTrap } from '../ui/focus-trap';
import { Button } from '../ui/button';
import { Icon } from '../ui/icon';
import { SessionStore } from '../stores/session.store';
import { NAV_ENTRIES, NavEntry, PHONE_TABS, navEntriesFor } from './nav';

/** One group of the More sheet: a destination, and the pages it links to. */
export interface MoreGroup {
  id: string;
  label: string;
  links: { label: string; path: string }[];
}

/**
 * The destinations the phone's tab bar does not hold, in rail order (v202
 * §3), each with its sections as links; a single page links to itself.
 * Today: Insights (Analytics, Research, Reports) and, for the admin only,
 * System (Health, Versions). Trades' sections are reached from its section tabs.
 */
export function morePageGroups(
  entries: readonly NavEntry[] = NAV_ENTRIES,
  tabs: readonly NavEntry[] = PHONE_TABS,
): MoreGroup[] {
  const onBar = new Set(tabs.map((tab) => tab.path));
  return entries
    .filter((entry) => !onBar.has(entry.path))
    .map((entry) => ({
      id: `more-${entry.path.slice(1)}`,
      label: entry.label,
      links: (entry.sections ?? [entry]).map(({ label, path }) => ({ label, path })),
    }));
}

/**
 * The phone's More sheet -- v195 Phase 3: every destination the tab bar does
 * not hold, with its sections (v202 §3), and the search field.
 *
 * A modal bottom sheet: scrim, `role=dialog`, focus trapped while open and
 * returned to the More tab on close (FocusTrap restores what had focus).
 * Escape, the scrim, Close and choosing a page all close it; the shell owns
 * the open state. The search field is first, so it takes focus; it only
 * asks (`searchRequested`), and the shell closes the sheet and opens the
 * command palette (V195-20).
 *
 * `display: contents` on the host: the shell's grid must not give this
 * element a cell of its own.
 */
@Component({
  selector: 'sb-more-sheet',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Icon, FocusTrap, Button],
  host: { '(document:keydown.escape)': 'onEscape()' },
  template: `
    @if (open()) {
      <div class="scrim" aria-hidden="true" (click)="closed.emit()"></div>
      <div class="sheet elev-overlay sb-sheet-in" role="dialog" aria-modal="true" aria-label="More" sbFocusTrap>
        <button type="button" class="search" (click)="searchRequested.emit()">
          <span class="glyph" aria-hidden="true"><sb-icon name="search" /></span>
          <span>Search or jump…</span>
        </button>
        @for (group of groups(); track group.id) {
          <p class="group-label" [id]="group.id">{{ group.label }}</p>
          <ul class="pages" [attr.aria-labelledby]="group.id">
            @for (link of group.links; track link.path) {
              <li>
                <a class="page" [routerLink]="link.path" (click)="closed.emit()">{{ link.label }}</a>
              </li>
            }
          </ul>
        }
        <button sb-button variant="secondary" type="button" class="close" (click)="closed.emit()">Close</button>
      </div>
    }
  `,
  styles: `
    :host { display: contents; }
    .scrim { position: fixed; inset: 0; z-index: 30; background: var(--scrim-soft); }
    .sheet {
      position: fixed;
      inset: auto 0 0 0;
      z-index: 31;
      max-height: 80dvh;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: var(--space-10);
      padding: var(--space-14) var(--space-14) calc(var(--space-14) + env(safe-area-inset-bottom));
      background: var(--surface-overlay);
      border-top: 1px solid var(--border-strong);
      border-radius: var(--panel-radius) var(--panel-radius) 0 0;
    }
    /* A button dressed as the field it opens: the palette owns the typing. */
    .search {
      display: flex;
      align-items: center;
      gap: var(--space-8);
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      border: 1px solid var(--border-strong);
      border-radius: var(--control-radius);
      background: var(--bg);
      color: var(--text-muted);
      font: inherit;
      font-size: var(--text-control);
      text-align: left;
      cursor: pointer;
    }
    .group-label { margin: var(--space-4) 0 0; color: var(--text-muted); font-size: var(--text-micro); }
    .pages {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--space-4);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .page {
      display: flex;
      align-items: center;
      gap: var(--space-8);
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      border-radius: var(--control-radius);
      color: var(--text-secondary);
      font-size: var(--text-body);
      text-decoration: none;
      transition: color var(--transition), background var(--transition);
    }
    .page:hover { background: var(--surface-raised); color: var(--text); }
    .glyph { display: inline-flex; line-height: 0; }
  `,
})
export class MoreSheet {
  readonly open = input(false);
  readonly closed = output<void>();
  readonly searchRequested = output<void>();

  private readonly session = inject(SessionStore);
  protected readonly groups = computed(() => morePageGroups(navEntriesFor(this.session.isAdmin())));

  protected onEscape(): void {
    if (this.open()) this.closed.emit();
  }
}
