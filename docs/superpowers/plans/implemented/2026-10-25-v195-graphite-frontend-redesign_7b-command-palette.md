# v195 — Graphite, Part 7b: the command palette

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-20:" -A 400 <this file>`.

**Scope of this part (V195-20):** split from Part 7 for the 1500-line cap, unchanged. V195-20 mounts the command palette in the shell on V195-19's `SearchIndexStore` and items. It runs after V195-18 (Part 6c: it edits the same four shell files) and V195-19 (Part 7).

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave.** Part 7's "The state earlier tasks leave" list (the shell after V195-18, `nav.ts`, `RouteTitleService`, `DensityService`, the `search` icon, the `primitives.spec.ts` gates and the rule on `title` in new templates) binds this task unchanged. On top of it, V195-19 (Part 7) left `frontend/src/app/stores/search-index.store.ts` (`SearchIndexStore`, `SEARCH_INDEX_TTL_MS`, `SEARCH_INDEX_TRADES_QUERY`) and `frontend/src/app/shell/palette/palette-items.ts` (`PaletteGroup`, `PaletteItem`, `PALETTE_GROUP_ORDER`, `PALETTE_GROUP_LABELS`, `TAB_PAGES`, `PREFERENCE_ITEMS`, `RECENT_TRADES`, `pageItems`, `tickerItems`, `tradeItems`, `rankPaletteItems`, `emptyQueryItems`) as its **Interfaces** block describes. Re-read each file before editing it; every step names its edit by symbol or exact string, never by line number.

---

# Phase 3 — Shell (continued): the command palette

### Task V195-20: Command palette: Ctrl/⌘K, `/` outside text fields and the top-bar trigger; overlay (sheet on phone), focus trap, Esc, ↑/↓/Enter; "tickers unavailable" row; no destructive action registered
**Model:** sonnet — one overlay component on V195-19's pure items plus three entry points in the shell; the care is in the combobox keyboard model, the focus hand-over from the More sheet, `/` never stealing a keystroke from a text field, and the palette never being able to act.

**Files:**
- Create: `frontend/src/app/shell/palette/command-palette.ts`
- Create: `frontend/src/app/shell/palette/command-palette.spec.ts`
- Modify: `frontend/src/app/shell/shell.ts` (imports; `imports` array; `host` key; `paletteOpen`, `paletteShortcut`, `openPalette()`, `closePalette()`, `onGlobalKeydown()`; `onSearchRequested()` body and docblock)
- Modify: `frontend/src/app/shell/shell.html` (the desktop/tablet trigger after `sb-breadcrumb`; `sb-command-palette` after the phone block)
- Modify: `frontend/src/app/shell/shell.css` (the trigger's rules; its shortcut hint hidden under the touch rules)
- Modify: `frontend/src/app/shell/shell.spec.ts` (one new describe)
- Modify: `frontend/src/app/shell/more-sheet.ts` (docblock only: the search field now opens the palette)
- Modify: `frontend/src/app/ui/primitives.spec.ts` (one `RAW_CONTROL_ALLOWLIST` entry, with its reason; not in the ledger row, see "What changes")

**Interfaces:**
- Consumes: `SearchIndexStore` (`tickers()`, `trades()`, `failed()`, `ensure(now?)`), `PaletteItem`, `PALETTE_GROUP_LABELS`, `PREFERENCE_ITEMS`, `pageItems`, `tickerItems`, `tradeItems`, `rankPaletteItems`, `emptyQueryItems` (V195-19); `DensityService.set(d: RowDensity)`, `DENSITY_STORAGE` (V195-6); `FocusTrap` (`[sbFocusTrap]`, `ui/focus-trap.ts`: focuses the first focusable element on init, traps Tab, restores the previously focused element on destroy; skips `tabindex="-1"`); `Button` (`button[sb-button]`, variant `ghost`), `Icon` with `'search'`; the global `.elev-overlay` class and `--scrim-soft`; `stripComments` (`ui/testing/all-sources.ts`); shell `isPhone`, `closeMore()`, `onSearchRequested()`, `moreOpen` (V195-18); `MoreSheet.searchRequested` (V195-18).
- Produces (nothing later consumes these beyond the shell; V195-33's gallery and V195-35's audit do not reach the palette):
  - `CommandPalette` (`sb-command-palette`): `open = input(false)`, `closed = output<void>()`. Open, it renders `div.scrim` and `div.dialog.elev-overlay[role=dialog][aria-modal=true][aria-label="Search or jump"][sbFocusTrap]` holding `input.query[role=combobox][aria-controls="palette-results"][aria-activedescendant]`, `button.close` (sb-button ghost), an optional `p.unavailable[role=status]`, `ul#palette-results[role=listbox]` > `li.option[role=option][id="palette-option-<n>"][aria-selected]` (`span.label`, optional `span.sub`, `span.kind`), and `p.none[role=status]` when nothing matches. `closed` fires on Escape, the scrim, Close and on choosing an item.
  - `isTypingTarget(el: Element | null): boolean`, `isPaletteShortcut(event: KeyboardEvent): boolean`, `shortcutLabel(platform: string): string`, `PALETTE_MAX_RESULTS = 50` (all exported from `command-palette.ts`; the last three are not in the ledger row because only the shell and the spec read them).
  - Shell: `protected readonly paletteOpen = signal(false)`, `protected readonly paletteShortcut` (string), `protected openPalette()`, `protected closePalette()`, `protected onGlobalKeydown(event: KeyboardEvent)`; `onSearchRequested()` now opens the palette. Markup: `header.topbar` > `sb-breadcrumb.topbar-lead`, then (above phone width only) `button.palette-trigger` (`aria-haspopup="dialog"`, `aria-expanded`, `aria-keyshortcuts="Control+K Meta+K /"`, text `Search or jump…` and a `kbd.shortcut`), then `div.status-cluster`, …; `<sb-command-palette [open]="paletteOpen()" (closed)="closePalette()" />` after the phone block, directly before `<sb-toast-host />`.

**What changes, and what is already there.** Spec §3.1: one way to jump anywhere. The palette opens from four places, all through `openPalette()`: Ctrl+K / ⌘K anywhere, `/` when focus is not in a text field, the top-bar trigger ("Search or jump…  Ctrl K", between the breadcrumb and the right cluster, above phone width), and on a phone the search icon and the More sheet's search field, which V195-18 already routes to `onSearchRequested()` (the Part 6 handoff: this task adds the open to that method instead of wiring those two entry points again). `openPalette()` closes the More sheet first so the palette never opens under it, and the palette's element sits after the sheet's in `shell.html`, so in the one change-detection pass that closes one and opens the other, the sheet's `FocusTrap` hands focus back to the More tab before the palette's `FocusTrap` records it as the place to return to. The shortcut is ignored while a native `<dialog>` is open (a confirm dialog or drawer owns the top layer and makes the page inert).

The palette is a modal: a scrim and a centred panel on desktop and tablet, a full-screen sheet on a phone; focus trapped (`FocusTrap`), Escape and the scrim close it, focus returns to whatever opened it. The field is an ARIA combobox over a listbox: ↑/↓ move the active option (wrapping), Enter opens it, a click opens it. Each row shows its label, a muted sub-line and its kind (`Ticker`, `Trade`, `Page`, `Preference`). Empty query: the rail pages and the five newest trades; typed: V195-19's ranking, capped at 50 rows. When the index read failed, a one-line `Tickers unavailable: pages and preferences still work.` sits above the list and pages and preferences still answer. Choosing a page, tab, ticker or trade navigates; choosing a density applies it in place through `DensityService` and stays on the page. Nothing else is reachable: the component injects only `Router`, `SearchIndexStore` and `DensityService` (a spec pins that), and its items are V195-19's data-only items.

The field is the one raw form control this plan adds outside `ui/`: an ARIA combobox needs `role`, `aria-activedescendant`, `aria-controls` and its own arrow and Enter handling, none of which `sb-text-input` exposes, so `primitives.spec.ts`'s `RAW_CONTROL_ALLOWLIST` gains one justified entry (the gate's own rule: an entry needs a reason). Every button goes through `sb-button`. The options are `li[role=option]` with `tabindex="-1"` and a `keydown.enter` binding beside the click, which is what the template accessibility lint (`interactive-supports-focus`, `click-events-have-key-events`) asks of a clickable element; `tabindex="-1"` keeps them out of the Tab order and out of `FocusTrap`'s list, so Tab cycles field and Close only.

- [ ] **Step 1: Write the failing palette tests**

Create `$WT/frontend/src/app/shell/palette/command-palette.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { DENSITY_STORAGE } from '../../ui/density.service';
import { stripComments } from '../../ui/testing/all-sources';
import { CommandPalette, isPaletteShortcut, isTypingTarget, shortcutLabel } from './command-palette';

@Component({ template: '' })
class Blank {}

@Component({
  imports: [CommandPalette],
  template: `<sb-command-palette [open]="open()" (closed)="onClosed()" />`,
})
class Host {
  readonly open = signal(true);
  closes = 0;
  onClosed(): void {
    this.closes += 1;
    this.open.set(false);
  }
}

const TICKERS = {
  tickers: [
    { symbol: 'NVDA', company_name: 'NVIDIA Corp', open_trades: 1, closed_trades: 4 },
    { symbol: 'RIOT', company_name: 'Riot Platforms', open_trades: 0, closed_trades: 0 },
  ],
};
const TRADES = {
  items: [
    { id: '812', ticker: 'NVDA', status: 'ACTIVE', strategy: 'RSI', created_at: '2026-10-20T09:00:00Z', opened_at: '2026-10-20T14:30:00Z' },
    { id: '901', ticker: 'AMD', status: 'PENDING', strategy: 'Fibonacci', created_at: '2026-10-26T09:00:00Z', opened_at: null },
  ],
  total: 2, page: 1, per_page: 200,
};

describe('CommandPalette (v195 §3.1)', () => {
  let stored: Map<string, string>;

  beforeEach(() => {
    stored = new Map();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: '**', component: Blank }]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: DENSITY_STORAGE, useValue: { get: (k: string) => stored.get(k) ?? null, set: (k: string, v: string) => stored.set(k, v) } },
      ],
    });
  });

  afterEach(() => {
    delete document.documentElement.dataset['density'];
  });

  async function settle(fixture: ComponentFixture<Host>): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function mount(answer: 'ok' | 'fail' = 'ok') {
    const fixture = TestBed.createComponent(Host);
    await settle(fixture);
    const http = TestBed.inject(HttpTestingController);
    if (answer === 'ok') {
      http.expectOne((r) => r.url.endsWith('/watchlist/tickers')).flush(TICKERS);
      http.expectOne((r) => r.url.endsWith('/trades')).flush(TRADES);
    } else {
      for (const request of http.match(() => true)) {
        request.flush({ error: { code: 'unavailable', message: 'down' } }, { status: 503, statusText: 'Unavailable' });
      }
    }
    await settle(fixture);
    return { fixture, el: fixture.nativeElement as HTMLElement, host: fixture.componentInstance };
  }

  const field = (el: HTMLElement) => el.querySelector<HTMLInputElement>('input[role=combobox]')!;
  const options = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>('[role=option]')];
  const optionLabels = (el: HTMLElement) => options(el).map((o) => o.querySelector('.label')!.textContent!.trim());
  const activeId = (el: HTMLElement) => field(el).getAttribute('aria-activedescendant');

  async function type(fixture: ComponentFixture<Host>, el: HTMLElement, text: string): Promise<void> {
    field(el).value = text;
    field(el).dispatchEvent(new Event('input'));
    await settle(fixture);
  }

  async function press(fixture: ComponentFixture<Host>, el: HTMLElement, key: string): Promise<void> {
    field(el).dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
    await settle(fixture);
  }

  it('renders nothing while closed and reads the index only when opened', async () => {
    const fixture = TestBed.createComponent(Host);
    fixture.componentInstance.open.set(false);
    await settle(fixture);
    const http = TestBed.inject(HttpTestingController);
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[role=dialog]')).toBeNull();
    http.expectNone(() => true);

    fixture.componentInstance.open.set(true);
    await settle(fixture);
    expect(el.querySelector('[role=dialog]')!.getAttribute('aria-modal')).toBe('true');
    expect(http.match((r) => r.url.endsWith('/watchlist/tickers'))).toHaveLength(1);
    expect(document.activeElement).toBe(field(el));
    expect(field(el).getAttribute('aria-controls')).toBe('palette-results');
  });

  it('shows the rail pages and the most recent trades for an empty query', async () => {
    const { el } = await mount();
    const shown = optionLabels(el);
    expect(shown.slice(0, 3)).toEqual(['Dashboard', 'Watchlist', 'Risk']);
    expect(shown.slice(-2)).toEqual(['AMD #901', 'NVDA #812']);
    expect(shown).toHaveLength(13);
  });

  it('ranks as the query is typed, with the first result active', async () => {
    const { fixture, el } = await mount();
    await type(fixture, el, 'ri');
    expect(optionLabels(el).slice(0, 2)).toEqual(['RIOT', 'Risk']);
    expect(activeId(el)).toBe(options(el)[0].id);
    expect(options(el)[0].getAttribute('aria-selected')).toBe('true');
    expect(options(el)[1].getAttribute('aria-selected')).toBe('false');
    expect(options(el)[0].querySelector('.kind')!.textContent!.trim()).toBe('Ticker');
    expect(options(el)[0].querySelector('.sub')!.textContent!.trim()).toBe('Riot Platforms');
  });

  it('moves with the arrow keys and wraps at both ends', async () => {
    const { fixture, el } = await mount();
    await type(fixture, el, 'ri');
    const last = options(el).length - 1;
    await press(fixture, el, 'ArrowDown');
    expect(activeId(el)).toBe(options(el)[1].id);
    await press(fixture, el, 'ArrowUp');
    await press(fixture, el, 'ArrowUp');
    expect(activeId(el)).toBe(options(el)[last].id);
    await press(fixture, el, 'ArrowDown');
    expect(activeId(el)).toBe(options(el)[0].id);
  });

  it('opens the active page on Enter and closes', async () => {
    const { fixture, el, host } = await mount();
    await type(fixture, el, 'risk');
    await press(fixture, el, 'Enter');
    expect(TestBed.inject(Router).url).toBe('/risk');
    expect(host.closes).toBe(1);
    expect(el.querySelector('[role=dialog]')).toBeNull();
  });

  it('opens a ticker, a plan and a workspace tab at their routes, starting fresh each time', async () => {
    const { fixture, el, host } = await mount();
    const router = TestBed.inject(Router);
    const reopen = async () => {
      host.open.set(true);
      await settle(fixture);
      expect(field(el).value).toBe('');
    };

    await type(fixture, el, 'nvda');
    options(el)[0].click();
    await settle(fixture);
    expect(router.url).toBe('/watchlist/NVDA');

    await reopen();
    await type(fixture, el, '901');
    options(el)[0].click();
    await settle(fixture);
    expect(router.url).toBe('/plans/901');

    await reopen();
    await type(fixture, el, 'logs');
    await press(fixture, el, 'Enter');
    expect(router.url).toBe('/system?tab=logs');
    // Fresh cache: the three reopens read nothing again.
    TestBed.inject(HttpTestingController).expectNone(() => true);
  });

  it('applies a density preference in place, without navigating', async () => {
    const { fixture, el, host } = await mount();
    const router = TestBed.inject(Router);
    const before = router.url;
    await type(fixture, el, 'comf');
    expect(optionLabels(el)).toEqual(['Density: Comfortable']);
    await press(fixture, el, 'Enter');
    expect(document.documentElement.dataset['density']).toBe('comfortable');
    expect(stored.get('ui.density')).toBe('comfortable');
    expect(router.url).toBe(before);
    expect(host.closes).toBe(1);
  });

  it('closes on Escape, on the scrim and on Close', async () => {
    const { fixture, el, host } = await mount();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(host.closes).toBe(1);

    host.open.set(true);
    await settle(fixture);
    el.querySelector<HTMLElement>('.scrim')!.click();
    await settle(fixture);
    expect(host.closes).toBe(2);

    host.open.set(true);
    await settle(fixture);
    el.querySelector<HTMLButtonElement>('button.close')!.click();
    await settle(fixture);
    expect(host.closes).toBe(3);
  });

  it('keeps Tab inside the palette: field and Close, never the options', async () => {
    const { el } = await mount();
    const close = el.querySelector<HTMLButtonElement>('button.close')!;
    expect(options(el).every((o) => o.getAttribute('tabindex') === '-1')).toBe(true);
    close.focus();
    close.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }));
    expect(document.activeElement).toBe(field(el));
    field(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }));
    expect(document.activeElement).toBe(close);
  });

  it('says so when nothing matches, such as a symbol that is not on the watchlist', async () => {
    const { fixture, el } = await mount();
    await type(fixture, el, 'ZZZZ');
    expect(options(el)).toHaveLength(0);
    expect(el.querySelector('.none')!.textContent!.trim()).toBe('No matches for “ZZZZ”');
    expect(activeId(el)).toBeNull();
    await press(fixture, el, 'Enter');
    expect(el.querySelector('[role=dialog]')).not.toBeNull();
  });

  it('still serves pages and preferences when the index cannot be read, and says so in one line', async () => {
    const { fixture, el } = await mount('fail');
    expect(el.querySelector('.unavailable')!.textContent!.trim())
      .toBe('Tickers unavailable: pages and preferences still work.');
    expect(optionLabels(el)).toContain('Dashboard');
    await type(fixture, el, 'dense');
    expect(optionLabels(el)).toEqual(['Density: Dense']);
  });

  it('can only navigate and set density: it injects nothing that acts', () => {
    const source = stripComments(readFileSync(join(process.cwd(), 'src/app/shell/palette/command-palette.ts'), 'utf8'));
    const injected = [...source.matchAll(/inject\((\w+)\)/g)].map(([, name]) => name).sort();
    expect(injected).toEqual(['DensityService', 'Router', 'SearchIndexStore']);
    expect(source).not.toMatch(/ApiClient|EventStream|killswitch|restart|triggerScan|HttpClient/i);
  });
});

describe('palette keyboard helpers (v195 §3.1)', () => {
  const make = (html: string): Element => {
    const holder = document.createElement('div');
    holder.innerHTML = html;
    return holder.firstElementChild!;
  };

  it('treats text fields as typing targets, and nothing else', () => {
    expect(isTypingTarget(make('<input type="text">'))).toBe(true);
    expect(isTypingTarget(make('<input>'))).toBe(true);
    expect(isTypingTarget(make('<input type="search">'))).toBe(true);
    expect(isTypingTarget(make('<textarea></textarea>'))).toBe(true);
    expect(isTypingTarget(make('<select></select>'))).toBe(true);
    expect(isTypingTarget(make('<div contenteditable="true"><span>x</span></div>').firstElementChild)).toBe(true);
    expect(isTypingTarget(make('<input type="checkbox">'))).toBe(false);
    expect(isTypingTarget(make('<button>Go</button>'))).toBe(false);
    expect(isTypingTarget(make('<div contenteditable="false"></div>'))).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });

  it('opens on Ctrl+K or ⌘K anywhere, and on / only outside a text field', () => {
    const input = document.createElement('input');
    const shortcut = (init: KeyboardEventInit, target?: Element) => {
      const event = new KeyboardEvent('keydown', init);
      if (target) Object.defineProperty(event, 'target', { value: target });
      return isPaletteShortcut(event);
    };
    expect(shortcut({ key: 'k', ctrlKey: true })).toBe(true);
    expect(shortcut({ key: 'K', metaKey: true })).toBe(true);
    expect(shortcut({ key: 'k', ctrlKey: true }, input)).toBe(true);
    expect(shortcut({ key: 'k' })).toBe(false);
    expect(shortcut({ key: 'k', ctrlKey: true, altKey: true })).toBe(false);
    expect(shortcut({ key: '/' }, document.body)).toBe(true);
    expect(shortcut({ key: '/' }, input)).toBe(false);
    expect(shortcut({ key: '/', ctrlKey: true }, document.body)).toBe(false);
    expect(shortcut({ key: 'Enter' })).toBe(false);
  });

  it('names the shortcut for the platform', () => {
    expect(shortcutLabel('MacIntel')).toBe('⌘K');
    expect(shortcutLabel('iPhone')).toBe('⌘K');
    expect(shortcutLabel('Win32')).toBe('Ctrl K');
    expect(shortcutLabel('')).toBe('Ctrl K');
  });
});
```

- [ ] **Step 2: Write the failing shell tests**

In `$WT/frontend/src/app/shell/shell.spec.ts`, at the end of the file (after `describe('shell above phone width (v195 Phase 3)', ...)`), append:

```ts

describe('shell command palette (v195 §3.1)', () => {
  let phone: WritableSignal<boolean>;

  beforeEach(() => {
    phone = signal(false);
    TestBed.configureTestingModule({ providers: shellProviders() });
    TestBed.overrideProvider(ViewportService, {
      useValue: { isPhone: phone, isNarrow: signal(false), viewport: signal('md') },
    });
  });

  afterEach(() => {
    document.querySelectorAll('.palette-probe').forEach((node) => node.remove());
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

  const palette = (el: HTMLElement) => el.querySelector('sb-command-palette [role=dialog]');
  const keydown = (init: KeyboardEventInit, target: EventTarget = document.body) =>
    target.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init }));
  const escape = () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  const probe = <T extends HTMLElement>(tag: string): T => {
    const node = document.createElement(tag) as T;
    node.classList.add('palette-probe');
    document.body.appendChild(node);
    return node;
  };

  it('puts the trigger between the breadcrumb and the cluster, and opens the palette from it', async () => {
    const { fixture, el } = await mount();
    const trigger = el.querySelector<HTMLButtonElement>('header.topbar > button.palette-trigger')!;
    expect(trigger.previousElementSibling!.matches('sb-breadcrumb.topbar-lead')).toBe(true);
    expect(trigger.nextElementSibling!.matches('div.status-cluster')).toBe(true);
    expect(trigger.textContent).toContain('Search or jump…');
    expect(trigger.getAttribute('aria-keyshortcuts')).toBe('Control+K Meta+K /');
    expect(trigger.querySelector('kbd.shortcut')!.getAttribute('aria-hidden')).toBe('true');
    expect(palette(el)).toBeNull();

    trigger.focus();
    trigger.click();
    await settle(fixture);
    expect(palette(el)).not.toBeNull();
    expect(trigger.getAttribute('aria-expanded')).toBe('true');

    // Closing hands focus back to the trigger (FocusTrap's restore).
    escape();
    await settle(fixture);
    expect(palette(el)).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('opens on Ctrl+K and on ⌘K', async () => {
    const { fixture, el } = await mount();
    expect(keydown({ key: 'k', ctrlKey: true })).toBe(false); // default prevented
    await settle(fixture);
    expect(palette(el)).not.toBeNull();
    escape();
    await settle(fixture);
    keydown({ key: 'k', metaKey: true });
    await settle(fixture);
    expect(palette(el)).not.toBeNull();
  });

  it('opens on / outside a text field, and leaves / to the field inside one', async () => {
    const { fixture, el } = await mount();
    const field = probe<HTMLInputElement>('input');
    expect(keydown({ key: '/' }, field)).toBe(true); // not prevented: the slash is typed
    await settle(fixture);
    expect(palette(el)).toBeNull();
    keydown({ key: '/' });
    await settle(fixture);
    expect(palette(el)).not.toBeNull();
  });

  it('never opens over an open dialog', async () => {
    const { fixture, el } = await mount();
    probe<HTMLDialogElement>('dialog').setAttribute('open', '');
    keydown({ key: 'k', ctrlKey: true });
    await settle(fixture);
    expect(palette(el)).toBeNull();
  });

  it('opens from the phone search icon and from the More sheet, focus landing in its field', async () => {
    phone.set(true);
    const { fixture, el } = await mount();
    expect(el.querySelector('button.palette-trigger')).toBeNull();

    el.querySelector<HTMLButtonElement>('header.topbar button.search-trigger')!.click();
    await settle(fixture);
    expect(palette(el)).not.toBeNull();
    escape();
    await settle(fixture);

    el.querySelector<HTMLButtonElement>('sb-phone-tab-bar button.more')!.click();
    await settle(fixture);
    el.querySelector<HTMLButtonElement>('sb-more-sheet button.search')!.click();
    await settle(fixture);
    // The sheet closes first, then the palette opens: never one under the other.
    expect(el.querySelector('sb-more-sheet [role=dialog]')).toBeNull();
    expect(palette(el)).not.toBeNull();
    expect(document.activeElement).toBe(el.querySelector('sb-command-palette input[role=combobox]'));
  });

  it('mounts the palette after the More sheet, so a hand-over restores focus in that order', () => {
    const html = readSource('src/app/shell/shell.html');
    expect(html.indexOf('<sb-command-palette')).toBeGreaterThan(html.indexOf('<sb-more-sheet'));
    expect(html.indexOf('<sb-command-palette')).toBeLessThan(html.indexOf('<sb-toast-host'));
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/palette/command-palette.spec.ts --include src/app/shell/shell.spec.ts
```

Expected: FAIL. `command-palette.spec.ts` does not compile (`./command-palette` does not exist). In `shell.spec.ts` every `shell command palette` case fails (no trigger, no `sb-command-palette`); the earlier describes still pass.

- [ ] **Step 4: Create `command-palette.ts`**

Create `$WT/frontend/src/app/shell/palette/command-palette.ts`:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { Router } from '@angular/router';

import { SearchIndexStore } from '../../stores/search-index.store';
import { Button } from '../../ui/button';
import { DensityService } from '../../ui/density.service';
import { FocusTrap } from '../../ui/focus-trap';
import { Icon } from '../../ui/icon';
import {
  PALETTE_GROUP_LABELS,
  PREFERENCE_ITEMS,
  PaletteItem,
  emptyQueryItems,
  pageItems,
  rankPaletteItems,
  tickerItems,
  tradeItems,
} from './palette-items';

/** The longest list rendered for a typed query; the ranking puts the best first. */
export const PALETTE_MAX_RESULTS = 50;

/** Input types that take no typing, so `/` there may open the palette. */
const NON_TEXT_INPUT_TYPES = new Set([
  'button', 'checkbox', 'color', 'file', 'hidden', 'image', 'radio', 'range', 'reset', 'submit',
]);

/** True when a keystroke on `el` is someone typing: `/` must reach it. */
export function isTypingTarget(el: Element | null): boolean {
  if (!el) return false;
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) return true;
  if (el instanceof HTMLInputElement) return !NON_TEXT_INPUT_TYPES.has(el.type);
  return el.closest('[contenteditable]:not([contenteditable="false"])') !== null;
}

/** Ctrl+K or ⌘K anywhere; a bare `/` only outside a text field (spec §3.1). */
export function isPaletteShortcut(event: KeyboardEvent): boolean {
  if (event.altKey) return false;
  if (event.key === 'k' || event.key === 'K') return event.ctrlKey || event.metaKey;
  if (event.key !== '/' || event.ctrlKey || event.metaKey) return false;
  return !isTypingTarget(event.target instanceof Element ? event.target : null);
}

/** The trigger's hint: `⌘K` on Apple platforms, `Ctrl K` everywhere else. */
export function shortcutLabel(platform: string): string {
  return /mac|iphone|ipad/i.test(platform) ? '⌘K' : 'Ctrl K';
}

const STEPS = new Map<string, number>([['ArrowDown', 1], ['ArrowUp', -1]]);

const optionId = (index: number): string => `palette-option-${index}`;

/**
 * The command palette -- v195 §3.1: jump to a ticker, a trade or plan, a
 * page or a workspace tab, or set the row density.
 *
 * Navigation and preferences only. It injects the router, the search index
 * and the density service and nothing else, and its items are plain data
 * (palette-items.ts), so no path through it can act on the book or the bot.
 * command-palette.spec.ts pins the injections.
 *
 * A modal: scrim plus a centred panel (a full-screen sheet below 640px),
 * focus trapped and returned to whatever opened it (FocusTrap). The field is
 * an ARIA combobox over a listbox: the arrows move the active option, Enter
 * or a click opens it, Escape and the scrim close. The options take
 * `tabindex="-1"`, so Tab cycles the field and Close only.
 *
 * The shell owns the open state; this asks to close (`closed`). Opening
 * starts fresh (empty query, first row active) and asks the index for its
 * rows, which it reads once and caches (SearchIndexStore).
 */
@Component({
  selector: 'sb-command-palette',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, FocusTrap, Icon],
  host: { '(document:keydown.escape)': 'onEscape()' },
  template: `
    @if (open()) {
      <div class="scrim" aria-hidden="true" (click)="closed.emit()"></div>
      <div class="dialog elev-overlay" role="dialog" aria-modal="true" aria-label="Search or jump" sbFocusTrap>
        <div class="field">
          <span class="glyph" aria-hidden="true"><sb-icon name="search" /></span>
          <input
            class="query"
            type="text"
            role="combobox"
            autocomplete="off"
            spellcheck="false"
            aria-label="Search tickers, trades, pages and preferences"
            aria-autocomplete="list"
            aria-expanded="true"
            aria-controls="palette-results"
            [attr.aria-activedescendant]="activeId()"
            placeholder="Search or jump…"
            [value]="query()"
            (input)="onInput($any($event.target).value)"
            (keydown)="onKeydown($event)"
          />
          <button sb-button variant="ghost" type="button" class="close" (click)="closed.emit()">Close</button>
        </div>
        @if (index.failed()) {
          <p class="unavailable" role="status">Tickers unavailable: pages and preferences still work.</p>
        }
        <ul id="palette-results" class="results" role="listbox" aria-label="Results">
          @for (item of results(); track item.key; let i = $index) {
            <li
              class="option"
              role="option"
              tabindex="-1"
              [id]="optionId(i)"
              [class.active]="i === active()"
              [attr.aria-selected]="i === active()"
              (mousemove)="active.set(i)"
              (click)="choose(item)"
              (keydown.enter)="choose(item)"
            >
              <span class="label">{{ item.label }}</span>
              @if (item.sub) {
                <span class="sub">{{ item.sub }}</span>
              }
              <span class="kind">{{ kindOf(item) }}</span>
            </li>
          }
        </ul>
        @if (results().length === 0) {
          <p class="none" role="status">No matches for “{{ query().trim() }}”</p>
        }
      </div>
    }
  `,
  styles: `
    :host { display: contents; }
    .scrim { position: fixed; inset: 0; z-index: 40; background: var(--scrim-soft); }
    .dialog {
      position: fixed;
      z-index: 41;
      top: 12vh;
      left: 50%;
      transform: translateX(-50%);
      width: min(640px, calc(100vw - 2 * var(--space-20)));
      max-height: 70vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .field {
      display: flex;
      align-items: center;
      gap: var(--space-8);
      padding: var(--space-6) var(--space-10);
      border-bottom: 1px solid var(--border);
    }
    .field:focus-within { border-bottom-color: var(--accent); }
    .glyph { display: inline-flex; line-height: 0; color: var(--text-muted); }
    .query {
      flex: 1 1 auto;
      min-width: 0;
      min-height: var(--control-h);
      border: 0;
      background: none;
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
    }
    .query::placeholder { color: var(--text-muted); }
    /* The field's own ring would sit inside the panel edge; the accent rule
       under the field row (.field:focus-within) is the focus cue. */
    .query:focus-visible { outline: none; }
    .results { flex: 1 1 auto; margin: 0; padding: var(--space-4); overflow-y: auto; list-style: none; }
    .option {
      display: flex;
      align-items: center;
      gap: var(--space-8);
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      border-radius: var(--control-radius);
      color: var(--text-secondary);
      cursor: pointer;
      transition: background var(--transition), color var(--transition);
    }
    .option.active { background: var(--surface-raised); color: var(--text); }
    .label, .sub { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .label { flex: 0 1 auto; font-size: var(--text-body); }
    .sub { flex: 1 1 auto; color: var(--text-muted); font-size: var(--text-table); }
    .kind { flex: none; margin-left: auto; color: var(--text-muted); font-size: var(--text-micro); }
    .unavailable, .none { margin: 0; padding: var(--space-8) var(--space-14); color: var(--text-muted); font-size: var(--text-table); }
    @media (max-width: 639px) {
      .dialog {
        inset: 0;
        transform: none;
        width: auto;
        max-height: none;
        border-radius: 0;
        padding-bottom: env(safe-area-inset-bottom);
      }
    }
  `,
})
export class CommandPalette {
  readonly open = input(false);
  readonly closed = output<void>();

  protected readonly index = inject(SearchIndexStore);
  private readonly density = inject(DensityService);
  private readonly router = inject(Router);

  protected readonly query = signal('');
  protected readonly active = signal(0);
  protected readonly optionId = optionId;

  private readonly pages = pageItems();

  private readonly items = computed<PaletteItem[]>(() => [
    ...tickerItems(this.index.tickers()),
    ...tradeItems(this.index.trades()),
    ...this.pages,
    ...PREFERENCE_ITEMS,
  ]);

  protected readonly results = computed<PaletteItem[]>(() =>
    this.query().trim()
      ? rankPaletteItems(this.query(), this.items()).slice(0, PALETTE_MAX_RESULTS)
      : emptyQueryItems(this.items()),
  );

  protected readonly activeId = computed(() => (this.results().length > 0 ? optionId(this.active()) : null));

  constructor() {
    // Each open starts fresh and asks the index (a no-op while its cache is
    // fresh). Untracked: only `open` drives this.
    effect(() => {
      if (!this.open()) return;
      untracked(() => {
        this.query.set('');
        this.active.set(0);
        this.index.ensure();
      });
    });
  }

  protected kindOf(item: PaletteItem): string {
    return PALETTE_GROUP_LABELS[item.group];
  }

  protected onInput(value: string): void {
    this.query.set(value);
    this.active.set(0);
  }

  protected onKeydown(event: KeyboardEvent): void {
    const step = STEPS.get(event.key);
    if (step !== undefined) {
      event.preventDefault();
      this.move(step);
      return;
    }
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const item = this.results()[this.active()];
    if (item) this.choose(item);
  }

  protected choose(item: PaletteItem): void {
    if (item.density) this.density.set(item.density);
    else if (item.route) void this.router.navigate([item.route], { queryParams: item.queryParams ?? {} });
    this.closed.emit();
  }

  protected onEscape(): void {
    if (this.open()) this.closed.emit();
  }

  private move(step: number): void {
    const count = this.results().length;
    if (count === 0) return;
    const next = (this.active() + step + count) % count;
    this.active.set(next);
    // jsdom has no scrollIntoView; a browser keeps the active row in view.
    document.getElementById(optionId(next))?.scrollIntoView?.({ block: 'nearest' });
  }
}
```

- [ ] **Step 5: Allow the combobox field in the form-control gate**

In `$WT/frontend/src/app/ui/primitives.spec.ts`, in `const RAW_CONTROL_ALLOWLIST = new Map<string, string>([`, after the `['workspaces/system/settings-tab.ts', 'type="file"'],` entry, add:

```ts
  // The command palette's field is an ARIA combobox (v195 §3.1): it carries
  // role="combobox", aria-activedescendant and aria-controls and owns the
  // arrow and Enter keys for the listbox under it. sb-text-input wraps a
  // plain field and exposes none of that; growing it a combobox mode for one
  // call site would be the worse trade.
  ['shell/palette/command-palette.ts', 'role="combobox"'],
```

The `every allowlist entry is justified` case reads the comment above each entry; this one has its own.

- [ ] **Step 6: Mount the palette in the shell**

1. `$WT/frontend/src/app/shell/shell.ts`:
   - After `import { MoreSheet } from './more-sheet';` add `import { CommandPalette, isPaletteShortcut, shortcutLabel } from './palette/command-palette';`.
   - In the `imports` array, after `PhoneTabBar, MoreSheet,` add `CommandPalette,`.
   - In the `@Component({...})` metadata, after `styleUrl: './shell.css',` add `host: { '(document:keydown)': 'onGlobalKeydown($event)' },`. (The shell has no `host` key before this task; if a re-read finds one, add the entry to it instead.)
   - Directly after the `onSearchRequested()` method (V195-18), add:

```ts

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
```

   - Replace the body and docblock of `onSearchRequested()` with:

```ts
  /**
   * The phone's search icon and the More sheet's search field both land
   * here (V195-18); both open the command palette, which closes the sheet
   * first.
   */
  protected onSearchRequested(): void {
    this.openPalette();
  }
```

   Check the imports at the top of `shell.ts` already name `signal` from `@angular/core` (V195-18's `moreOpen` uses it).

2. `$WT/frontend/src/app/shell/shell.html`:
   - In `header.topbar`, directly after `<sb-breadcrumb class="topbar-lead" />`, add:

```html
      <!-- v195 §3.1: the command palette's trigger, centred between the
           breadcrumb and the cluster (both carry an auto left margin, which
           splits the free space). Phones use the search icon instead. -->
      @if (!isPhone()) {
        <button sb-button variant="ghost" type="button" class="palette-trigger"
                aria-haspopup="dialog" [attr.aria-expanded]="paletteOpen()"
                aria-keyshortcuts="Control+K Meta+K /" (click)="openPalette()">
          <span class="glyph" aria-hidden="true"><sb-icon name="search" /></span>
          <span class="trigger-text">Search or jump…</span>
          <kbd class="shortcut" aria-hidden="true">{{ paletteShortcut }}</kbd>
        </button>
      }
```

   - Directly before `  <sb-toast-host />` (so after the `@if (isPhone()) { <sb-phone-tab-bar …/> <sb-more-sheet …/> }` block), add:

```html
  <!-- v195 §3.1: the command palette. After the More sheet on purpose: when
       the sheet's search field opens it, the sheet's focus trap returns focus
       first and the palette's records that as the place to go back to. -->
  <sb-command-palette [open]="paletteOpen()" (closed)="closePalette()" />

```

3. `$WT/frontend/src/app/shell/shell.css`:
   - Directly after the `.topbar-lead { flex: 0 1 auto; min-width: 0; }` rule, add:

```css
/* v195 §3.1: the palette trigger, a field-shaped quiet button. Its auto left
   margin and the cluster's split the free space, so it sits mid-bar. */
.palette-trigger {
  flex: 0 1 260px;
  min-width: 0;
  margin-left: auto;
  justify-content: flex-start;
  gap: var(--space-8);
  border: 1px solid var(--border);
  color: var(--text-muted);
}
.palette-trigger .glyph { display: inline-flex; line-height: 0; }
.palette-trigger .trigger-text {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}
.palette-trigger .shortcut { font-family: var(--font-mono); font-size: var(--text-micro); color: var(--text-muted); }
```

   - In the `@media (pointer: coarse), (max-width: 1023px)` block, after `  .shell { --topbar-h: 48px; }`, add `  .palette-trigger .shortcut { display: none; }` (a touch screen has no shortcut to hint at).

4. `$WT/frontend/src/app/shell/more-sheet.ts`: in the class docblock, the sentence that ends `and the shell decides what opens.` (it wraps across two comment lines, starting at `The search field is first, so it takes focus;`) becomes `The search field is first, so it takes focus; it only asks (searchRequested), and the shell closes the sheet and opens the command palette (V195-20).` No code change.

- [ ] **Step 7: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/palette/command-palette.spec.ts --include src/app/shell/palette/palette-items.spec.ts --include src/app/shell/shell.spec.ts --include src/app/shell/more-sheet.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/title-usage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/motion-home.spec.ts --include src/app/ui/text-styles.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `shell.spec.ts`'s V195-18 phone case `collapses the bar to the title, the two chips, a search icon and the avatar` stays green: the trigger renders only above phone width, so the phone bar still has exactly its five children. `title-usage.spec.ts` finds no new site (no `title` binding in the palette; its icon sits in an `aria-hidden` span). `hit-area.spec.ts` stays green: the one new media rule sits inside the existing `(pointer: coarse), (max-width: 1023px)` block. If the More-sheet focus case finds focus on the More tab, the palette's element sits before the sheet's in `shell.html`: move it after. If `/` opens the palette from the probe field, `isPaletteShortcut` read the wrong target: it must check `event.target`, not `document.activeElement`. If a palette case's navigation has not landed when it asserts the URL, `settle()` was skipped after the click.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. The template accessibility lint passes on the options because each carries `tabindex="-1"` and `(keydown.enter)` beside its `(click)`; the scrim is `aria-hidden`.

- [ ] **Step 8: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`. At 1440: the trigger sits mid-bar reading `Search or jump…` and `Ctrl K`; Ctrl+K opens the palette centred with focus in the field; the empty list shows the eleven pages and up to five recent trades; type a watchlist symbol and press Enter: its ticker page opens and the palette closes; reopen with `/` (focus on the page body), type `logs`, Enter: System opens on Logs; reopen, type `comf`, Enter: rows grow to 44px and the page did not change; type `/` into the Trades search field: the slash is typed and nothing opens; Escape returns focus to the trigger. At 768: the trigger shows without the `Ctrl K` hint and nothing in the bar overflows (`document.querySelector('header.topbar').scrollWidth <= clientWidth`). At 390 (touch context): no trigger; the search icon opens the palette as a full-screen sheet; More, then its search field, opens the same sheet with the More sheet gone; every row is at least 44px tall. Save the PNGs under the session scratchpad.

- [ ] **Step 9: Close**

Close: standard (test: `frontend/src/app/shell/palette/command-palette.spec.ts`), plus `frontend/src/app/shell/shell.spec.ts` and `frontend/src/app/ui/primitives.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/shell/palette/command-palette.ts frontend/src/app/shell/palette/command-palette.spec.ts frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts frontend/src/app/shell/more-sheet.ts frontend/src/app/ui/primitives.spec.ts
git -C "$WT" commit -m "feat(v195): command palette in the shell (V195-20)" -m "Spec §3.1: Ctrl/⌘K, / outside a text field, a top-bar trigger between the breadcrumb and the cluster, and on a phone the search icon and the More sheet's field (through onSearchRequested) open one palette. A modal combobox over a listbox: focus trapped and returned, Escape and the scrim close, arrows move and wrap, Enter or a click opens a ticker, trade or plan, page or tab, or applies a density in place. Empty query: the rail pages and the five newest trades; a failed index read leaves one 'Tickers unavailable' line and pages and preferences working. It injects only the router, the search index and the density service, so nothing destructive or money-moving is reachable from it. primitives.spec.ts allows the one combobox field, with its reason." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

