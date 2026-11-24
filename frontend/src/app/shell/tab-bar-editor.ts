import { ChangeDetectionStrategy, ChangeDetectorRef, Component, ElementRef, inject, input, output, signal } from '@angular/core';

import { Icon } from '../ui/icon';
import { Drawer } from '../ui/layout';
import { NavEntry } from './nav';
import { MAX_TAB_PAGES, TabBarPrefs } from './tab-bar-prefs';

/** Why Add is unavailable: inline text above Under More, never only a tooltip (spec v240 §6). */
export const ADD_LIMIT_REASON = `The bar holds ${MAX_TAB_PAGES} pages. Remove one to add another.`;

/** The control that takes focus after an edit: the moved page's own button. */
type RowAction = 'up' | 'down' | 'remove' | 'add';

/**
 * The phone tab bar's editor (spec v240 §6), in an sb-drawer the shell
 * hosts beside the More sheet. Two lists that partition the pages this
 * login may open: "In the tab bar" (Home pinned first, then up, down and
 * remove) and "Under More" (add). Edits apply at once through TabBarPrefs,
 * which validates and saves them; every edit is announced in one polite
 * live region.
 *
 * Buttons only, no drag-reorder, so nothing competes with the sheet's drag
 * to close. Unavailable buttons are aria-disabled, not disabled: a disabled
 * button drops focus to <body> and FocusTrap skips it. Rows are tracked by
 * path, so a move re-inserts the row; focus then follows the page.
 */
@Component({
  selector: 'sb-tab-bar-editor',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Drawer, Icon],
  template: `
    <sb-drawer [open]="open()" heading="Edit tab bar" (closed)="onDrawerClosed()">
      <div class="editor">
        <h3 class="list-label" id="tab-bar-on">In the tab bar</h3>
        <ol class="rows on-bar" aria-labelledby="tab-bar-on">
          @for (tab of prefs.tabs(); track tab.path; let i = $index, last = $last) {
            <li class="row" [attr.data-path]="tab.path">
              <span class="glyph" aria-hidden="true"><sb-icon [name]="tab.icon" title="" [size]="20" /></span>
              <span class="row-label">{{ tab.label }}</span>
              @if (i === 0) {
                <span class="pinned">Always first</span>
              } @else {
                <button type="button" class="act up" [attr.aria-disabled]="i === 1 ? 'true' : null"
                        [attr.aria-label]="'Move ' + tab.label + ' up'" (click)="moveUp(tab, i)"><sb-icon name="up" title="" [size]="20" /></button>
                <button type="button" class="act down" [attr.aria-disabled]="last ? 'true' : null"
                        [attr.aria-label]="'Move ' + tab.label + ' down'" (click)="moveDown(tab, last)"><sb-icon name="down" title="" [size]="20" /></button>
                <button type="button" class="act remove" [attr.aria-label]="'Remove ' + tab.label + ' from the tab bar'"
                        (click)="remove(tab)"><sb-icon name="minus" title="" [size]="20" /></button>
              }
            </li>
          }
        </ol>

        <h3 class="list-label" id="tab-bar-more">Under More</h3>
        @if (!prefs.canAdd()) {
          <p class="reason" id="tab-bar-full">{{ reason }}</p>
        }
        <ul class="rows under-more" aria-labelledby="tab-bar-more">
          @for (entry of prefs.underMore(); track entry.path) {
            <li class="row" [attr.data-path]="entry.path">
              <span class="glyph" aria-hidden="true"><sb-icon [name]="entry.icon" title="" [size]="20" /></span>
              <span class="row-label">{{ entry.label }}</span>
              <button type="button" class="act add" [attr.aria-disabled]="prefs.canAdd() ? null : 'true'"
                      [attr.aria-describedby]="prefs.canAdd() ? null : 'tab-bar-full'"
                      [attr.aria-label]="'Add ' + entry.label + ' to the tab bar'" (click)="add(entry)"><sb-icon name="plus" title="" [size]="20" /></button>
            </li>
          }
        </ul>

        <p class="announce" aria-live="polite" aria-atomic="true">{{ announcement() }}</p>
      </div>
    </sb-drawer>
  `,
  styles: `
    :host { display: contents; }
    .announce { position: absolute; inline-size: 1px; block-size: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  `,
})
export class TabBarEditor {
  readonly open = input(false);
  /** Once per close: Done (V247-15), or the drawer's own ×, Escape or backdrop. */
  readonly closed = output<void>();

  protected readonly prefs = inject(TabBarPrefs);
  protected readonly reason = ADD_LIMIT_REASON;
  protected readonly announcement = signal('');

  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  private readonly cdr = inject(ChangeDetectorRef);

  protected moveUp(tab: NavEntry, index: number): void {
    if (index <= 1) return;
    this.prefs.moveUp(tab.path);
    this.edited(tab.path, 'up', `${tab.label} moved to position ${this.position(tab.path)}`);
  }

  protected moveDown(tab: NavEntry, last: boolean): void {
    if (last) return;
    this.prefs.moveDown(tab.path);
    this.edited(tab.path, 'down', `${tab.label} moved to position ${this.position(tab.path)}`);
  }

  protected remove(tab: NavEntry): void {
    this.prefs.remove(tab.path);
    this.edited(tab.path, 'add', `${tab.label} moved to More`);
  }

  protected add(entry: NavEntry): void {
    if (!this.prefs.canAdd()) return;
    this.prefs.add(entry.path);
    this.edited(entry.path, 'remove', `${entry.label} added to the tab bar`);
  }

  /** The drawer reports every close; the editor passes it on only while the shell still has it open. */
  protected onDrawerClosed(): void {
    if (this.open()) this.closed.emit();
  }

  private position(path: string): number {
    return this.prefs.paths().indexOf(path) + 1;
  }

  private edited(path: string, action: RowAction, message: string): void {
    this.announce(message);
    this.refocus(path, action);
  }

  private announce(message: string): void {
    this.announcement.set(message);
  }

  /** Renders the edit now, then focuses the page's control: its row was re-inserted, so the browser dropped focus. */
  private refocus(path: string, action: RowAction): void {
    this.cdr.detectChanges();
    this.host.querySelector<HTMLElement>(`li[data-path="${path}"] button.${action}`)?.focus();
  }
}
