import {
  ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, ElementRef, computed, effect, inject, input, output, signal, untracked,
} from '@angular/core';

import { Button } from '../ui/button';
import { Icon } from '../ui/icon';
import { Drawer } from '../ui/layout';
import { NavEntry } from './nav';
import { MAX_TAB_PAGES, TabBarPrefs } from './tab-bar-prefs';

/** Why Add is unavailable: inline text above Under More, never only a tooltip (spec v240 §6). */
export const ADD_LIMIT_REASON = `The bar holds ${MAX_TAB_PAGES} pages. Remove one to add another.`;

/** How long Reset's inline Undo stays (spec v240 §6). */
export const UNDO_MS = 8000;

/** The control that takes focus after an edit: the moved page's own button. */
type RowAction = 'up' | 'down' | 'remove' | 'add';

/**
 * The phone tab bar's editor (spec v240 §6), in an sb-drawer the shell
 * hosts beside the More sheet. Two lists that partition the pages this
 * login may open: "In the tab bar" (Home pinned first, then up, down and
 * remove) and "Under More" (add). Edits apply at once through TabBarPrefs,
 * which validates and saves them; a live preview shows the bar, and every
 * edit is announced in one polite live region.
 *
 * Buttons only, no drag-reorder, so nothing competes with the sheet's drag
 * to close. Unavailable buttons are aria-disabled, not disabled: a disabled
 * button drops focus to <body> and FocusTrap skips it. Rows are tracked by
 * path, so a move re-inserts the row; focus then follows the page.
 */
@Component({
  selector: 'sb-tab-bar-editor',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Drawer, Icon, Button],
  template: `
    <sb-drawer [open]="open()" heading="Edit tab bar" (closed)="onDrawerClosed()">
      <div class="editor">
        <figure class="preview" role="img" [attr.aria-label]="previewLabel()">
          @for (tab of prefs.tabs(); track tab.path) {
            <span class="preview-tab"><sb-icon [name]="tab.icon" title="" [size]="20" /><span class="preview-label">{{ tab.label }}</span></span>
          }
          <span class="preview-tab"><sb-icon name="more" title="" [size]="20" /><span class="preview-label">More</span></span>
        </figure>
        <h3 class="list-label" id="tab-bar-on">In the tab bar</h3>
        <ol class="rows on-bar" aria-labelledby="tab-bar-on">
          @for (tab of prefs.tabs(); track tab.path; let i = $index, last = $last) {
            <li class="row" [attr.data-path]="tab.path">
              <span class="glyph" aria-hidden="true"><sb-icon [name]="tab.icon" title="" [size]="20" /></span>
              <span class="row-label">{{ tab.label }}</span>
              @if (i === 0) {
                <span class="pinned">Always first</span>
              } @else {
                <button sb-button variant="icon" type="button" class="act up" [attr.aria-disabled]="i === 1 ? 'true' : null"
                        [attr.aria-label]="'Move ' + tab.label + ' up'" (click)="moveUp(tab, i)"><sb-icon name="up" title="" [size]="20" /></button>
                <button sb-button variant="icon" type="button" class="act down" [attr.aria-disabled]="last ? 'true' : null"
                        [attr.aria-label]="'Move ' + tab.label + ' down'" (click)="moveDown(tab, last)"><sb-icon name="down" title="" [size]="20" /></button>
                <button sb-button variant="icon" type="button" class="act remove" [attr.aria-label]="'Remove ' + tab.label + ' from the tab bar'"
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
              <button sb-button variant="icon" type="button" class="act add" [attr.aria-disabled]="prefs.canAdd() ? null : 'true'"
                      [attr.aria-describedby]="prefs.canAdd() ? null : 'tab-bar-full'"
                      [attr.aria-label]="'Add ' + entry.label + ' to the tab bar'" (click)="add(entry)"><sb-icon name="plus" title="" [size]="20" /></button>
            </li>
          }
        </ul>

        <div class="actions">
          <button sb-button variant="secondary" type="button" class="reset"
                  [attr.aria-disabled]="prefs.isDefault() ? 'true' : null" (click)="reset()">Reset</button>
          @if (undoPaths()) {
            <button sb-button variant="secondary" type="button" class="undo" (click)="undo()">Undo</button>
          }
          <button sb-button variant="primary" type="button" class="done" (click)="done()">Done</button>
        </div>

        <p class="announce" aria-live="polite" aria-atomic="true">{{ announcement() }}</p>
      </div>
    </sb-drawer>
  `,
  styles: `
    :host { display: contents; }
    .editor { display: flex; flex-direction: column; gap: var(--space-10); }
    /* The bar as it will look: equal shares, the label truncating like the real bar's. */
    .preview {
      display: grid;
      grid-auto-flow: column;
      grid-auto-columns: minmax(0, 1fr);
      gap: var(--space-4);
      margin: 0;
      padding: var(--space-6);
      border: 1px solid var(--border);
      border-radius: var(--panel-radius);
      background: var(--bg);
    }
    .preview-tab { display: flex; flex-direction: column; align-items: center; gap: var(--space-4); min-width: 0; color: var(--text-muted); }
    .preview-label { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--text-micro); font-weight: 600; }
    .list-label { margin: var(--space-4) 0 0; color: var(--text-muted); font-size: var(--text-micro); font-weight: 600; }
    .rows { display: flex; flex-direction: column; gap: var(--space-4); margin: 0; padding: 0; list-style: none; }
    .row {
      display: flex;
      align-items: center;
      gap: var(--space-8);
      min-height: 44px;
      padding: 0 var(--space-4) 0 var(--space-10);
      border: 1px solid var(--border);
      border-radius: var(--control-radius);
      background: var(--surface-raised);
    }
    .glyph { display: inline-flex; line-height: 0; color: var(--text-muted); }
    .row-label { flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; color: var(--text); font-size: var(--text-body); }
    .pinned { padding-right: var(--space-10); color: var(--text-muted); font-size: var(--text-micro); }
    /* 44x44 at every width: the editor is a touch surface first (spec v240 §6). */
    .act {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 44px;
      min-height: 44px;
      padding: 0;
      border: 0;
      border-radius: var(--control-radius);
      background: none;
      color: var(--text-secondary);
      cursor: pointer;
    }
    .act:hover { background: var(--surface-overlay); color: var(--text); }
    .act:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
    .act[aria-disabled='true'] { color: var(--text-muted); opacity: 0.5; cursor: not-allowed; }
    .reason { margin: 0; color: var(--text-secondary); font-size: var(--text-micro); }
    .actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-8); margin-top: var(--space-4); }
    .actions button { min-height: 44px; }
    .actions .done { margin-left: auto; }
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
  /** The preview's accessible name: the bar left to right, then More. */
  protected readonly previewLabel = computed(() =>
    `Tab bar preview: ${[...this.prefs.tabs().map((tab) => tab.label), 'More'].join(', ')}`);

  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  private readonly cdr = inject(ChangeDetectorRef);

  /** The bar from before a Reset, while its Undo is offered. */
  protected readonly undoPaths = signal<readonly string[] | null>(null);
  private undoTimer: ReturnType<typeof setTimeout> | undefined;

  constructor() {
    // Closing by any path drops a pending Undo (Decision 15).
    effect(() => {
      if (!this.open()) untracked(() => this.clearUndo());
    });
    inject(DestroyRef).onDestroy(() => this.clearUndo());
  }

  protected reset(): void {
    if (this.prefs.isDefault()) return;
    const before = this.prefs.reset();
    this.clearUndo();
    this.undoPaths.set(before);
    this.undoTimer = setTimeout(() => this.expireUndo(), UNDO_MS);
    this.announce('Tab bar reset to default');
  }

  protected undo(): void {
    const before = this.undoPaths();
    if (!before) return;
    this.prefs.set(before);
    this.clearUndo();
    this.announce('Tab bar restored');
    this.focusAction('reset');
  }

  /** Every edit is already saved; Done only closes. */
  protected done(): void {
    this.clearUndo();
    this.closed.emit();
  }

  /** The Undo button leaves the DOM; if it held focus, Reset takes it, never <body>. */
  private expireUndo(): void {
    const focused = this.host.querySelector('.actions .undo') === document.activeElement;
    this.clearUndo();
    if (focused) this.focusAction('reset');
  }

  private clearUndo(): void {
    clearTimeout(this.undoTimer);
    this.undoTimer = undefined;
    this.undoPaths.set(null);
  }

  private focusAction(name: 'reset'): void {
    this.cdr.detectChanges();
    this.host.querySelector<HTMLElement>(`.actions .${name}`)?.focus();
  }

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
