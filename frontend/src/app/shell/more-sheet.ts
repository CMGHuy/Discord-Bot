import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';

import { FocusTrap } from '../ui/focus-trap';
import { Button } from '../ui/button';
import { Icon } from '../ui/icon';
import { NAV_GROUPS, NavEntry, NavGroup, PHONE_TABS } from './nav';

/** The rail's groups minus the pages already on the phone's tab bar, in rail
 *  order; a group left with no page is dropped (Monitor, today). */
export function morePageGroups(
  groups: readonly NavGroup[] = NAV_GROUPS,
  tabs: readonly NavEntry[] = PHONE_TABS,
): NavGroup[] {
  const onBar = new Set(tabs.map((tab) => tab.path));
  return groups
    .map((group) => ({ ...group, entries: group.entries.filter((entry) => !onBar.has(entry.path)) }))
    .filter((group) => group.entries.length > 0);
}

/**
 * The phone's More sheet -- v195 Phase 3: every page the tab bar does not
 * hold, grouped as on the rail, and the search field.
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
        @for (group of groups; track group.id) {
          <p class="group-label" [id]="'more-' + group.id">{{ group.label }}</p>
          <ul class="pages" [attr.aria-labelledby]="'more-' + group.id">
            @for (entry of group.entries; track entry.path) {
              <li>
                <a class="page" [routerLink]="entry.path" (click)="closed.emit()">
                  <span class="glyph" aria-hidden="true"><sb-icon [name]="entry.icon" /></span>
                  <span>{{ entry.label }}</span>
                </a>
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

  protected readonly groups = morePageGroups();

  protected onEscape(): void {
    if (this.open()) this.closed.emit();
  }
}
