# v195 — Graphite, Part 6c: the phone shell

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-18:" -A 400 <this file>`.

**Scope of this part (V195-18):** split from Part 6b for the 1500-line cap, unchanged. V195-18 gives phones the bottom tab bar and the More sheet, and collapses the phone top bar to the page title, the two chips and a search icon. It runs after V195-17 (Part 6b): both rewrite the same four shell files.

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave.** Part 6's "The state earlier tasks leave" list covers everything up to V195-15, and its rule on `title` in new templates binds the new components here too (no `title` binding in any `.ts` template; an icon inside a link sits in an `aria-hidden` span). On top of that, V195-16 left the shell as its **Interfaces** block in Part 6 describes: `nav.rail` with `a.rail-link` entries and anchored hints, `header.topbar` (sticky, 40px, 48px in the touch block) leading with `sb-breadcrumb.topbar-lead`, then `div.topbar-tape`, `div.status-cluster` (`sb-connection-status`, `span.clock`) and `sb-profile-menu`; the killswitch strip; `main.workspace` with `sb-scan-progress` at its top; no `<h1>`; no `viewport` or `titles` field in `shell.ts`; and the new shell spec helpers `Blank`, `shellProviders(routes)` and `readSource(path)` after `FakeEventStream` in `shell.spec.ts`. Re-read each file before editing it; every step names its edit by symbol or exact string, never by line number. V195-17 (Part 6b) then left the shell as its **Interfaces** block describes: `header.topbar` > `sb-breadcrumb.topbar-lead`, `div.status-cluster` (`sb-killswitch-chip`, `sb-freshness-chip`, `sb-connection-status`, `span.clock`), `sb-profile-menu` (with `[density]`/`(densityChanged)`), `sb-scan-progress` as the bar's last child; then `div.tape-strip`, the killswitch strip and `main.workspace`; `shell.ts` has `density`, a protected `clock`, and `killswitchOn = signal<boolean | null>(null)`; `shell.spec.ts` imports `DENSITY_STORAGE` and ends with `describe('shell top-bar cluster (v195 Phase 3)', ...)`.

---

# Phase 3 — Shell (rebuilt, continued)

### Task V195-18: Phone: top bar collapses to title, killswitch and freshness chips and a search icon; bottom tab bar (56px + safe area); More sheet with the remaining pages and the search field
**Model:** sonnet — two presentational components over `NAV_GROUPS`/`PHONE_TABS` and a phone branch in the shell; the care is in the sheet's modal behaviour (focus trap, Escape, scrim, close on navigation) and in the grid not gaining a stray row from the new hosts.

**Files:**
- Create: `frontend/src/app/shell/phone-tab-bar.ts`
- Create: `frontend/src/app/shell/phone-tab-bar.spec.ts`
- Create: `frontend/src/app/shell/more-sheet.ts`
- Create: `frontend/src/app/shell/more-sheet.spec.ts`
- Modify: `frontend/src/app/shell/shell.ts` (imports; `imports` array; `isPhone`, `moreOpen`, the off-phone effect, `toggleMore`, `closeMore`, `onSearchRequested`)
- Modify: `frontend/src/app/shell/shell.html` (a phone search button in the top bar; the tab bar and the sheet after `div.main`)
- Modify: `frontend/src/app/shell/shell.css` (the phone block hides the rail, drops the rail column and reserves the tab bar's height)
- Modify: `frontend/src/app/shell/shell.spec.ts` (two new describes)

**Interfaces:**
- Consumes: `NAV_GROUPS`, `PHONE_TABS`, `NavGroup`, `navEntryFor` (`shell/nav.ts`, V195-15); `KillswitchChip`, `FreshnessChip` and the V195-17 top-bar markup; `ViewportService.isPhone` (`ui/breakpoints.ts`, root; true below 640px); `FocusTrap` (`[sbFocusTrap]`, `ui/focus-trap.ts`: focuses the first focusable element on init, traps Tab, restores focus on destroy); `Icon` with `'search'` and `'more'` (`ui/icon.ts`); `Button` (`ui/button.ts`); the global `.elev-overlay` and `.sb-sheet-in` classes (`styles.css`, `styles/motion.css`); `--scrim-soft` (`tokens.css`).
- Produces (V195-20 consumes these):
  - `PhoneTabBar` (`sb-phone-tab-bar`): `moreOpen = input(false)`, `moreRequested = output<void>()`. Renders `nav[aria-label="Main pages"]` with one `a.tab` per `PHONE_TABS` entry (`aria-current="page"` on the tab `navEntryFor(url)` resolves to, so `/plans/7` lights Trades) and a `button.tab.more` (`aria-haspopup="dialog"`, `aria-expanded` = `moreOpen()`, class `active` when the sheet is open or the current page is not on the bar). Fixed to the bottom, `height: calc(56px + env(safe-area-inset-bottom))`.
  - `MoreSheet` (`sb-more-sheet`): `open = input(false)`, `closed = output<void>()`, `searchRequested = output<void>()`. Open, it renders a scrim and `div.sheet[role=dialog][aria-modal=true][aria-label="More"][sbFocusTrap]` holding `button.search` ("Search or jump…", first, so it takes focus), the remaining pages grouped as `p.group-label` + `ul.pages` > `li` > `a.page`, and `button.close`. `closed` fires on Escape, on the scrim, on Close and on choosing a page. `morePageGroups(groups?: readonly NavGroup[], tabs?: readonly NavEntry[]): NavGroup[]` (exported; `NAV_GROUPS` minus the `PHONE_TABS` entries, empty groups dropped).
  - Shell: `protected readonly isPhone` (`ViewportService.isPhone`), `protected readonly moreOpen = signal(false)`, `protected toggleMore()`, `protected closeMore()`, `protected onSearchRequested()` (closes the sheet; **V195-20 adds the palette open to it**, so the phone search icon and the sheet's search field reach the palette through this one method). Phone-only top-bar control: `button.search-trigger` (`aria-label="Search or jump to a page"`), between `div.status-cluster` and `sb-profile-menu`.

**What changes, and what is already there.** Below 640px the shell has kept V195-16's 48px rail beside the page; Phase 3 gives the phone its own frame instead. The rail is hidden and its column dropped; a bottom tab bar holds Dashboard · Watchlist · Trades · Risk (`PHONE_TABS`) and More, at 56px plus the safe-area inset, and the page reserves that height so its last row is never under the bar. Risk is a tab, so the halt is two taps from anywhere (the killswitch chip in the top bar, then Risk's header control). More opens a bottom sheet with the seven pages the bar does not hold, grouped as on the rail, and the search field (V195-20 opens the palette from it). The top bar on a phone already shows only the current crumb (`sb-breadcrumb`'s own 639px rule, V195-15), the chips (V195-17) and, with the clock and tape hidden since V195-16/V195-17, the avatar; this task adds the search icon. The avatar stays on the phone bar: it is the only way to sign out, change text size, Motion or Density there, which the spec's phone list does not place elsewhere (see the OPEN note in the plan return). Toasts (`toast-host.ts`, `z-index: 10`, 20px from the bottom) stay above the tab bar (`z-index: 8`) and may cover it while they show; the sheet (`z-index: 30/31`) covers both.

- [ ] **Step 1: Write the failing tab-bar tests**

Create `$WT/frontend/src/app/shell/phone-tab-bar.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { PHONE_TABS } from './nav';
import { PhoneTabBar } from './phone-tab-bar';

@Component({ template: '' })
class Blank {}

describe('PhoneTabBar (v195 Phase 3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([{ path: '**', component: Blank }])],
    });
  });

  async function mount(url: string, moreOpen = false) {
    await TestBed.inject(Router).navigateByUrl(url);
    const fixture = TestBed.createComponent(PhoneTabBar);
    fixture.componentRef.setInput('moreOpen', moreOpen);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  const current = (el: HTMLElement) =>
    [...el.querySelectorAll('a.tab[aria-current="page"]')].map((a) => a.querySelector('.tab-label')!.textContent!.trim());

  it('holds Dashboard, Watchlist, Trades, Risk and More, in that order', async () => {
    const { el } = await mount('/dashboard');
    expect(el.querySelector('nav')!.getAttribute('aria-label')).toBe('Main pages');
    expect([...el.querySelectorAll('.tab .tab-label')].map((n) => n.textContent!.trim()))
      .toEqual(['Dashboard', 'Watchlist', 'Trades', 'Risk', 'More']);
    expect([...el.querySelectorAll('a.tab')].map((a) => a.getAttribute('href')))
      .toEqual(PHONE_TABS.map((tab) => tab.path));
  });

  it('marks the current tab, and the list tab for its detail pages', async () => {
    expect(current((await mount('/risk')).el)).toEqual(['Risk']);
    expect(current((await mount('/plans/7')).el)).toEqual(['Trades']);
    expect(current((await mount('/watchlist/NVDA')).el)).toEqual(['Watchlist']);
  });

  it('lights More for a page the bar does not hold', async () => {
    const { el } = await mount('/calendar');
    expect(current(el)).toEqual([]);
    expect(el.querySelector('button.tab.more')!.classList).toContain('active');
  });

  it('asks for the More sheet and reports it open', async () => {
    const { fixture, el } = await mount('/dashboard');
    let asked = 0;
    fixture.componentInstance.moreRequested.subscribe(() => (asked += 1));
    const more = el.querySelector<HTMLButtonElement>('button.tab.more')!;
    expect(more.getAttribute('aria-haspopup')).toBe('dialog');
    expect(more.getAttribute('aria-expanded')).toBe('false');
    expect(more.classList).not.toContain('active');
    more.click();
    expect(asked).toBe(1);
    fixture.componentRef.setInput('moreOpen', true);
    fixture.detectChanges();
    expect(more.getAttribute('aria-expanded')).toBe('true');
    expect(more.classList).toContain('active');
  });

  it('keeps every glyph out of the accessible name', async () => {
    const { el } = await mount('/dashboard');
    const icons = [...el.querySelectorAll('sb-icon')];
    expect(icons).toHaveLength(5);
    for (const icon of icons) {
      expect(icon.parentElement!.matches('.glyph[aria-hidden="true"]')).toBe(true);
    }
  });

  it('sits on the bottom edge at 56px plus the safe-area inset, under the toasts', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/phone-tab-bar.ts'), 'utf8');
    expect(source).toContain('height: calc(56px + env(safe-area-inset-bottom));');
    expect(source).toContain('padding-bottom: env(safe-area-inset-bottom);');
    expect(source).toMatch(/:host \{[^}]*position: fixed;[^}]*z-index: 8;/s);
  });
});
```

- [ ] **Step 2: Write the failing More-sheet tests**

Create `$WT/frontend/src/app/shell/more-sheet.spec.ts`:

```ts
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { MoreSheet, morePageGroups } from './more-sheet';
import { NAV_GROUPS } from './nav';

@Component({ template: '' })
class Blank {}

describe('morePageGroups (v195 Phase 3)', () => {
  it('keeps the pages the tab bar does not hold, grouped and in rail order', () => {
    expect(morePageGroups().map((group) => [group.label, group.entries.map((entry) => entry.label)])).toEqual([
      ['Review', ['Calendar', 'Cancels']],
      ['Insights', ['Analytics', 'Research', 'Reports']],
      ['System', ['System', 'Versions']],
    ]);
  });

  it('drops a group whose every page is already a tab', () => {
    expect(morePageGroups().some((group) => group.id === 'nav-monitor')).toBe(false);
  });

  it('keeps every group when no tab is given', () => {
    expect(morePageGroups(NAV_GROUPS, [])).toHaveLength(4);
  });
});

describe('MoreSheet (v195 Phase 3)', () => {
  let fixture: ComponentFixture<MoreSheet>;
  let el: HTMLElement;
  let closed: number;
  let searched: number;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([{ path: '**', component: Blank }])],
    });
    fixture = TestBed.createComponent(MoreSheet);
    el = fixture.nativeElement as HTMLElement;
    closed = 0;
    searched = 0;
    fixture.componentInstance.closed.subscribe(() => (closed += 1));
    fixture.componentInstance.searchRequested.subscribe(() => (searched += 1));
    fixture.detectChanges();
  });

  function open(): void {
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
  }

  const dialog = () => el.querySelector<HTMLElement>('[role=dialog]');

  it('renders nothing while closed, and ignores Escape then', () => {
    expect(dialog()).toBeNull();
    expect(el.querySelector('.scrim')).toBeNull();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(closed).toBe(0);
  });

  it('opens as a labelled modal dialog with focus on the search field', () => {
    open();
    expect(dialog()!.getAttribute('aria-modal')).toBe('true');
    expect(dialog()!.getAttribute('aria-label')).toBe('More');
    expect(dialog()!.classList).toContain('elev-overlay');
    expect(document.activeElement).toBe(el.querySelector('button.search'));
    expect(el.querySelector('button.search')!.textContent!.trim()).toBe('Search or jump…');
  });

  it('lists the remaining pages under their group names, linking to each', () => {
    open();
    expect([...el.querySelectorAll('.group-label')].map((n) => n.textContent!.trim()))
      .toEqual(['Review', 'Insights', 'System']);
    expect([...el.querySelectorAll('a.page')].map((a) => [a.textContent!.trim(), a.getAttribute('href')])).toEqual([
      ['Calendar', '/calendar'], ['Cancels', '/cancels'],
      ['Analytics', '/analytics'], ['Research', '/research'], ['Reports', '/reports'],
      ['System', '/system'], ['Versions', '/versions'],
    ]);
    for (const list of el.querySelectorAll('ul.pages')) {
      expect(el.querySelector(`#${list.getAttribute('aria-labelledby')}`)).not.toBeNull();
    }
    for (const icon of el.querySelectorAll('a.page sb-icon')) {
      expect(icon.parentElement!.matches('.glyph[aria-hidden="true"]')).toBe(true);
    }
  });

  it('closes on Escape, on the scrim, on Close and on choosing a page', () => {
    open();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    el.querySelector<HTMLElement>('.scrim')!.click();
    el.querySelector<HTMLButtonElement>('button.close')!.click();
    el.querySelector<HTMLAnchorElement>('a.page')!.click();
    expect(closed).toBe(4);
  });

  it('asks for search from its search field', () => {
    open();
    el.querySelector<HTMLButtonElement>('button.search')!.click();
    expect(searched).toBe(1);
  });
});
```

- [ ] **Step 3: Write the failing shell tests**

In `$WT/frontend/src/app/shell/shell.spec.ts`:

1. Imports. After `import { CLOCK } from '../ui/clock';` add `import { ViewportService } from '../ui/breakpoints';`.

2. At the end of the file, append:

```ts

describe('shell on a phone (v195 Phase 3)', () => {
  let phone: WritableSignal<boolean>;

  beforeEach(() => {
    phone = signal(true);
    TestBed.configureTestingModule({ providers: shellProviders([{ path: 'calendar', component: Blank }]) });
    TestBed.overrideProvider(ViewportService, {
      useValue: { isPhone: phone, isNarrow: signal(true), viewport: signal('xs') },
    });
  });

  async function mount() {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  const sheet = (el: HTMLElement) => el.querySelector('sb-more-sheet [role=dialog]');
  const moreTab = (el: HTMLElement) => el.querySelector<HTMLButtonElement>('sb-phone-tab-bar button.more')!;

  it('swaps the rail for the bottom tab bar, with the More sheet closed', async () => {
    const { el } = await mount();
    expect(el.querySelector('sb-phone-tab-bar')).not.toBeNull();
    expect(sheet(el)).toBeNull();
    const css = readSource('src/app/shell/shell.css');
    const phoneBlock = css.slice(css.indexOf('@media (max-width: 639px)'));
    expect(phoneBlock).toMatch(/\.rail \{ display: none; \}/);
    expect(phoneBlock).toMatch(/\.shell \{ grid-template-columns: 1fr; \}/);
    expect(phoneBlock).toContain('.main { padding-bottom: calc(56px + env(safe-area-inset-bottom)); }');
  });

  it('collapses the bar to the title, the two chips, a search icon and the avatar', async () => {
    const { el } = await mount();
    const bar = el.querySelector('header.topbar')!;
    const order = ['sb-breadcrumb.topbar-lead', 'div.status-cluster', 'button.search-trigger', 'sb-profile-menu', 'sb-scan-progress'];
    expect(bar.children).toHaveLength(order.length);
    order.forEach((selector, index) => expect(bar.children[index].matches(selector), selector).toBe(true));
    const search = bar.querySelector('button.search-trigger')!;
    expect(search.getAttribute('aria-label')).toBe('Search or jump to a page');
    // The magnifier: sb-icon's default label for 'search' (V195-14).
    expect(search.querySelector('sb-icon')!.getAttribute('title')).toBe('Search');
    expect(bar.querySelector('.status-cluster sb-killswitch-chip')).not.toBeNull();
    expect(bar.querySelector('.status-cluster sb-freshness-chip')).not.toBeNull();
  });

  it('opens the More sheet from the More tab, and the tab closes it again', async () => {
    const { fixture, el } = await mount();
    moreTab(el).click();
    await settle(fixture);
    expect(sheet(el)).not.toBeNull();
    expect(moreTab(el).getAttribute('aria-expanded')).toBe('true');
    moreTab(el).click();
    await settle(fixture);
    expect(sheet(el)).toBeNull();
  });

  it('closes the More sheet on Escape and when a page is chosen', async () => {
    const { fixture, el } = await mount();
    moreTab(el).click();
    await settle(fixture);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(sheet(el)).toBeNull();
    moreTab(el).click();
    await settle(fixture);
    el.querySelector<HTMLAnchorElement>('sb-more-sheet a.page[href="/calendar"]')!.click();
    await settle(fixture);
    expect(sheet(el)).toBeNull();
  });

  it('closes the More sheet when its search field is used', async () => {
    const { fixture, el } = await mount();
    moreTab(el).click();
    await settle(fixture);
    el.querySelector<HTMLButtonElement>('sb-more-sheet button.search')!.click();
    await settle(fixture);
    expect(sheet(el)).toBeNull();
  });

  it('forgets an open sheet when the window grows past phone width', async () => {
    const { fixture, el } = await mount();
    moreTab(el).click();
    await settle(fixture);
    phone.set(false);
    await settle(fixture);
    expect(el.querySelector('sb-phone-tab-bar')).toBeNull();
    phone.set(true);
    await settle(fixture);
    expect(sheet(el)).toBeNull();
  });
});

describe('shell above phone width (v195 Phase 3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: shellProviders() });
    TestBed.overrideProvider(ViewportService, {
      useValue: { isPhone: signal(false), isNarrow: signal(false), viewport: signal('md') },
    });
  });

  it('renders no tab bar, no More sheet and no phone search icon', () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-phone-tab-bar')).toBeNull();
    expect(el.querySelector('sb-more-sheet')).toBeNull();
    expect(el.querySelector('button.search-trigger')).toBeNull();
    expect(el.querySelector('nav.rail')).not.toBeNull();
  });
});
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/phone-tab-bar.spec.ts --include src/app/shell/more-sheet.spec.ts --include src/app/shell/shell.spec.ts
```

Expected: FAIL. `phone-tab-bar.spec.ts` and `more-sheet.spec.ts` do not compile (the components do not exist). `shell.spec.ts`: every `shell on a phone` case fails (no tab bar, no search trigger, no phone CSS); `shell above phone width` passes already (it pins that the phone parts never leak above 640px).

- [ ] **Step 5: Create `phone-tab-bar.ts`**

Create `$WT/frontend/src/app/shell/phone-tab-bar.ts`:

```ts
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
```

- [ ] **Step 6: Create `more-sheet.ts`**

Create `$WT/frontend/src/app/shell/more-sheet.ts`:

```ts
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';

import { FocusTrap } from '../ui/focus-trap';
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
 * asks (`searchRequested`) and the shell decides what opens.
 *
 * `display: contents` on the host: the shell's grid must not give this
 * element a cell of its own.
 */
@Component({
  selector: 'sb-more-sheet',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Icon, FocusTrap],
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
        <button type="button" class="close" (click)="closed.emit()">Close</button>
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
    .close {
      min-height: var(--control-h);
      border: 1px solid var(--border);
      border-radius: var(--control-radius);
      background: none;
      color: var(--text-secondary);
      font: inherit;
      cursor: pointer;
    }
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
```

- [ ] **Step 7: The phone branch in the shell**

1. `$WT/frontend/src/app/shell/shell.ts`:
   - After `import { CLOCK } from '../ui/clock';` add `import { ViewportService } from '../ui/breakpoints';` and `import { Button } from '../ui/button';`. After `import { KillswitchChip } from './killswitch-chip';` add `import { MoreSheet } from './more-sheet';` and `import { PhoneTabBar } from './phone-tab-bar';`.
   - In the `imports` array, after `Tape,` add `Button, PhoneTabBar, MoreSheet,`.
   - Directly after the `versionText` computed (V195-16), add:

```ts

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
   * here. The sheet closes first so the palette never opens under it;
   * V195-20 adds the palette open to this method.
   */
  protected onSearchRequested(): void {
    this.closeMore();
  }
```

2. `$WT/frontend/src/app/shell/shell.html`:
   - In `header.topbar`, directly before `<sb-profile-menu`, add:

```html
      <!-- Phone only: the bar collapses to the title, the two chips, this
           search icon and the avatar (the one place to sign out there). -->
      @if (isPhone()) {
        <button sb-button variant="icon" type="button" class="search-trigger"
                aria-label="Search or jump to a page" (click)="onSearchRequested()">
          <sb-icon name="search" />
        </button>
      }
```

   - Directly before `  <sb-toast-host />`, add:

```html
  <!-- v195 Phase 3, phone: the bottom tab bar and its More sheet. Both hosts
       stay out of the grid: the bar is fixed, the sheet's host is
       display: contents. -->
  @if (isPhone()) {
    <sb-phone-tab-bar [moreOpen]="moreOpen()" (moreRequested)="toggleMore()" />
    <sb-more-sheet [open]="moreOpen()" (closed)="closeMore()" (searchRequested)="onSearchRequested()" />
  }

```

3. `$WT/frontend/src/app/shell/shell.css`: inside the `@media (max-width: 639px)` block, after its first line `  .clock { display: none; }`, add:

```css
  /* The phone frame: no rail and no rail column; the page leaves room under
     its last row for the fixed tab bar (phone-tab-bar.ts). */
  .shell { grid-template-columns: 1fr; }
  .rail { display: none; }
  .main { padding-bottom: calc(56px + env(safe-area-inset-bottom)); }
```

   and change that block's opening comment's last sentence to `The breadcrumb already shows only the current crumb below 640px and truncates it with an ellipsis; the rail gives way to the bottom tab bar.`

- [ ] **Step 8: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/phone-tab-bar.spec.ts --include src/app/shell/more-sheet.spec.ts --include src/app/shell/shell.spec.ts --include src/app/ui/title-usage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/elevation.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `title-usage.spec.ts` finds no new site (neither new component binds a `title`; their icons sit in `aria-hidden` spans). `hit-area.spec.ts` stays green: no phone-only `@media (pointer: coarse), (max-width: 639px)` block was added (the new rules sit in the existing width-only phone block). If the sheet's focus case finds focus on `body`, the fixture is not attached to the document: TestBed attaches it by default; do not add a manual `focus()` to the component. If the `forgets an open sheet` case fails, the effect wrote `moreOpen` while tracked: keep the write inside `untracked`.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 9: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`. At 390 (touch context): no rail; the bar shows the current page title, the killswitch and freshness chips, the search icon and the avatar with nothing overflowing; the tab bar sits on the bottom edge at 56px (`getBoundingClientRect().height`), Dashboard lit; scroll the Dashboard to its end and its last row clears the tab bar; tap Risk (lit), then More: the sheet rises with focus on the search field and lists Review (Calendar, Cancels), Insights (Analytics, Research, Reports) and System (System, Versions); tap Calendar: the sheet closes, Calendar loads and More stays lit; reopen More and close it with the scrim and with Close; every tab, page link and button is at least 44px tall. At 768 and 1440: the rail is back, no tab bar, no phone search icon. Save the PNGs under the session scratchpad.

- [ ] **Step 10: Close**

Close: standard (test: `frontend/src/app/shell/shell.spec.ts`), plus `frontend/src/app/shell/phone-tab-bar.spec.ts` and `frontend/src/app/shell/more-sheet.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/shell/phone-tab-bar.ts frontend/src/app/shell/phone-tab-bar.spec.ts frontend/src/app/shell/more-sheet.ts frontend/src/app/shell/more-sheet.spec.ts frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts
git -C "$WT" commit -m "feat(v195): phone tab bar and More sheet (V195-18)" -m "Spec Phase 3: below 640px the rail gives way to a bottom tab bar (Dashboard, Watchlist, Trades, Risk, More; 56px plus the safe-area inset, current tab from the nav model) and a modal More sheet with the seven remaining pages by group and the search field. The phone top bar is the current crumb, the killswitch and freshness chips, a search icon and the avatar. The shell owns the sheet's state; onSearchRequested() closes it, and V195-20 opens the palette from there." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

