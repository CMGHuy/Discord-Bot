# v247 — Doctena night, plan 3 of 5: Shell and navigation — Part 5: Editor and browser check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V247-15" -A 400 <this file>`).

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) §6 ("Editing the bar": two lists, up/down/remove/add with 44px targets, the inline add-limit reason, live preview, Reset with an 8s Undo, Done, `aria-live` announcements, focus trapped and returned, "Risk is never out of reach"), §8 (the editor never shows a page the login cannot open; a viewer never sees System), §9 (editor at 390/820/1440, ≥44px targets), §11 (the partition gate; the E2E lines: rail tooltip and the phone editor round-trip).
**Index:** [2026-11-23-v247-doctena-night-shell-and-navigation_0-index.md](2026-11-23-v247-doctena-night-shell-and-navigation_0-index.md) — Goal, Global Constraints, Decisions (4, 14 and 15 above all), Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks: V247-14 (the `sb-tab-bar-editor` component: the two lists, the moves, the inline reason, focus and the announcements), V247-14b (its live preview, its three-width styles with 44px targets, and the partition gate), V247-15 (Reset with its 8s Undo, Done; the More sheet's **Edit tab bar** action; the shell hosts the editor and focus returns to the Edit button), V247-16 (a Playwright check at 390/820/1440 plus `layout-audit.mjs` at the three widths). They run **in id order**, one commit each: V247-14b and V247-15 edit `tab-bar-editor.ts` after V247-14, and V247-16 drives the finished shell.

Runs after part 4: `shell/tab-bar-prefs.ts` exports `TAB_BAR_PREF_KEY = 'ui.tabbar'`, `MAX_TAB_PAGES = 4`, `TabBarStorage`, `TAB_BAR_STORAGE` and the root service `TabBarPrefs` (`paths`, `tabs`, `underMore`, `canAdd`, `isDefault` signals; `set`, `add`, `remove`, `moveUp`, `moveDown`, `reset(): readonly string[]`, V247-11b). `tabs()` carries the phone labels (the Dashboard reads **Home**), `underMore()` the rail labels in rail order. Every edit re-validates and saves; the Dashboard never moves and is never removed; `add` is a no-op while the bar is full. `MoreSheet.groups` already reads `TabBarPrefs.tabs()` (V247-12), and `PhoneTabBar` carries four `role="tooltip"` hints (V247-13).

All frontend commands run from the worktree root; `--include` paths are relative to `frontend/`. Session state in specs comes from `patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'admin', role: 'admin' })` (viewer: `role: 'viewer'`). Every spec that mounts something reading `TabBarPrefs` provides an in-memory `TAB_BAR_STORAGE`, so no spec writes jsdom's real `localStorage`. jsdom has no `showModal()`: a spec that opens an `sb-drawer` calls `installDialogPolyfill()` (`app/testing/dialog-polyfill.ts`) and provides `provideMotion('off')` so a close is immediate (`ui/motion/exit.ts` `playExit`). The polyfill flips `open` and fires `close`; it does not trap focus, so focus tests assert only what `FocusTrap` (`ui/focus-trap.ts`) does itself: focus the first focusable on open, and restore what had focus on close.

The three-width design (spec §9): the editor lives in `sb-drawer`, which is a bottom sheet below 640px (85dvh at most, drag handle), 85vw from the right at 640–1023px and 480px wide from 1024px (`ui/layout.ts`), so its rows are one flexible column that never sets a width. Every row button is a 44×44 box at every width (`min-width: 44px; min-height: 44px`, pinned in V247-14). The editor is reached from the More sheet, which exists only below 640px; at 820 and 1440px there is no tab bar, no More sheet and so no editor, and widening the window while it is open closes it (V247-15). V247-16 checks the editor at 390px (and the bar at 320px) and checks at 820 and 1440px that none of the three is in the DOM while the rail tooltip works.

---

# Phase 5 — Editor and browser check

### Task V247-14: Tab-bar editor: two lists, move/add/remove, inline reason, announcements

**Model:** sonnet — a new component over V247-11b's service with focus handling; the logic is thin, the a11y details need care.

**Split:** this task passed 20 KB whole. V247-14 builds the component's lists, edits, inline reason, focus and announcements; **V247-14b** adds the live preview, the full `styles` block with its 44px pins, and the partition gate. Run V247-14b straight after.

**Files:**
- Create: `frontend/src/app/shell/tab-bar-editor.ts`
- Create: `frontend/src/app/shell/tab-bar-editor.spec.ts`

**Interfaces:**
- Consumes (V247-11b, `shell/tab-bar-prefs.ts`): `TabBarPrefs` (`paths`, `tabs`, `underMore`, `canAdd` signals; `add`, `remove`, `moveUp`, `moveDown`), `MAX_TAB_PAGES`, `TAB_BAR_PREF_KEY`, `TAB_BAR_STORAGE`. (`shell/nav.ts`): `NavEntry`. Existing: `Drawer` (`sb-drawer`; inputs `open`, `heading`; output `closed`; `ui/layout.ts`), `Icon` (`sb-icon`; `name`, `title`, `size: 16 | 20 | 24`; `up`, `down`, `plus`, `minus` exist), `installDialogPolyfill` (`testing/dialog-polyfill.ts`), `provideMotion` (`ui/motion/motion.service.ts`), `ViewportService` (`ui/breakpoints.ts`).
- Produces (V247-14b, V247-15 and V247-16 consume):
  - `@Component({ selector: 'sb-tab-bar-editor' }) export class TabBarEditor { readonly open = input(false); readonly closed = output<void>() }`; `closed` fires once per close, whoever closed it.
  - `export const ADD_LIMIT_REASON = 'The bar holds 4 pages. Remove one to add another.'`
  - DOM: `sb-drawer` headed `Edit tab bar`; inside it one `div.editor` column holding `h3#tab-bar-on`, `ol.rows.on-bar > li.row[data-path]`, `h3#tab-bar-more`, `p.reason#tab-bar-full` (only while full), `ul.rows.under-more > li.row[data-path]`, then `p.announce[aria-live=polite]` last. Each row has a `.row-label`; buttons `button.act.up|down|remove|add`, labelled `Move <Label> up`, `Move <Label> down`, `Remove <Label> from the tab bar`, `Add <Label> to the tab bar`.
  - In `tab-bar-editor.spec.ts`: `mount(role = 'admin', saved?: string)`, `labels(el, list)`, `rowPaths(el, list)`, `button(el, path, action)`, `announced(el)`, `press(fixture, button)`, `text(node)` and the `stored` map (V247-14b and V247-15 append to the file).
  - Private helpers V247-15 reuses: `announce(message: string): void`, `refocus(path: string, action: RowAction): void`.

Spec §6 ("Editing the bar") and Decision 14 fix the rules and the announcement texts; the viewer and minimum-bar edge cases are in V247-14b with the partition gate.

Two design points the tests pin:

1. **Unavailable means `aria-disabled`, not `disabled`.** A `disabled` button drops focus to `<body>` the moment it becomes disabled, and `FocusTrap` skips it; `aria-disabled="true"` stays focusable, and its handler does nothing.
2. **Focus follows the page.** A move re-inserts the row (tracked by path) and the browser drops focus, so after every edit the editor renders at once (`ChangeDetectorRef.detectChanges()`; the projected rows belong to its view) and focuses the page's control: the same up/down button, its add button after a remove, its remove button after an add.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/shell/tab-bar-editor.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { describe, expect, it } from 'vitest';

import { SessionStore } from '../stores/session.store';
import { installDialogPolyfill } from '../testing/dialog-polyfill';
import { ViewportService } from '../ui/breakpoints';
import { provideMotion } from '../ui/motion/motion.service';
import { TAB_BAR_PREF_KEY, TAB_BAR_STORAGE } from './tab-bar-prefs';
import { ADD_LIMIT_REASON, TabBarEditor } from './tab-bar-editor';

type List = 'on-bar' | 'under-more';
type Action = 'up' | 'down' | 'remove' | 'add';

let stored: Map<string, string>;

function mount(role: 'admin' | 'viewer' = 'admin', saved?: string) {
  installDialogPolyfill();
  stored = new Map(saved === undefined ? [] : [[TAB_BAR_PREF_KEY, saved]]);
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideMotion('off'),
      { provide: ViewportService, useValue: { isPhone: () => true } },
      {
        provide: TAB_BAR_STORAGE,
        useValue: { get: (key: string) => stored.get(key) ?? null, set: (key: string, value: string) => void stored.set(key, value) },
      },
    ],
  });
  patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: role, role });
  const fixture = TestBed.createComponent(TabBarEditor);
  fixture.componentRef.setInput('open', true);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

const text = (node: Element) => node.textContent!.trim();
const labels = (el: HTMLElement, list: List) => [...el.querySelectorAll(`.${list} .row-label`)].map(text);
const rowPaths = (el: HTMLElement, list: List) =>
  [...el.querySelectorAll(`.${list} li.row`)].map((row) => row.getAttribute('data-path')!);
const button = (el: HTMLElement, path: string, action: Action) =>
  el.querySelector<HTMLButtonElement>(`li[data-path="${path}"] button.${action}`)!;
const announced = (el: HTMLElement) => text(el.querySelector('.announce')!);
const savedPaths = () => JSON.parse(stored.get(TAB_BAR_PREF_KEY)!) as string[];

function press(fixture: ComponentFixture<TabBarEditor>, target: HTMLButtonElement): void {
  target.click();
  fixture.detectChanges();
}

describe('TabBarEditor (v240 §6)', () => {
  it('is an sb-drawer headed Edit tab bar, with nothing rendered while closed', () => {
    const { fixture, el } = mount();
    expect(text(el.querySelector('sb-drawer h2')!)).toBe('Edit tab bar');
    expect(el.querySelector('dialog')!.open).toBe(true);
    fixture.componentRef.setInput('open', false);
    fixture.detectChanges();
    expect(el.querySelector('dialog')!.open).toBe(false);
    expect(el.querySelector('.editor')).toBeNull();
  });

  it('lists the bar in order, Home pinned first with no buttons', () => {
    const { el } = mount();
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    const home = el.querySelector('.on-bar li.row')!;
    expect(home.querySelectorAll('button')).toHaveLength(0);
    expect(text(home.querySelector('.pinned')!)).toBe('Always first');
    for (const path of ['/watchlist', '/trades', '/calendar']) {
      for (const action of ['up', 'down', 'remove'] as const) expect(button(el, path, action)).not.toBeNull();
    }
    expect(button(el, '/watchlist', 'up').getAttribute('aria-label')).toBe('Move Watchlist up');
    expect(button(el, '/watchlist', 'down').getAttribute('aria-label')).toBe('Move Watchlist down');
    expect(button(el, '/watchlist', 'remove').getAttribute('aria-label')).toBe('Remove Watchlist from the tab bar');
  });

  it('lists every other page under More, rail order and rail labels, each with an add button', () => {
    const { el } = mount();
    expect(labels(el, 'under-more')).toEqual(['Risk', 'Insights', 'System']);
    expect(button(el, '/risk', 'add').getAttribute('aria-label')).toBe('Add Risk to the tab bar');
  });

  it('marks up unavailable at position 2 and down at the last position, and those presses do nothing', () => {
    const { fixture, el } = mount();
    expect(button(el, '/watchlist', 'up').getAttribute('aria-disabled')).toBe('true');
    expect(button(el, '/calendar', 'down').getAttribute('aria-disabled')).toBe('true');
    expect(button(el, '/trades', 'up').hasAttribute('aria-disabled')).toBe(false);
    expect(button(el, '/watchlist', 'up').disabled).toBe(false);
    press(fixture, button(el, '/watchlist', 'up'));
    press(fixture, button(el, '/calendar', 'down'));
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    expect(announced(el)).toBe('');
    expect(stored.has(TAB_BAR_PREF_KEY)).toBe(false);
  });

  it('moves a page, saves it, announces its new position and keeps focus on the same button', () => {
    const { fixture, el } = mount();
    press(fixture, button(el, '/watchlist', 'down'));
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Trades', 'Watchlist', 'Calendar']);
    expect(savedPaths()).toEqual(['/dashboard', '/trades', '/watchlist', '/calendar']);
    expect(announced(el)).toBe('Watchlist moved to position 3');
    expect(document.activeElement).toBe(button(el, '/watchlist', 'down'));
    press(fixture, button(el, '/calendar', 'up'));
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Trades', 'Calendar', 'Watchlist']);
    expect(announced(el)).toBe('Calendar moved to position 3');
    expect(document.activeElement).toBe(button(el, '/calendar', 'up'));
  });

  it('removes a page to More in rail order, announces it and focuses its add button', () => {
    const { fixture, el } = mount();
    press(fixture, button(el, '/watchlist', 'remove'));
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Trades', 'Calendar']);
    expect(labels(el, 'under-more')).toEqual(['Watchlist', 'Risk', 'Insights', 'System']);
    expect(announced(el)).toBe('Watchlist moved to More');
    expect(document.activeElement).toBe(button(el, '/watchlist', 'add'));
  });

  it('shows the add-limit reason inline above Under More while the bar is full, and add does nothing', () => {
    const { fixture, el } = mount();
    const reason = el.querySelector('p.reason')!;
    expect(text(reason)).toBe(ADD_LIMIT_REASON);
    expect(ADD_LIMIT_REASON).toBe('The bar holds 4 pages. Remove one to add another.');
    const underMore = el.querySelector('ul.under-more')!;
    expect(reason.compareDocumentPosition(underMore) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const add = button(el, '/risk', 'add');
    expect(add.getAttribute('aria-disabled')).toBe('true');
    expect(add.getAttribute('aria-describedby')).toBe(reason.id);
    press(fixture, add);
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    expect(announced(el)).toBe('');
  });

  it('adds once there is room: the reason goes, the page joins the end and its remove button takes focus', () => {
    const { fixture, el } = mount();
    press(fixture, button(el, '/watchlist', 'remove'));
    expect(el.querySelector('p.reason')).toBeNull();
    expect(button(el, '/risk', 'add').hasAttribute('aria-disabled')).toBe(false);
    expect(button(el, '/risk', 'add').hasAttribute('aria-describedby')).toBe(false);
    press(fixture, button(el, '/risk', 'add'));
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Trades', 'Calendar', 'Risk']);
    expect(savedPaths()).toEqual(['/dashboard', '/trades', '/calendar', '/risk']);
    expect(announced(el)).toBe('Risk added to the tab bar');
    expect(document.activeElement).toBe(button(el, '/risk', 'remove'));
  });

  it('carries the announcements in one polite live region, last in the editor', () => {
    const { el } = mount();
    const regions = el.querySelectorAll('[aria-live]');
    expect(regions).toHaveLength(1);
    expect(regions[0].getAttribute('aria-live')).toBe('polite');
    expect(regions[0].classList).toContain('announce');
    expect(el.querySelector('.editor')!.lastElementChild).toBe(regions[0]);
  });

  it('reports one close when the drawer closes itself (its × button)', () => {
    const { fixture, el } = mount();
    let closed = 0;
    fixture.componentInstance.closed.subscribe(() => (closed += 1));
    el.querySelector<HTMLButtonElement>('sb-drawer header button.close')!.click();
    fixture.detectChanges();
    expect(closed).toBe(1);
  });
});
```

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/tab-bar-editor.spec.ts`
Expected: FAIL: `./tab-bar-editor` cannot be resolved.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/shell/tab-bar-editor.ts`:

```ts
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
```

`onDrawerClosed` guards on `open()`: the drawer's own ×, Escape and backdrop close while the input is still `true`; when the shell closes it (Done, or leaving phone width) the input is already `false`, so nothing is reported twice. The sr-only region uses `inline-size`/`block-size` so V247-14b's "never fixes a width" scan stays a plain `width:` match.

- [ ] **Step 4: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/tab-bar-editor.spec.ts`
Expected: PASS, 0 failed. A failing focus assertion means `refocus` lost its `cdr.detectChanges()` before the query. A 60s `Timeout waiting for worker` is load: re-run once.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/tab-bar-editor.ts frontend/src/app/shell/tab-bar-editor.spec.ts
git commit -m "feat(v247): tab-bar editor -- two lists, move/add/remove, inline add-limit reason, announcements" -m "Home pinned first; aria-disabled keeps focus on an unavailable button; focus follows the moved page (spec v240 §6). Preview, styles and the partition gate follow in V247-14b."
```

### Task V247-14b: Tab-bar editor: live preview, three-width styles with 44px targets, the partition gate

**Model:** sonnet — a template addition, one `styles` block with source-scan pins, and a parameterised partition gate over two roles; fully specified below.

**Files:**
- Modify: `frontend/src/app/shell/tab-bar-editor.ts` (V247-14's file: the `@angular/core` import, the template's first child, the `styles` block, one field)
- Modify: `frontend/src/app/shell/tab-bar-editor.spec.ts` (V247-14's file: two imports, three describes appended)
- Modify: `frontend/src/app/ui/money-colour.spec.ts` (`NAV_FILES` += `'app/shell/tab-bar-editor.ts'`)

**Interfaces:**
- Consumes (V247-14): `TabBarEditor`, its DOM (`div.editor`, `ol.on-bar`, `ul.under-more`, `li.row[data-path]`, `.row-label`, `button.act.*`, `p.reason`) and the spec helpers `mount`, `labels`, `rowPaths`, `button`, `press`, `text`. (V247-11b): `TabBarPrefs.tabs`. (`shell/nav.ts`): `navEntriesFor`.
- Produces (V247-16 reads it): `figure.preview[role=img]`, first child of `div.editor`, `aria-label` = `Tab bar preview: <tab labels>, More`, one `.preview-label` per tab plus `More`.

Spec §6: "A live preview of the bar"; "Risk is never out of reach … A test pins that every nav page the login may see is in exactly one of the two lists." Spec §8: "The editor never shows a page the login cannot open"; "A viewer (non-admin) never sees System in the rail, More sheet or editor." Spec §9: the editor at phone, tablet and desktop widths, targets ≥44px, nothing scrolling sideways at 390px, long labels wrapping.

The three widths: the editor never sets a width; `sb-drawer` does (a bottom sheet below 640px, 85vw at 640–1023px, 480px from 1024px). The rows are one flexible column; a label wraps (`overflow-wrap: anywhere`) rather than pushing the buttons off the edge; the preview shares its width equally between tabs (`minmax(0, 1fr)`) and truncates a label with an ellipsis, as the real bar does. Every row button is a 44×44 box at every width, not only under the touch block: the editor is a touch surface first.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/shell/tab-bar-editor.spec.ts`: add to the import block:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

and below the `./tab-bar-prefs` import:

```ts
import { navEntriesFor } from './nav';
```

Append at the end of the file:

```ts
describe('TabBarEditor preview and edge cases (v240 §6, §8)', () => {
  it('previews the bar it edits, More last, and follows every edit', () => {
    const { fixture, el } = mount();
    const preview = el.querySelector('figure.preview')!;
    expect(el.querySelector('.editor')!.firstElementChild).toBe(preview);
    expect(preview.getAttribute('role')).toBe('img');
    expect(preview.getAttribute('aria-label')).toBe('Tab bar preview: Home, Watchlist, Trades, Calendar, More');
    expect([...preview.querySelectorAll('.preview-label')].map(text)).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar', 'More']);
    press(fixture, button(el, '/trades', 'remove'));
    expect(preview.getAttribute('aria-label')).toBe('Tab bar preview: Home, Watchlist, Calendar, More');
    expect([...preview.querySelectorAll('.preview-label')].map(text)).toEqual(['Home', 'Watchlist', 'Calendar', 'More']);
  });

  it('holds the minimum bar, Home alone, with every other page under More and no reason', () => {
    const { el } = mount('admin', '["/dashboard"]');
    expect(labels(el, 'on-bar')).toEqual(['Home']);
    expect(el.querySelectorAll('.on-bar button')).toHaveLength(0);
    expect(labels(el, 'under-more')).toEqual(['Watchlist', 'Trades', 'Calendar', 'Risk', 'Insights', 'System']);
    expect(el.querySelector('p.reason')).toBeNull();
    expect(el.querySelector('figure.preview')!.getAttribute('aria-label')).toBe('Tab bar preview: Home, More');
  });

  it('never shows a viewer System, even when the stored bar holds it', () => {
    const { el } = mount('viewer', '["/dashboard","/system"]');
    expect(labels(el, 'on-bar')).toEqual(['Home']);
    expect(labels(el, 'under-more')).toEqual(['Watchlist', 'Trades', 'Calendar', 'Risk', 'Insights']);
    expect(el.querySelector('[data-path="/system"]')).toBeNull();
  });
});

describe('TabBarEditor partition (v240 §6 "Risk is never out of reach", §11)', () => {
  const STORED: [string, string | undefined][] = [
    ['nothing', undefined],
    ['Home alone', '["/dashboard"]'],
    ['System and two more', '["/dashboard","/system","/insights","/risk"]'],
    ['an old Calendar path', '["/dashboard","/trades/calendar"]'],
    ['not JSON', 'not json'],
    ['an empty list', '[]'],
  ];

  for (const role of ['admin', 'viewer'] as const) {
    it.each(STORED)(`${role}, stored %s: every page the login may open is in exactly one list`, (_name, value) => {
      const { el } = mount(role, value);
      const all = [...rowPaths(el, 'on-bar'), ...rowPaths(el, 'under-more')];
      expect(new Set(all).size).toBe(all.length);
      expect([...all].sort()).toEqual(navEntriesFor(role === 'admin').map((entry) => entry.path).sort());
      expect(rowPaths(el, 'on-bar')[0]).toBe('/dashboard');
      expect(all).toContain('/risk');
      if (role === 'viewer') expect(all).not.toContain('/system');
    });
  }

  it('keeps the partition through a remove and an add', () => {
    const { fixture, el } = mount();
    press(fixture, button(el, '/watchlist', 'remove'));
    press(fixture, button(el, '/risk', 'add'));
    const all = [...rowPaths(el, 'on-bar'), ...rowPaths(el, 'under-more')];
    expect([...all].sort()).toEqual(navEntriesFor(true).map((entry) => entry.path).sort());
    expect(rowPaths(el, 'on-bar')).toEqual(['/dashboard', '/trades', '/calendar', '/risk']);
  });
});

describe('TabBarEditor styles (v240 §6, §9)', () => {
  const source = readFileSync(join(process.cwd(), 'src/app/shell/tab-bar-editor.ts'), 'utf8');
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const rule = (selector: string) => source.match(new RegExp(`^\\s*${esc(selector)} \\{[^}]*\\}`, 'm'))?.[0] ?? '';

  it('gives every row button and every row a 44px target at every width', () => {
    expect(rule('.act')).toContain('min-width: 44px');
    expect(rule('.act')).toContain('min-height: 44px');
    expect(rule('.row')).toContain('min-height: 44px');
  });

  it('never fixes a width, so the drawer sets it (sheet below 640px, 85vw, then 480px)', () => {
    expect(source).not.toMatch(/(?:^|[\s;{])width:\s*\d/m);
  });

  it('wraps a long row label, shares the preview equally, and reads no faint text token', () => {
    expect(rule('.row-label')).toContain('overflow-wrap: anywhere');
    expect(rule('.row-label')).toContain('min-width: 0');
    expect(rule('.preview')).toContain('grid-auto-columns: minmax(0, 1fr)');
    expect(rule('.preview-label')).toContain('text-overflow: ellipsis');
    expect(source).not.toContain('--text-faint');
  });

  it('marks an unavailable button without the disabled attribute, and rounds with tokens only', () => {
    expect(source).toContain(".act[aria-disabled='true']");
    expect(source).not.toMatch(/border-radius:\s*\d+px/);
  });
});
```

`frontend/src/app/ui/money-colour.spec.ts`: add the editor to `NAV_FILES`, so the scan holds its active and focus rules to the no-`--pos`/`--neg` rule (the existing "every NAV_FILES entry is a real source" test keeps the path honest):

```ts
const NAV_FILES: readonly string[] = [
  'app/shell/breadcrumb.ts',
  'app/shell/more-sheet.ts',
  'app/shell/phone-tab-bar.ts',
  'app/shell/section-tabs.ts',
  'app/shell/tab-bar-editor.ts',
];
```

- [ ] **Step 2: Run the specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/tab-bar-editor.spec.ts --include src/app/ui/money-colour.spec.ts`
Expected: FAIL: no `figure.preview` (the preview tests throw on `null`), and the style pins find no `.act`/`.row`/`.preview` rules. The partition, minimum-bar and viewer tests already pass (V247-14's lists hold them); money-colour passes.

- [ ] **Step 3: Add the preview and the styles** in `frontend/src/app/shell/tab-bar-editor.ts`.

Add `computed` to the `@angular/core` import:

```ts
import { ChangeDetectionStrategy, ChangeDetectorRef, Component, ElementRef, computed, inject, input, output, signal } from '@angular/core';
```

In the template, insert as the first child of `<div class="editor">` (before `<h3 class="list-label" id="tab-bar-on">`):

```html
        <figure class="preview" role="img" [attr.aria-label]="previewLabel()">
          @for (tab of prefs.tabs(); track tab.path) {
            <span class="preview-tab"><sb-icon [name]="tab.icon" title="" [size]="20" /><span class="preview-label">{{ tab.label }}</span></span>
          }
          <span class="preview-tab"><sb-icon name="more" title="" [size]="20" /><span class="preview-label">More</span></span>
        </figure>
```

Replace the whole `styles` block with:

```ts
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
    .announce { position: absolute; inline-size: 1px; block-size: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  `,
```

In the class, below `announcement`, add:

```ts
  /** The preview's accessible name: the bar left to right, then More. */
  protected readonly previewLabel = computed(() =>
    `Tab bar preview: ${[...this.prefs.tabs().map((tab) => tab.label), 'More'].join(', ')}`);
```

In the component doc, replace `which validates and saves them; every edit is announced` with `which validates and saves them; a live preview shows the bar, and every edit is announced`.

- [ ] **Step 4: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/tab-bar-editor.spec.ts --include src/app/ui/money-colour.spec.ts --include src/app/ui/type-gates.spec.ts`
Expected: PASS, 0 failed (`type-gates.spec.ts` rides along: the new rules hold no figures, so no `tabular-nums` rule is owed). A 60s `Timeout waiting for worker` is load: re-run once.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/tab-bar-editor.ts frontend/src/app/shell/tab-bar-editor.spec.ts frontend/src/app/ui/money-colour.spec.ts
git commit -m "feat(v247): tab-bar editor preview, 44px targets at every width, and the partition gate" -m "Every page the login may open sits in exactly one list, for admin and viewer, across stored edge cases (spec v240 §6 'Risk is never out of reach', §8, §9, §11)."
```

### Task V247-15: Reset with 8s Undo, Done; the More sheet's Edit tab bar action; shell wiring and focus return

**Model:** sonnet — fake-timer Undo, an Escape hand-off between two overlays and a focus-return path across three files; each piece is small and spelled out.

**Files:**
- Modify: `frontend/src/app/shell/tab-bar-editor.ts`, `frontend/src/app/shell/tab-bar-editor.spec.ts` (V247-14/14b's files)
- Modify: `frontend/src/app/shell/more-sheet.ts`, `frontend/src/app/shell/more-sheet.spec.ts`
- Modify: `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.spec.ts`

**Interfaces:**
- Consumes: `TabBarEditor`, its private `announce(message)` and its spec helpers (V247-14); `TabBarPrefs.isDefault`, `reset()`, `set(paths)` (V247-11b); `TAB_BAR_STORAGE`, `TabBarStorage` (V247-11); the More sheet spec's `open()` and `closed` counter (V247-12); `Button` (`button[sb-button]`, variants `primary`, `secondary`).
- Produces (V247-16 drives them): `export const UNDO_MS = 8000` (`tab-bar-editor.ts`); editor buttons `button.reset`, `button.undo` (only while an Undo is pending), `button.done` in `div.actions`; `MoreSheet.editRequested = output<void>()`, `MoreSheet.editing = input(false)`, its `button.edit` ("Edit tab bar"); `Shell.editorOpen` (protected signal), `openEditor()`, `closeEditor()`; `shellProviders()` in `shell.spec.ts` gains an in-memory `TAB_BAR_STORAGE`.

Spec §6: an **Edit tab bar** action (pencil) in the More sheet; **Reset** with an inline **Undo** for 8 seconds; **Done** closes; focus returns to the Edit button. Decision 15: the timer is cleared on Undo, Done or close; Done keeps every edit.

Focus return: the More sheet stays open under the editor, and `sb-drawer`'s `FocusTrap` restores whatever had focus when it opened. Safari does not focus a clicked button, so the sheet focuses its Edit button itself before asking. While the editor is open the sheet ignores Escape (`editing`). Leaving phone width or closing the sheet closes the editor too.

Reset is `aria-disabled` while the bar is already the default (as in V247-14, so focus stays on it after a reset). Undo restores and hands focus to Reset; an Undo that expires while focused hands focus to Reset too, never to `<body>`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/shell/tab-bar-editor.spec.ts`: change the vitest import to `import { afterEach, describe, expect, it, vi } from 'vitest';` and the editor import to `import { ADD_LIMIT_REASON, TabBarEditor, UNDO_MS } from './tab-bar-editor';`. Append:

```ts
describe('TabBarEditor Reset, Undo and Done (v240 §6, Decision 15)', () => {
  afterEach(() => vi.useRealTimers());

  const action = (el: HTMLElement, name: 'reset' | 'undo' | 'done') =>
    el.querySelector<HTMLButtonElement>(`.actions button.${name}`);

  it('pins the Undo window at 8 seconds and puts Reset, Done in one wrapping row before the live region', () => {
    const { el } = mount('admin', '["/dashboard","/risk"]');
    expect(UNDO_MS).toBe(8000);
    expect(text(action(el, 'reset')!)).toBe('Reset');
    expect(text(action(el, 'done')!)).toBe('Done');
    expect(action(el, 'undo')).toBeNull();
    expect(el.querySelector('.actions')!.nextElementSibling!.classList).toContain('announce');
  });

  it('marks Reset unavailable on the default bar, and that press does nothing', () => {
    const { fixture, el } = mount();
    expect(action(el, 'reset')!.getAttribute('aria-disabled')).toBe('true');
    press(fixture, action(el, 'reset')!);
    expect(announced(el)).toBe('');
    expect(action(el, 'undo')).toBeNull();
  });

  it('resets to the default, saves and announces it, and offers Undo for exactly 8 seconds', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, el } = mount('admin', '["/dashboard","/risk"]');
    press(fixture, action(el, 'reset')!);
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    expect(savedPaths()).toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
    expect(announced(el)).toBe('Tab bar reset to default');
    expect(action(el, 'undo')).not.toBeNull();
    vi.advanceTimersByTime(UNDO_MS - 1);
    fixture.detectChanges();
    expect(action(el, 'undo')).not.toBeNull();
    vi.advanceTimersByTime(1);
    fixture.detectChanges();
    expect(action(el, 'undo')).toBeNull();
  });

  it('Undo restores the bar from before the reset, announces it and hands focus to Reset', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, el } = mount('admin', '["/dashboard","/risk"]');
    press(fixture, action(el, 'reset')!);
    press(fixture, action(el, 'undo')!);
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Risk']);
    expect(savedPaths()).toEqual(['/dashboard', '/risk']);
    expect(announced(el)).toBe('Tab bar restored');
    expect(action(el, 'undo')).toBeNull();
    expect(document.activeElement).toBe(action(el, 'reset'));
    expect(vi.getTimerCount()).toBe(0);
  });

  it('an Undo that expires while focused hands focus to Reset', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, el } = mount('admin', '["/dashboard","/risk"]');
    press(fixture, action(el, 'reset')!);
    action(el, 'undo')!.focus();
    vi.advanceTimersByTime(UNDO_MS);
    fixture.detectChanges();
    expect(document.activeElement).toBe(action(el, 'reset'));
  });

  it('Done closes once, keeps the edits and clears a pending Undo', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, el } = mount('admin', '["/dashboard","/risk"]');
    let closed = 0;
    fixture.componentInstance.closed.subscribe(() => (closed += 1));
    press(fixture, action(el, 'reset')!);
    press(fixture, action(el, 'done')!);
    expect(closed).toBe(1);
    expect(savedPaths()).toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('closing the editor clears a pending Undo, so reopening shows none', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, el } = mount('admin', '["/dashboard","/risk"]');
    press(fixture, action(el, 'reset')!);
    fixture.componentRef.setInput('open', false);
    fixture.detectChanges();
    expect(vi.getTimerCount()).toBe(0);
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    expect(action(el, 'undo')).toBeNull();
  });

  it('gives the action buttons a 44px target at every width', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/tab-bar-editor.ts'), 'utf8');
    expect(source).toMatch(/^\s*\.actions button \{[^}]*min-height: 44px/m);
    expect(source).toMatch(/^\s*\.actions \{[^}]*flex-wrap: wrap/m);
  });
});
```

`frontend/src/app/shell/more-sheet.spec.ts`: in `create()`, add `edited = 0;` and `fixture.componentInstance.editRequested.subscribe(() => (edited += 1));`, and declare `let edited: number;` beside `let searched: number;`. Append inside `describe('MoreSheet (v195 Phase 3)')`:

```ts
  it('offers Edit tab bar with the pencil, just before Close (v240 §6)', () => {
    open();
    const edit = el.querySelector<HTMLButtonElement>('button.edit')!;
    expect(edit.textContent!.trim()).toBe('Edit tab bar');
    expect(edit.querySelector('sb-icon')).not.toBeNull();
    expect(edit.nextElementSibling!.matches('button.close')).toBe(true);
  });

  it('takes focus on Edit before asking for the editor, so focus can come back to it', () => {
    open();
    const edit = el.querySelector<HTMLButtonElement>('button.edit')!;
    edit.click();
    expect(edited).toBe(1);
    expect(document.activeElement).toBe(edit);
    expect(closed).toBe(0);
  });

  it('leaves Escape to the editor while it is open over the sheet', () => {
    open();
    fixture.componentRef.setInput('editing', true);
    fixture.detectChanges();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(closed).toBe(0);
    fixture.componentRef.setInput('editing', false);
    fixture.detectChanges();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(closed).toBe(1);
  });
```

`frontend/src/app/shell/shell.spec.ts`. Imports: add `import { installDialogPolyfill } from '../testing/dialog-polyfill';` and `import { TAB_BAR_STORAGE, TabBarStorage } from './tab-bar-prefs';`. Below `memoryThemeStorage` add:

```ts
/** An in-memory ui.tabbar, so no shell spec writes jsdom's localStorage (v240 §6). */
function memoryTabBarStorage(map = new Map<string, string>()): TabBarStorage {
  return { get: (key) => map.get(key) ?? null, set: (key, value) => void map.set(key, value) };
}
```

and add `{ provide: TAB_BAR_STORAGE, useValue: memoryTabBarStorage() },` as the last entry of `shellProviders()`. Append at the end of the file:

```ts
describe('shell tab-bar editor (v240 §6)', () => {
  let phone: WritableSignal<boolean>;

  beforeEach(() => {
    installDialogPolyfill();
    phone = signal(true);
    TestBed.configureTestingModule({ providers: [...shellProviders([{ path: 'dashboard', component: Blank }]), provideMotion('off')] });
    TestBed.overrideProvider(ViewportService, { useValue: { isPhone: phone, isNarrow: signal(true), viewport: signal('xs') } });
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'admin', role: 'admin' });
  });

  async function settle(fixture: ComponentFixture<Shell>): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function openEditor() {
    const fixture = createShell();
    await settle(fixture);
    const el = fixture.nativeElement as HTMLElement;
    el.querySelector<HTMLButtonElement>('sb-phone-tab-bar button.more')!.click();
    await settle(fixture);
    const edit = el.querySelector<HTMLButtonElement>('sb-more-sheet button.edit')!;
    edit.click();
    await settle(fixture);
    return { fixture, el, edit };
  }

  const editorOpen = (el: HTMLElement) => el.querySelector('sb-tab-bar-editor dialog')?.hasAttribute('open') ?? false;
  const sheet = (el: HTMLElement) => el.querySelector('sb-more-sheet [role=dialog]');

  it('opens the editor over the More sheet; Escape leaves the sheet; Done returns focus to Edit tab bar', async () => {
    const { fixture, el, edit } = await openEditor();
    expect(editorOpen(el)).toBe(true);
    expect(sheet(el)).not.toBeNull();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(sheet(el)).not.toBeNull();
    el.querySelector<HTMLButtonElement>('sb-tab-bar-editor .actions button.done')!.click();
    await settle(fixture);
    expect(editorOpen(el)).toBe(false);
    expect(sheet(el)).not.toBeNull();
    expect(document.activeElement).toBe(edit);
  });

  it('shows an edit on the bar and in the More sheet at once', async () => {
    const { fixture, el } = await openEditor();
    el.querySelector<HTMLButtonElement>('sb-tab-bar-editor li[data-path="/watchlist"] button.remove')!.click();
    await settle(fixture);
    expect([...el.querySelectorAll('sb-phone-tab-bar .tab-label')].map((n) => n.textContent!.trim()))
      .toEqual(['Home', 'Trades', 'Calendar', 'More']);
    expect([...el.querySelectorAll('sb-more-sheet .group-label')].map((n) => n.textContent!.trim())).toContain('Watchlist');
  });

  it('closes the editor with its sheet when the window leaves phone width', async () => {
    const { fixture, el } = await openEditor();
    phone.set(false);
    await settle(fixture);
    expect(el.querySelector('sb-tab-bar-editor')).toBeNull();
    phone.set(true);
    await settle(fixture);
    expect(editorOpen(el)).toBe(false);
    expect(sheet(el)).toBeNull();
  });
});
```

Every other name used here is already imported in `shell.spec.ts`. No tooltip count here is page-wide (V247-13 carry-over).

- [ ] **Step 2: Run the specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/tab-bar-editor.spec.ts --include src/app/shell/more-sheet.spec.ts --include src/app/shell/shell.spec.ts`
Expected: FAIL: `UNDO_MS` is not exported and there is no `.actions` row; `editRequested`/`button.edit` do not exist; the shell mounts no `sb-tab-bar-editor`.

- [ ] **Step 3: Reset, Undo and Done** in `frontend/src/app/shell/tab-bar-editor.ts`.

Imports become:

```ts
import {
  ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, ElementRef, computed, effect, inject, input, output, signal, untracked,
} from '@angular/core';

import { Button } from '../ui/button';
```

(keep the `Icon`, `Drawer`, `NavEntry`, `tab-bar-prefs` imports), and `imports: [Drawer, Icon, Button]`. Below `ADD_LIMIT_REASON` add:

```ts
/** How long Reset's inline Undo stays (spec v240 §6). */
export const UNDO_MS = 8000;
```

In the template, insert just before `<p class="announce" …>`:

```html
        <div class="actions">
          <button sb-button variant="secondary" type="button" class="reset"
                  [attr.aria-disabled]="prefs.isDefault() ? 'true' : null" (click)="reset()">Reset</button>
          @if (undoPaths()) {
            <button sb-button variant="secondary" type="button" class="undo" (click)="undo()">Undo</button>
          }
          <button sb-button variant="primary" type="button" class="done" (click)="done()">Done</button>
        </div>
```

In `styles`, add before the `.announce` rule:

```css
    .actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-8); margin-top: var(--space-4); }
    .actions button { min-height: 44px; }
    .actions .done { margin-left: auto; }
```

In the class, below `previewLabel`, add:

```ts
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
```

- [ ] **Step 4: The Edit action** in `frontend/src/app/shell/more-sheet.ts`.

In the template, insert before the Close button:

```html
        <button sb-button variant="secondary" type="button" class="edit" (click)="requestEdit($event)">
          <sb-icon name="edit" title="" /> Edit tab bar
        </button>
```

In `MoreSheet`, below `searchRequested`, add:

```ts
  /** Asks the shell for the tab-bar editor (v240 §6). */
  readonly editRequested = output<void>();
  /** True while the editor is open over this sheet: its Escape is the editor's. */
  readonly editing = input(false);
```

Replace `onEscape` with:

```ts
  protected onEscape(): void {
    if (this.open() && !this.editing()) this.closed.emit();
  }

  /** Focus first: the editor's FocusTrap returns focus to whatever held it on open, and Safari does not focus a clicked button. */
  protected requestEdit(event: Event): void {
    (event.currentTarget as HTMLElement).focus();
    this.editRequested.emit();
  }
```

- [ ] **Step 5: Host the editor** in the shell.

`frontend/src/app/shell/shell.html`, the phone block becomes:

```html
  @if (isPhone()) {
    <sb-phone-tab-bar [moreOpen]="moreOpen()" (moreRequested)="toggleMore()" />
    <sb-more-sheet [open]="moreOpen()" [editing]="editorOpen()" (closed)="closeMore()"
                   (searchRequested)="onSearchRequested()" (editRequested)="openEditor()" />
    <!-- v240 §6: the tab-bar editor, over the More sheet, which stays open so
         the editor's FocusTrap can hand focus back to its Edit button. -->
    <sb-tab-bar-editor [open]="editorOpen()" (closed)="closeEditor()" />
  }
```

`frontend/src/app/shell/shell.ts`: import `TabBarEditor` from `./tab-bar-editor` and add it to `imports` beside `MoreSheet`. Replace the `closeMoreOffPhone` effect and `closeMore()` with:

```ts
  /** A sheet left open on a phone must not reappear when the window is
   *  narrowed again later: leaving phone width closes it, and its editor. */
  private readonly closeMoreOffPhone = effect(() => {
    if (!this.isPhone()) untracked(() => this.closeMore());
  });

  protected closeMore(): void {
    this.moreOpen.set(false);
    this.closeEditor();
  }

  /** The tab-bar editor (v240 §6) opens over the More sheet and never outlives it. */
  protected readonly editorOpen = signal(false);

  protected openEditor(): void {
    this.editorOpen.set(true);
  }

  protected closeEditor(): void {
    this.editorOpen.set(false);
  }
```

- [ ] **Step 6: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/tab-bar-editor.spec.ts --include src/app/shell/more-sheet.spec.ts --include src/app/shell/shell.spec.ts --include src/app/shell/phone-tab-bar.spec.ts`
Expected: PASS, 0 failed. If the shell's focus-return test fails, check that `requestEdit` focuses before it emits (the trap records focus when the drawer opens). A 60s `Timeout waiting for worker` is load: re-run once.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/shell/tab-bar-editor.ts frontend/src/app/shell/tab-bar-editor.spec.ts frontend/src/app/shell/more-sheet.ts frontend/src/app/shell/more-sheet.spec.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.spec.ts
git commit -m "feat(v247): Edit tab bar -- Reset with 8s Undo, Done, the More sheet's action, focus back to Edit" -m "The shell hosts the editor over the More sheet; the sheet leaves Escape to it; leaving phone width closes both; shell specs get an in-memory TAB_BAR_STORAGE (spec v240 §6, Decision 15)."
```

### Task V247-16: Browser check at 320/390/820/1440 (rail tooltip, editor round-trip) and the layout audit

**Model:** sonnet — a Playwright script with a small pure helper module under `node --test`, then a run against a local instance; the selectors are all fixed by earlier tasks.

**Files:**
- Create: `frontend/scripts/shell-nav-check-lib.mjs` (pure helpers), `frontend/scripts/shell-nav-check-lib.test.mjs` (run by `tests/scripts/test_node_scripts.py` with every `frontend/scripts/*.test.mjs`)
- Create: `frontend/scripts/shell-nav-check.mjs` (the Playwright driver)

**Interfaces:**
- Consumes (DOM): the rail links' `aria-label` and `aria-describedby` tooltip (V247-8/9; hover delay 300ms, V247-5); `sb-phone-tab-bar .tab`, `.tab-label`, `button.more` (V247-12); `sb-more-sheet button.edit` and the editor's `.act`, `.announce`, `.actions button.*` (V247-14/15); `localStorage['ui.tabbar']` (V247-11). Login: `POST /api/v1/session`, as `layout-audit.mjs` `signInFromEnv` does.
- Produces: nothing later tasks consume. Exit 0 all passed, 1 a check failed, 2 cannot run; `results.json` and a screenshot per viewport in `--out` (default `<tmp>/swingbot-shell-nav-check`).

Decision 4: spec §11's E2E lines (rail tooltip; phone editor round-trip) have no Playwright suite, so a script plus `layout-audit.mjs` at the three widths covers them; spec §9 adds the 320px bar and ≥44px targets. The credentials come from `.env` inside the script (`process.loadEnvFile`) and are never printed, logged or written to `results.json`. The script changes only `localStorage` in its own throwaway browser contexts, never server state, and leaves `ui.tabbar` at the default.

- [ ] **Step 1: Write the failing tests**

Create `frontend/scripts/shell-nav-check-lib.test.mjs`:

```js
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  DEFAULT_BASE, DEFAULT_TABS, EDITED_PATHS, EDITED_TABS, MIN_TARGET_PX, RAIL_PATHS, RAIL_WIDTH_PX, VIEWPORTS,
  exitCode, formatResult, parseArgs, sameList, smallTargets, tooltipVerdict,
} from './shell-nav-check-lib.mjs';

test('parseArgs defaults to the local admin and strips a trailing slash from --base', () => {
  assert.deepEqual(parseArgs([]), { base: DEFAULT_BASE, out: null });
  assert.equal(DEFAULT_BASE, 'http://localhost:1234');
  assert.deepEqual(parseArgs(['--base', 'http://localhost:4123/', '--out', 'x']), { base: 'http://localhost:4123', out: 'x' });
});

test('parseArgs rejects an unknown or incomplete flag', () => {
  assert.throws(() => parseArgs(['--widths', '390']), /unknown or incomplete flag --widths/);
  assert.throws(() => parseArgs(['--base']), /unknown or incomplete flag --base/);
});

test('checks the narrow phone, the phone, the tablet and the desktop (spec v240 §9)', () => {
  assert.deepEqual(VIEWPORTS.map((v) => v.width), [320, 390, 820, 1440]);
  assert.equal(RAIL_WIDTH_PX, 64);
  assert.equal(MIN_TARGET_PX, 44);
});

test('expects the rail order and the round-trip bars the spec names (v240 §5, §6, §11)', () => {
  assert.deepEqual(RAIL_PATHS, ['/dashboard', '/watchlist', '/trades', '/calendar', '/risk', '/insights', '/system']);
  assert.deepEqual(DEFAULT_TABS, ['Home', 'Watchlist', 'Trades', 'Calendar', 'More']);
  assert.deepEqual(EDITED_TABS, ['Home', 'Trades', 'Calendar', 'Risk', 'More']);
  assert.deepEqual(EDITED_PATHS, ['/dashboard', '/trades', '/calendar', '/risk']);
});

test('smallTargets names boxes under 44px on either side, with half a pixel for rounding', () => {
  const boxes = [
    { name: 'ok', width: 44, height: 44 }, { name: 'rounded', width: 43.6, height: 48 },
    { name: 'thin', width: 60, height: 28 }, { name: 'narrow', width: 30, height: 44 },
  ];
  assert.deepEqual(smallTargets(boxes), ['thin', 'narrow']);
  assert.deepEqual(smallTargets([]), []);
});

test('tooltipVerdict names the first thing wrong, or null', () => {
  assert.equal(tooltipVerdict({ name: '', tooltip: 'Risk', visible: true }), 'no-name');
  assert.equal(tooltipVerdict({ name: 'Risk', tooltip: null, visible: false }), 'no-tooltip');
  assert.equal(tooltipVerdict({ name: 'Risk', tooltip: 'Risk', visible: false }), 'not-shown');
  assert.equal(tooltipVerdict({ name: 'Risk', tooltip: 'Heat', visible: true }), 'tooltip-not-name');
  assert.equal(tooltipVerdict({ name: 'Risk', tooltip: 'Risk', visible: true }), null);
});

test('sameList compares in order; exitCode is 0 only when every check passed; formatResult reads PASS/FAIL', () => {
  assert.equal(sameList(['a', 'b'], ['a', 'b']), true);
  assert.equal(sameList(['b', 'a'], ['a', 'b']), false);
  assert.equal(exitCode([{ ok: true }, { ok: true }]), 0);
  assert.equal(exitCode([{ ok: true }, { ok: false }]), 1);
  assert.equal(exitCode([]), 0);
  assert.equal(formatResult({ name: 'rail-width@1440', ok: true, detail: '64px' }), 'PASS rail-width@1440');
  assert.equal(formatResult({ name: 'rail-width@820', ok: false, detail: '80px' }), 'FAIL rail-width@820 -- 80px');
  assert.equal(formatResult({ name: 'x', ok: false, detail: '' }), 'FAIL x');
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test frontend/scripts/shell-nav-check-lib.test.mjs`
Expected: FAIL: `Cannot find module '.../shell-nav-check-lib.mjs'`.

- [ ] **Step 3: Write the helper module**

Create `frontend/scripts/shell-nav-check-lib.mjs`:

```js
/**
 * Pure helpers for shell-nav-check.mjs (v247 V247-16, spec v240 §9, §11):
 * flags, the viewports, the lists the check expects, and its verdicts.
 * No browser here, so `node --test` covers all of it.
 */
export const DEFAULT_BASE = 'http://localhost:1234';
export const MIN_TARGET_PX = 44;
export const RAIL_WIDTH_PX = 64;

/** 320 for the five-tab bar, 390 for the editor, 820 and 1440 for the rail. */
export const VIEWPORTS = Object.freeze([
  { name: 'phone-narrow', width: 320, height: 640 },
  { name: 'phone', width: 390, height: 844 },
  { name: 'tablet', width: 820, height: 1180 },
  { name: 'desktop', width: 1440, height: 900 },
]);

export const RAIL_PATHS = Object.freeze(['/dashboard', '/watchlist', '/trades', '/calendar', '/risk', '/insights', '/system']);
export const DEFAULT_TABS = Object.freeze(['Home', 'Watchlist', 'Trades', 'Calendar', 'More']);
/** After the round-trip's edits: Watchlist removed, Risk added. */
export const EDITED_TABS = Object.freeze(['Home', 'Trades', 'Calendar', 'Risk', 'More']);
export const EDITED_PATHS = Object.freeze(['/dashboard', '/trades', '/calendar', '/risk']);

const FLAGS = new Set(['--base', '--out']);

export function parseArgs(argv) {
  const opts = { base: DEFAULT_BASE, out: null };
  for (let i = 0; i < argv.length; i += 2) {
    const flag = argv[i];
    const value = argv[i + 1];
    if (!FLAGS.has(flag) || value === undefined) throw new Error(`unknown or incomplete flag ${flag}`);
    opts[flag.slice(2)] = flag === '--base' ? value.replace(/\/+$/, '') : value;
  }
  return opts;
}

/** The names of boxes under `min` px on either side; half a pixel is rounding. */
export function smallTargets(boxes, min = MIN_TARGET_PX) {
  return boxes.filter((box) => box.width < min - 0.5 || box.height < min - 0.5).map((box) => box.name);
}

/** null when a rail link's tooltip is shown and reads the link's name; else the first thing wrong. */
export function tooltipVerdict({ name, tooltip, visible }) {
  if (!name) return 'no-name';
  if (tooltip === null) return 'no-tooltip';
  if (!visible) return 'not-shown';
  return tooltip === name ? null : 'tooltip-not-name';
}

export function sameList(actual, expected) {
  return actual.length === expected.length && actual.every((value, index) => value === expected[index]);
}

export function exitCode(results) {
  return results.every((result) => result.ok) ? 0 : 1;
}

export function formatResult({ name, ok, detail }) {
  return `${ok ? 'PASS' : 'FAIL'} ${name}${!ok && detail ? ` -- ${detail}` : ''}`;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test frontend/scripts/shell-nav-check-lib.test.mjs`, then `python scripts/dev/testrun.py file tests/scripts/test_node_scripts.py` (the pytest wrapper that runs it in CI).
Expected: PASS, 0 failed, for both.

- [ ] **Step 5: Write the driver**

Create `frontend/scripts/shell-nav-check.mjs`:

```js
#!/usr/bin/env node
/**
 * v247 V247-16: the shell's navigation in a real browser (spec v240 §9, §11 E2E lines).
 * 1440/820: the rail (64px, order, 44px links, tooltip on hover and focus), no phone nav.
 * 320: the five-tab bar fits. 390: the editor round-trip (remove Watchlist, add Risk, Done,
 * reload, Reset) and its 44px targets.
 *   node frontend/scripts/shell-nav-check.mjs [--base http://localhost:1234] [--out DIR]
 * .env ADMIN_USERNAME/ADMIN_PASSWORD stay in this process, never printed. Exit 0 / 1 failed / 2 cannot run.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import {
  DEFAULT_TABS, EDITED_PATHS, EDITED_TABS, RAIL_PATHS, RAIL_WIDTH_PX, VIEWPORTS,
  exitCode, formatResult, parseArgs, sameList, smallTargets, tooltipVerdict,
} from './shell-nav-check-lib.mjs';

const ENV_FILE = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '.env');
const TAB_KEY = 'ui.tabbar';
const HOVER_WAIT_MS = 450; // HINT_HOVER_DELAY_MS (300) plus a frame
const results = [];

class CannotRun extends Error {}

function check(name, ok, detail = '') {
  const result = { name, ok: Boolean(ok), detail };
  results.push(result);
  console.log(formatResult(result));
}

async function signedInState(browser, base) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const page = await context.newPage();
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  try { process.loadEnvFile(ENV_FILE); } catch { /* no .env: the check below says so */ }
  const { ADMIN_USERNAME: username, ADMIN_PASSWORD: password } = process.env;
  const ok = Boolean(username && password) && await page.evaluate(async ({ url, body }) => (await fetch(url, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })).ok, { url: `${base}/api/v1/session`, body: { username, password } }).catch(() => false);
  const state = ok ? await context.storageState() : null;
  await context.close();
  if (!state) throw new CannotRun(`cannot sign in at ${base}: is the local admin up, and does .env set ADMIN_USERNAME/ADMIN_PASSWORD?`);
  return state;
}

/** Runs in the page: a box per element, named by its aria-label or text. */
function boxesOf(elements) {
  return elements.map((el) => {
    const rect = el.getBoundingClientRect();
    return { name: el.getAttribute('aria-label') ?? el.textContent.trim(), width: rect.width, height: rect.height };
  });
}

/** Runs in the page: the link's name and the role=tooltip its aria-describedby names. */
function tooltipOf(link) {
  const ids = (link.getAttribute('aria-describedby') ?? '').split(/\s+/).filter(Boolean);
  const tip = ids.map((id) => document.getElementById(id)).find((el) => el?.getAttribute('role') === 'tooltip') ?? null;
  const rect = tip?.getBoundingClientRect();
  return { name: link.getAttribute('aria-label') ?? '', tooltip: tip ? tip.textContent.trim() : null, visible: Boolean(rect && rect.width > 0 && rect.height > 0) };
}

async function checkRail(page, at) {
  const links = page.locator('nav.rail a.rail-link');
  await page.locator('nav.rail').waitFor({ state: 'visible', timeout: 15000 });
  const width = await page.locator('nav.rail').evaluate((nav) => nav.getBoundingClientRect().width);
  check(`rail-width@${at}`, Math.round(width) === RAIL_WIDTH_PX, `${width}px`);
  const hrefs = await links.evaluateAll((all) => all.map((a) => a.getAttribute('href')));
  check(`rail-order@${at}`, sameList(hrefs, RAIL_PATHS), hrefs.join(' '));
  const small = smallTargets(await links.evaluateAll(boxesOf));
  check(`rail-targets@${at}`, small.length === 0, small.join(', '));
  for (const [how, path] of [['hover', '/watchlist'], ['focus', '/calendar']]) {
    const link = page.locator(`nav.rail a.rail-link[href="${path}"]`);
    await (how === 'hover' ? link.hover() : link.focus());
    await page.waitForTimeout(HOVER_WAIT_MS);
    const verdict = tooltipVerdict(await link.evaluate(tooltipOf));
    check(`rail-tooltip-${how}@${at}`, verdict === null, verdict ?? '');
    await page.keyboard.press('Escape');
    await page.mouse.move(0, 0);
  }
  const present = await page.evaluate(() =>
    ['sb-phone-tab-bar', 'sb-more-sheet', 'sb-tab-bar-editor'].filter((tag) => document.querySelector(tag)));
  check(`no-phone-nav@${at}`, present.length === 0, present.join(', '));
}

async function checkNarrowBar(page, at) {
  await page.locator('sb-phone-tab-bar').waitFor({ state: 'visible', timeout: 15000 });
  const fit = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const tabs = [...document.querySelectorAll('sb-phone-tab-bar .tab')].map((tab) => tab.getBoundingClientRect());
    return { count: tabs.length, inside: tabs.every((r) => r.left >= 0 && r.right <= vw + 0.5), noScroll: document.documentElement.scrollWidth <= vw };
  });
  check(`tab-bar-fits@${at}`, fit.count === 5 && fit.inside && fit.noScroll, JSON.stringify(fit));
}

const tabLabels = async (page) => (await page.locator('sb-phone-tab-bar .tab-label').allTextContents()).map((s) => s.trim());

async function openEditor(page) {
  await page.locator('sb-phone-tab-bar button.more').click();
  await page.locator('sb-more-sheet button.edit').click();
  await page.locator('sb-tab-bar-editor dialog[open] .editor').waitFor({ state: 'visible', timeout: 5000 });
}

async function closeEditorAndSheet(page) {
  await page.locator('sb-tab-bar-editor .actions button.done').click();
  await page.locator('sb-tab-bar-editor dialog[open]').waitFor({ state: 'detached', timeout: 5000 });
  const focusOnEdit = await page.evaluate(() => document.activeElement?.matches('sb-more-sheet button.edit') ?? false);
  await page.keyboard.press('Escape'); // the More sheet
  await page.locator('sb-more-sheet [role=dialog]').waitFor({ state: 'detached', timeout: 5000 });
  return focusOnEdit;
}

async function editorRoundTrip(page, at, out) {
  await page.evaluate((key) => localStorage.removeItem(key), TAB_KEY);
  await page.reload({ waitUntil: 'load' });
  await page.locator('sb-phone-tab-bar').waitFor({ state: 'visible', timeout: 15000 });
  check(`tabs-default@${at}`, sameList(await tabLabels(page), DEFAULT_TABS), (await tabLabels(page)).join(' '));
  await openEditor(page);
  const small = smallTargets(await page.locator('sb-tab-bar-editor .act, sb-tab-bar-editor .actions button').evaluateAll(boxesOf));
  check(`editor-targets@${at}`, small.length === 0, small.join(', '));
  const sideways = await page.locator('sb-tab-bar-editor dialog').evaluate((d) => d.scrollWidth > d.clientWidth);
  check(`editor-no-sideways-scroll@${at}`, !sideways);
  await page.screenshot({ path: join(out, `editor@${at}.png`) });
  await page.locator('sb-tab-bar-editor li[data-path="/watchlist"] button.remove').click();
  await page.locator('sb-tab-bar-editor li[data-path="/risk"] button.add').click();
  const said = (await page.locator('sb-tab-bar-editor .announce').textContent()).trim();
  check(`editor-announces@${at}`, said === 'Risk added to the tab bar', said);
  check(`editor-focus-returns@${at}`, await closeEditorAndSheet(page));
  check(`tabs-edited@${at}`, sameList(await tabLabels(page), EDITED_TABS), (await tabLabels(page)).join(' '));
  await page.reload({ waitUntil: 'load' });
  await page.locator('sb-phone-tab-bar').waitFor({ state: 'visible', timeout: 15000 });
  check(`tabs-survive-reload@${at}`, sameList(await tabLabels(page), EDITED_TABS), (await tabLabels(page)).join(' '));
  const stored = await page.evaluate((key) => localStorage.getItem(key), TAB_KEY);
  check(`tabs-stored@${at}`, stored === JSON.stringify(EDITED_PATHS), String(stored));
  await openEditor(page);
  await page.locator('sb-tab-bar-editor .actions button.reset').click();
  check(`reset-offers-undo@${at}`, await page.locator('sb-tab-bar-editor .actions button.undo').isVisible());
  await closeEditorAndSheet(page);
  check(`tabs-reset@${at}`, sameList(await tabLabels(page), DEFAULT_TABS), (await tabLabels(page)).join(' '));
}

async function runViewport(browser, state, viewport, base, out) {
  const { width, height } = viewport;
  const context = await browser.newContext({
    storageState: state, viewport: { width, height }, serviceWorkers: 'block', hasTouch: width < 1024, isMobile: width < 640,
  });
  const page = await context.newPage();
  try {
    await page.goto(`${base}/dashboard`, { waitUntil: 'load' });
    if (width >= 640) await checkRail(page, width);
    else if (width < 390) await checkNarrowBar(page, width);
    else await editorRoundTrip(page, width, out);
    await page.screenshot({ path: join(out, `${viewport.name}@${width}.png`) });
  } finally {
    await context.close();
  }
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const out = opts.out ?? join(tmpdir(), 'swingbot-shell-nav-check');
  mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  try {
    const state = await signedInState(browser, opts.base);
    for (const viewport of VIEWPORTS) await runViewport(browser, state, viewport, opts.base, out);
  } finally {
    await browser.close();
  }
  writeFileSync(join(out, 'results.json'), JSON.stringify(results, null, 2));
  console.log(`${results.filter((r) => r.ok).length}/${results.length} passed; shots and results.json in ${out}`);
  return exitCode(results);
}

main().then((code) => process.exit(code), (error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(2);
});
```

- [ ] **Step 6: Run the check and the layout audit against a local instance**

Set up as `docs/claude/ui-design.md` § Checklist says: `/replicate-prod-db`, `cd frontend && npm run build`, copy `frontend/dist/frontend/browser/.` over the gitignored `swingbot/admin/static/app` (check the served `main-*.js` equals `dist`'s; a worktree's `.env` `DATABASE_URL` must point at the replica), then `python admin_ui.py` in the background.

Run: `node frontend/scripts/shell-nav-check.mjs --base http://localhost:1234`
Expected: every line `PASS`, last line `N/N passed`, exit 0. Look at the out dir's screenshots: the editor (rows, preview, Reset/Done) at 390, five tabs at 320, the label-less rail at 820 and 1440.

Run: `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,820,1440` (no `--prune`: that needs 390,768,1440)
Expected: exit 0 (allow-listed findings pass, `rail-label` and `hint` are never allowed).

Fix a failure in a file this plan changed (spec updated, re-run narrowly), then re-run both. A finding on a page this plan never touched goes to the controller's hand-off, not into this task (one page per UI fix task). Stop `admin_ui.py` when done.

- [ ] **Step 7: Commit**

```bash
git add frontend/scripts/shell-nav-check-lib.mjs frontend/scripts/shell-nav-check-lib.test.mjs frontend/scripts/shell-nav-check.mjs
git commit -m "test(v247): browser check -- rail tooltip at 820/1440, tab bar at 320, editor round-trip at 390" -m "Signs in from .env without printing it; layout-audit.mjs ran clean at 390, 820 and 1440 (spec v240 §9, §11 E2E lines)."
```

