# v247 — Doctena night, plan 3 of 5: Shell and navigation — Part 2: Hint API and long-press

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V247-6" -A 400 <this file>`).

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) §5 (rail tooltip: hover delay, focus, long-press, one at a time), §6 (press and hold, the OS must not fight it), §9 (long-press ignores a mouse), §11 (Long-press directive lines, long-press host links gate).
**Index:** [2026-11-23-v247-doctena-night-shell-and-navigation_0-index.md](2026-11-23-v247-doctena-night-shell-and-navigation_0-index.md) — Goal, Global Constraints, Decisions (6 and 7 above all), Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks: V247-5 (`Hint` hover delay, public `dismiss()`, one open hint app-wide), V247-6 (`Hint.openPinned()` and `placement="above"`), V247-7 (the `sbLongPress` directive). V247-5 → V247-6 is sequential (same two files); V247-7 is independent of both and may run beside V247-5.

This part adds API only: no existing caller of `sb-hint` changes, and every existing hint keeps opening at once (`openDelay` defaults to `0`). The rail (part 3) and the tab bar (part 4) are the first consumers.

All frontend commands run from the worktree root; `--include` paths are relative to `frontend/`. Tests drive a zoneless `TestBed` synchronously (`dispatchEvent` then `fixture.detectChanges()`), as `ui/hint.spec.ts` already does. Timer tests fake only `setTimeout`/`clearTimeout` (`vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })`): the open effect calls `requestAnimationFrame`, which must stay real, and nothing here awaits `whenStable()` while the clock is fake.

---

# Phase 2 — Hint API and long-press

### Task V247-5: `Hint`: hover open delay, public `dismiss()`, one open hint app-wide

**Model:** sonnet — a shared UI primitive with three open reasons, a timer and a module-level slot; every existing hint must behave exactly as before.

**Files:**
- Modify: `frontend/src/app/ui/hint.ts` (imports 1-11; after `let nextId = 0;` at 15; the class doc comment 88-126; host bindings 131-139; inputs 236-254; constructor 289-320; `toggle`/`close` 322-331; `onDocumentPointer` 340-342; `watchHostDialog` 361-378; `bindAnchor` 380-411)
- Test: `frontend/src/app/ui/hint.spec.ts` (import at line 7; two host components after `AnchorHost` at 42; two new `describe` blocks appended at the end)

**Interfaces:**
- Consumes: nothing new (`Hint`, `POPOVER_OPEN_ATTR`, `installPopoverPolyfill` exist).
- Produces (consumed by V247-6, V247-8, V247-13):
  - `export const HINT_HOVER_DELAY_MS = 300;` in `ui/hint.ts`
  - `Hint.openDelay = input(0)` — milliseconds; delays only the hover reason
  - `Hint.dismiss(): void` — public; closes every reason and cancels a pending hover. Replaces the protected `close()`, which is deleted.
  - Module-level rule: opening any `sb-hint` (hover, focus, pin) dismisses the hint that was open.

Behaviour, pinned by Decisions 6 and 7 of the index: the delay applies to `mouseenter` only (glyph host and anchor alike); `mouseleave` before it elapses cancels it; focus and click stay immediate. A destroyed hint clears its timer and frees the open slot.

- [ ] **Step 1: Write the failing tests** in `frontend/src/app/ui/hint.spec.ts`.

Change the import on line 7 to:

```ts
import { DIALOG_CLOSING_EVENT, HINT_HOVER_DELAY_MS, Hint, clampPopover, placeBeside, supportsPopover } from './hint';
```

Add `import { By } from '@angular/platform-browser';` below the `@angular/core/testing` import.

Insert these two host components directly after `class AnchorHost { ... }`:

```ts
/** v247 Decision 6: a rail-style label and a glyph hint, both with the hover delay. */
@Component({
  imports: [Hint],
  template: `
    <a #a href="/dashboard" class="link-a" aria-label="Dashboard">D</a>
    <sb-hint class="anchored-hint" [anchor]="a" text="Dashboard" [openDelay]="delay" />
    <sb-hint class="glyph-hint" text="Explained." label="About it" [openDelay]="delay" />
  `,
})
class DelayHost {
  readonly delay = HINT_HOVER_DELAY_MS;
}

/** v247 Decision 7: two rail labels and a glyph hint on one page. */
@Component({
  imports: [Hint],
  template: `
    <a #a href="/dashboard" class="link-a" aria-label="Dashboard">D</a>
    <sb-hint [anchor]="a" text="Dashboard" />
    <a #b href="/watchlist" class="link-b" aria-label="Watchlist">W</a>
    <sb-hint [anchor]="b" text="Watchlist" />
    <sb-hint class="glyph-hint" text="Explained." label="About it" />
    <span class="outside">Elsewhere</span>
  `,
})
class PairHost {}
```

Append at the end of the file:

```ts
describe('Hint hover delay and dismiss() (v247 Decision 6)', () => {
  let fixture: ComponentFixture<DelayHost>;

  beforeEach(async () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(DelayHost);
    fixture.detectChanges();
    await fixture.whenStable();
    // Only the delay timer is faked: the open effect's requestAnimationFrame stays real.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  });

  afterEach(() => vi.useRealTimers());

  const el = () => fixture.nativeElement as HTMLElement;
  const link = () => el().querySelector('a.link-a') as HTMLAnchorElement;
  const popFor = (hint: string) => el().querySelector(`sb-hint.${hint} [role=tooltip]`) as HTMLElement;
  const trigger = () => el().querySelector('sb-hint.glyph-hint button.trigger') as HTMLButtonElement;
  const isOpen = (hint: string) => popFor(hint).hasAttribute(POPOVER_OPEN_ATTR);
  const fire = (target: Element, event: Event) => {
    target.dispatchEvent(event);
    fixture.detectChanges();
  };
  const tick = (ms: number) => {
    vi.advanceTimersByTime(ms);
    fixture.detectChanges();
  };
  const instance = (hint: string): Hint =>
    fixture.debugElement.query(By.css(`sb-hint.${hint}`)).componentInstance as Hint;

  it('exports the 300ms hover delay the rail and the tab bar pass', () => {
    expect(HINT_HOVER_DELAY_MS).toBe(300);
  });

  it('opens an anchor label only once the hover has lasted the delay', () => {
    fire(link(), new MouseEvent('mouseenter'));
    tick(HINT_HOVER_DELAY_MS - 1);
    expect(isOpen('anchored-hint')).toBe(false);
    tick(1);
    expect(isOpen('anchored-hint')).toBe(true);
    fire(link(), new MouseEvent('mouseleave'));
    expect(isOpen('anchored-hint')).toBe(false);
  });

  it('never opens for a pointer that leaves before the delay', () => {
    fire(link(), new MouseEvent('mouseenter'));
    tick(HINT_HOVER_DELAY_MS - 50);
    fire(link(), new MouseEvent('mouseleave'));
    tick(HINT_HOVER_DELAY_MS);
    expect(isOpen('anchored-hint')).toBe(false);
  });

  it('delays hover only: keyboard focus on the anchor opens at once', () => {
    fire(link(), new FocusEvent('focus'));
    expect(isOpen('anchored-hint')).toBe(true);
  });

  it('delays a glyph trigger hover too, but a click pins it at once', () => {
    const host = el().querySelector('sb-hint.glyph-hint')!;
    fire(host, new MouseEvent('mouseenter'));
    expect(isOpen('glyph-hint')).toBe(false);
    fire(trigger(), new MouseEvent('click', { bubbles: true }));
    expect(isOpen('glyph-hint')).toBe(true);
  });

  it('dismiss() closes a hint held by focus and hover, and cancels a pending hover', () => {
    fire(link(), new FocusEvent('focus'));
    fire(link(), new MouseEvent('mouseenter'));
    tick(HINT_HOVER_DELAY_MS);
    instance('anchored-hint').dismiss();
    fixture.detectChanges();
    expect(isOpen('anchored-hint')).toBe(false);

    fire(link(), new MouseEvent('mouseleave'));
    fire(link(), new FocusEvent('blur'));
    fire(link(), new MouseEvent('mouseenter'));
    instance('anchored-hint').dismiss();
    tick(HINT_HOVER_DELAY_MS * 2);
    expect(isOpen('anchored-hint')).toBe(false);
  });

  it('has no protected close() left: dismiss() is the one way to close', () => {
    expect(SOURCE).not.toMatch(/\bclose\(\): void/);
    expect(SOURCE).not.toMatch(/this\.close\(\)|'close\(\)'/);
    expect(SOURCE).toMatch(/^ {2}dismiss\(\): void \{/m);
  });
});

describe('Hint: one open at a time, app-wide (v247 Decision 7)', () => {
  let fixture: ComponentFixture<PairHost>;

  beforeEach(async () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(PairHost);
    fixture.detectChanges();
    await fixture.whenStable();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const popOf = (anchor: Element) =>
    el().querySelector(`[id="${anchor.getAttribute('aria-describedby')}"]`) as HTMLElement;
  const linkA = () => el().querySelector('a.link-a') as HTMLAnchorElement;
  const linkB = () => el().querySelector('a.link-b') as HTMLAnchorElement;
  const glyphPop = () => el().querySelector('sb-hint.glyph-hint [role=tooltip]') as HTMLElement;
  const trigger = () => el().querySelector('sb-hint.glyph-hint button.trigger') as HTMLButtonElement;
  const open = (pop: HTMLElement) => pop.hasAttribute(POPOVER_OPEN_ATTR);
  const fire = async (target: Element, event: Event) => {
    target.dispatchEvent(event);
    fixture.detectChanges();
    await fixture.whenStable();
  };

  it('closes the open label when another label opens', async () => {
    await fire(linkA(), new MouseEvent('mouseenter'));
    expect(open(popOf(linkA()))).toBe(true);
    await fire(linkB(), new FocusEvent('focus'));
    expect(open(popOf(linkB()))).toBe(true);
    expect(open(popOf(linkA()))).toBe(false);
  });

  it('closes an open label when a glyph hint is pinned, and the other way round', async () => {
    await fire(linkA(), new FocusEvent('focus'));
    await fire(trigger(), new MouseEvent('click', { bubbles: true }));
    expect(open(glyphPop())).toBe(true);
    expect(open(popOf(linkA()))).toBe(false);
    await fire(linkB(), new MouseEvent('mouseenter'));
    expect(open(popOf(linkB()))).toBe(true);
    expect(open(glyphPop())).toBe(false);
  });

  it('does not reopen the displaced hint when the newer one closes', async () => {
    await fire(linkA(), new MouseEvent('mouseenter'));
    await fire(linkB(), new MouseEvent('mouseenter'));
    await fire(linkB(), new MouseEvent('mouseleave'));
    expect(open(popOf(linkA()))).toBe(false);
    expect(open(popOf(linkB()))).toBe(false);
  });

  it('frees the slot when an open hint is destroyed', async () => {
    await fire(linkA(), new MouseEvent('mouseenter'));
    fixture.destroy();
    const next = TestBed.createComponent(PairHost);
    next.detectChanges();
    await next.whenStable();
    const link = (next.nativeElement as HTMLElement).querySelector('a.link-b') as HTMLAnchorElement;
    link.dispatchEvent(new MouseEvent('mouseenter'));
    next.detectChanges();
    await next.whenStable();
    const pop = (next.nativeElement as HTMLElement)
      .querySelector(`[id="${link.getAttribute('aria-describedby')}"]`) as HTMLElement;
    expect(open(pop)).toBe(true);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/hint.spec.ts`
Expected: FAIL — the build errors on `HINT_HOVER_DELAY_MS` (not exported) and `openDelay` (unknown input); once those exist, the one-at-a-time tests fail (both labels stay open).

- [ ] **Step 3: Implement** in `frontend/src/app/ui/hint.ts`.

3a. Add `DestroyRef` to the `@angular/core` import list (after `Component`).

3b. Directly after `let nextId = 0;`:

```ts
/** The hover delay the rail and the tab bar pass to `openDelay` (v247
 *  Decision 6): a pointer sweeping across the rail does not flash every
 *  label on its way, and a resting pointer still gets an answer quickly.
 *  The spec cited "the existing hint delay"; there was none, so this is it. */
export const HINT_HOVER_DELAY_MS = 300;

/** The one hint open app-wide (v240 §5 "only one tooltip shows at a time",
 *  v247 Decision 7). Claimed by the open effect, released by its cleanup;
 *  a module variable because hints share no parent to hold it. */
let openHint: Hint | null = null;
```

3c. Append this paragraph to the class doc comment, before its closing `*/`:

```ts
 *
 * v247: `openDelay` holds the hover reason back by that many ms (focus,
 * click and openPinned() stay immediate; 0 keeps the old instant hover).
 * Only one hint is open app-wide: whichever opens dismisses the one that
 * was open. `dismiss()` is public, so that rule -- and a host holding a
 * template ref -- can close a hint whatever holds it open.
```

3d. Replace the hover, focus and escape lines of the `host` block:

```ts
    '(mouseenter)': 'onHoverStart()',
    '(mouseleave)': 'onHoverEnd()',
    '(focusin)': 'focused.set(true)',
    '(focusout)': 'onFocusOut($event)',
    '(keydown.escape)': 'dismiss()',
```

3e. After the `anchor` input, add:

```ts
  /** Hover-only open delay in ms (v247 Decision 6). Focus, click and
   *  openPinned() stay immediate. 0 (default) opens on hover at once, as
   *  every hint did before; the rail and tab bar pass HINT_HOVER_DELAY_MS. */
  readonly openDelay = input(0);
```

3f. After `private shown = false;`, add:

```ts
  /** The pending hover open, while a delay is running. */
  private hoverTimer: ReturnType<typeof setTimeout> | null = null;
```

3g. Make this the constructor's first line:

```ts
    inject(DestroyRef).onDestroy(() => this.clearHoverTimer());
```

In the open effect, call `this.claimOpenSlot();` right after `if (!this.open()) return;`, and `this.releaseOpenSlot();` inside `onCleanup`, just before `this.hide(pop);`.

3h. Replace `toggle()` and `close()` (lines 322-331) with:

```ts
  protected toggle(): void {
    if (this.pinned()) this.dismiss();
    else this.pinned.set(true);
  }

  /** Closes the hint whatever holds it open -- pin, hover (current or
   *  pending) and focus. Public since v247 (replaces the protected close()):
   *  the open-slot rule calls it on the hint it displaces. */
  dismiss(): void {
    this.clearHoverTimer();
    this.pinned.set(false);
    this.hovered.set(false);
    this.focused.set(false);
  }

  /** Hover start, glyph host or anchor alike: at once, or after openDelay. */
  protected onHoverStart(): void {
    this.clearHoverTimer();
    const delay = this.openDelay();
    if (delay <= 0) {
      this.hovered.set(true);
      return;
    }
    this.hoverTimer = setTimeout(() => {
      this.hoverTimer = null;
      this.hovered.set(true);
    }, delay);
  }

  /** Hover end: a pending open is cancelled, a current one ends. */
  protected onHoverEnd(): void {
    this.clearHoverTimer();
    this.hovered.set(false);
  }

  private clearHoverTimer(): void {
    if (this.hoverTimer === null) return;
    clearTimeout(this.hoverTimer);
    this.hoverTimer = null;
  }

  /** This hint is opening: the one that was open closes (v247 Decision 7). */
  private claimOpenSlot(): void {
    if (openHint && openHint !== this) openHint.dismiss();
    openHint = this;
  }

  /** From the open effect's cleanup: closing, or destroyed while open. */
  private releaseOpenSlot(): void {
    if (openHint === this) openHint = null;
  }
```

3i. `onDocumentPointer`: `if (!this.host.contains(event.target as Node)) this.dismiss();`

3j. `watchHostDialog`: `const onClosing = (): void => this.dismiss();`. In its doc comment, change "`close` covers a host shut" to "the dialog's `close` event covers a host shut".

3k. `bindAnchor`: `onKey` calls `this.dismiss()`; the listener table becomes

```ts
    const listeners: [string, EventListener][] = [
      ['mouseenter', () => this.onHoverStart()],
      ['mouseleave', () => this.onHoverEnd()],
      ['pointerdown', () => { pressed = true; this.dismiss(); }],
      ['focus', () => { if (!pressed) this.focused.set(true); pressed = false; }],
      ['blur', () => { pressed = false; this.focused.set(false); }],
      ['keydown', onKey],
    ];
```

and the remover's last line becomes `this.dismiss();`.

Check nothing still calls the old method: `git grep -n -e "this\.close()" -e "'close()'" -- frontend/src/app/ui/hint.ts` prints nothing. `close` was `protected`, so no other file could call it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/hint.spec.ts --include src/app/shell/shell.spec.ts`
Expected: PASS. `shell.spec.ts` holds the brand, version and theme-toggle hints. If one of its tests opens two hints and expects both open, it now contradicts Decision 7: report it to the controller rather than weakening the rule.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/hint.ts frontend/src/app/ui/hint.spec.ts
git commit -m "feat(v247): Hint hover delay, public dismiss(), one open hint app-wide"
```

### Task V247-6: `Hint`: `openPinned()` and anchor `placement: 'beside' | 'above'`

**Model:** sonnet — public API on the shared tooltip plus pure geometry; the long-press flow (press, open, the focus the press causes) must not close what it opened.

**Files:**
- Modify: `frontend/src/app/ui/hint.ts` (after `placeBeside` at ~86; class doc comment; `host` block; inputs after `openDelay`; `reposition` ~274-287; methods after `dismiss()`)
- Test: `frontend/src/app/ui/hint.spec.ts` (imports at lines 3 and 7; one host component after `PairHost`; two `describe` blocks appended at the end)

**Interfaces:**
- Consumes (V247-5): `Hint.dismiss()`, `Hint.openDelay`, the one-open-hint slot (`claimOpenSlot` in the open effect).
- Produces (consumed by V247-9 and V247-13):
  - `Hint.openPinned(): void` — public; opens and pins at once, cancelling a pending hover. It closes on the next `pointerdown` anywhere or on Escape pressed anywhere; hover and focus ending do not close it (index Global Constraints: "Long-press tooltip stays until the next pointerdown anywhere or Escape; no timed close").
  - `Hint.placement = input<'beside' | 'above'>('beside')` — anchor mode only; `'above'` centres the label over its anchor, two gaps off it.
  - `export function placeAbove(anchor: { top: number; bottom: number; left: number; right: number; width: number }, pop: { width: number; height: number }, viewport: { width: number; height: number }, margin = 8): { top: number; left: number }`

A pinned hint now also closes on Escape pressed anywhere in the document (`(document:keydown.escape)`, pinned only). Before, Escape reached a pinned glyph hint only with focus inside it; a touch user who long-pressed a tab has no focus there to press Escape from. Hover-open and focus-open hints keep the old rule.

- [ ] **Step 1: Write the failing tests** in `frontend/src/app/ui/hint.spec.ts`.

Line 3 becomes:

```ts
import { Component, provideZonelessChangeDetection, signal, viewChild } from '@angular/core';
```

Line 7 becomes:

```ts
import { DIALOG_CLOSING_EVENT, HINT_HOVER_DELAY_MS, Hint, clampPopover, placeAbove, placeBeside, supportsPopover } from './hint';
```

Insert directly after `class PairHost {}`:

```ts
/** v247: a tab-bar tab with its name above it, and a rail label beside its link. */
@Component({
  imports: [Hint],
  template: `
    <a #tab href="/trades" class="tab" aria-label="Trades">T</a>
    <sb-hint #tip [anchor]="tab" text="Trades" placement="above" />
    <a #rail href="/dashboard" class="rail-link" aria-label="Dashboard">D</a>
    <sb-hint #railTip [anchor]="rail" text="Dashboard" />
    <span class="outside">Elsewhere</span>
  `,
})
class PinHost {
  readonly tip = viewChild.required<Hint>('tip');
  readonly railTip = viewChild.required<Hint>('railTip');
}
```

Append at the end of the file:

```ts
describe('Hint.openPinned() and placement (v247)', () => {
  let fixture: ComponentFixture<PinHost>;
  const root = document.documentElement;

  beforeEach(async () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(PinHost);
    fixture.detectChanges();
    await fixture.whenStable();
  });

  afterEach(() => {
    // Undo the viewport stub: the own properties shadow Element.prototype's getters.
    delete (root as unknown as Record<string, unknown>)['clientWidth'];
    delete (root as unknown as Record<string, unknown>)['clientHeight'];
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const tab = () => el().querySelector('a.tab') as HTMLAnchorElement;
  const rail = () => el().querySelector('a.rail-link') as HTMLAnchorElement;
  const popOf = (anchor: Element) =>
    el().querySelector(`[id="${anchor.getAttribute('aria-describedby')}"]`) as HTMLElement;
  const open = (anchor: Element) => popOf(anchor).hasAttribute(POPOVER_OPEN_ATTR);
  const settle = async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  };
  const fire = async (target: Element, event: Event) => {
    target.dispatchEvent(event);
    await settle();
  };
  const pin = async () => {
    fixture.componentInstance.tip().openPinned();
    await settle();
  };
  /** jsdom has no layout: give the anchor a rect, the popover a size and the page a viewport. */
  const stubGeometry = (
    anchor: HTMLElement,
    rect: { top: number; bottom: number; left: number; right: number; width: number },
    size: { width: number; height: number },
    viewport: { width: number; height: number },
  ) => {
    anchor.getBoundingClientRect = () =>
      ({ ...rect, x: rect.left, y: rect.top, height: rect.bottom - rect.top, toJSON: () => ({}) }) as DOMRect;
    const pop = popOf(anchor);
    Object.defineProperty(pop, 'offsetWidth', { configurable: true, value: size.width });
    Object.defineProperty(pop, 'offsetHeight', { configurable: true, value: size.height });
    Object.defineProperty(root, 'clientWidth', { configurable: true, value: viewport.width });
    Object.defineProperty(root, 'clientHeight', { configurable: true, value: viewport.height });
  };

  it('opens the label at once, with no hover and no focus', async () => {
    expect(open(tab())).toBe(false);
    await pin();
    expect(open(tab())).toBe(true);
  });

  it('stays open after the hover and the focus that came with the press end', async () => {
    await fire(tab(), new MouseEvent('mouseenter'));
    await fire(tab(), new FocusEvent('focus'));
    await pin();
    await fire(tab(), new MouseEvent('mouseleave'));
    await fire(tab(), new FocusEvent('blur'));
    expect(open(tab())).toBe(true);
  });

  it('survives the long-press order: press, then openPinned(), then the focus the press causes', async () => {
    await fire(tab(), new Event('pointerdown', { bubbles: true }));
    await pin();
    await fire(tab(), new FocusEvent('focus'));
    expect(open(tab())).toBe(true);
  });

  it('closes on the next pointerdown anywhere, the anchor included', async () => {
    await pin();
    await fire(el().querySelector('.outside')!, new MouseEvent('pointerdown', { bubbles: true }));
    expect(open(tab())).toBe(false);
    await pin();
    await fire(tab(), new Event('pointerdown', { bubbles: true }));
    expect(open(tab())).toBe(false);
  });

  it('closes on Escape pressed anywhere in the document, with no focus on it', async () => {
    await pin();
    await fire(document.body, new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(open(tab())).toBe(false);
  });

  it('dismisses the other open hint (one at a time)', async () => {
    await fire(rail(), new FocusEvent('focus'));
    expect(open(rail())).toBe(true);
    await pin();
    expect(open(tab())).toBe(true);
    expect(open(rail())).toBe(false);
  });

  it('places an above label centred over its anchor, 8px off it', async () => {
    stubGeometry(tab(), { top: 788, bottom: 844, left: 78, right: 156, width: 78 },
      { width: 70, height: 24 }, { width: 390, height: 844 });
    await pin();
    expect(popOf(tab()).style.top).toBe('756px');
    expect(popOf(tab()).style.left).toBe('82px');
  });

  it('keeps the default placement beside its anchor', async () => {
    stubGeometry(rail(), { top: 100, bottom: 144, left: 10, right: 54, width: 44 },
      { width: 80, height: 24 }, { width: 1440, height: 900 });
    fixture.componentInstance.railTip().openPinned();
    await settle();
    expect(popOf(rail()).style.top).toBe('110px');
    expect(popOf(rail()).style.left).toBe('62px');
  });
});

describe('placeAbove (v247)', () => {
  const tab = { top: 788, bottom: 844, left: 78, right: 156, width: 78 };
  const label = { width: 70, height: 24 };
  const phone = { width: 390, height: 844 };

  it('sits above the anchor, 8px off it, horizontally centred on it', () => {
    expect(placeAbove(tab, label, phone)).toEqual({ top: 756, left: 82 });
  });

  it('stays 8px inside the left edge for the first tab', () => {
    expect(placeAbove({ ...tab, left: 0, right: 78 }, { width: 100, height: 24 }, phone).left).toBe(8);
  });

  it('stays 8px inside the right edge for the last tab', () => {
    expect(placeAbove({ ...tab, left: 312, right: 390 }, { width: 100, height: 24 }, phone).left).toBe(282);
  });

  it('stays 8px inside the top edge for an anchor at the top of the screen', () => {
    expect(placeAbove({ ...tab, top: 10, bottom: 50 }, label, phone).top).toBe(8);
  });

  it('takes the margin as a parameter', () => {
    expect(placeAbove({ ...tab, left: 0, right: 78 }, { width: 100, height: 24 }, phone, 16).left).toBe(16);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/hint.spec.ts`
Expected: FAIL — the build errors on `placeAbove` (not exported), `openPinned` (no such method) and `placement` (unknown input).

- [ ] **Step 3: Implement** in `frontend/src/app/ui/hint.ts`.

3a. Directly after `placeBeside`:

```ts
/**
 * Where an above-placed anchor label goes (v247, the phone tab bar's
 * press-and-hold, spec v240 §6): over its anchor, two gaps off it,
 * horizontally centred on it, and kept `margin` px inside the viewport --
 * shifted right off the left edge, left off the right, down off the top.
 * A tab sits at the foot of the screen, so beside would run off it. Pure,
 * like placeBeside.
 */
export function placeAbove(
  anchor: { top: number; bottom: number; left: number; right: number; width: number },
  pop: { width: number; height: number },
  viewport: { width: number; height: number },
  margin = 8,
): { top: number; left: number } {
  const centre = anchor.left + anchor.width / 2;
  return {
    top: clamp(anchor.top - 2 * POP_GAP - pop.height, margin, viewport.height - margin - pop.height),
    left: clamp(centre - pop.width / 2, margin, viewport.width - margin - pop.width),
  };
}
```

3b. Extend the class doc comment's v247 paragraph (added by V247-5) with:

```ts
 * `openPinned()` opens and pins it for a gesture the hint cannot see
 * (sbLongPress on the anchor); a pinned hint closes on the next pointerdown
 * anywhere or on Escape pressed anywhere. `placement="above"` puts an
 * anchor label over its anchor (placeAbove) instead of beside it.
```

3c. Add to the `host` block, after `'(document:pointerdown)': 'onDocumentPointer($event)',`:

```ts
    '(document:keydown.escape)': 'onDocumentEscape()',
```

3d. After the `openDelay` input:

```ts
  /** Anchor mode only (v247): 'beside' (default) labels to the right of the
   *  anchor -- the rail; 'above' centres the label over it -- the phone tab
   *  bar, whose tabs sit at the foot of the screen. */
  readonly placement = input<'beside' | 'above'>('beside');
```

3e. In `reposition`, replace the `const place = ...` line and its comment with:

```ts
    // Anchor mode labels beside (or above) its anchor; the glyph trigger opens below.
    const place = anchor ? this.placeLabel(rect, size, viewport) : clampPopover(rect, size, viewport, this.align());
```

and add this private method after `reposition`:

```ts
  private placeLabel(
    rect: DOMRect,
    size: { width: number; height: number },
    viewport: { width: number; height: number },
  ): { top: number; left: number } {
    return this.placement() === 'above' ? placeAbove(rect, size, viewport) : placeBeside(rect, size, viewport);
  }
```

`reposition` is an arrow-function field declared before the methods; it calls `this.placeLabel` only when run, so declaration order does not matter.

3f. After `dismiss()`:

```ts
  /** Opens and pins the hint at once (v247): for a gesture the hint cannot
   *  see -- sbLongPress on its anchor, wired by the host template as
   *  `(longPress)="hint.openPinned()"`. Pinned, it outlives hover and focus
   *  ending, and closes on the next pointerdown anywhere (onDocumentPointer,
   *  the anchor's own pointerdown) or on Escape anywhere (onDocumentEscape).
   *  No timed close: a slow reader is not rushed (spec v240 §6). */
  openPinned(): void {
    this.clearHoverTimer();
    this.pinned.set(true);
  }

  /** Escape anywhere closes a pinned hint: a touch user who long-pressed a
   *  tab has no focus inside it to press Escape from. Hover and focus opens
   *  keep their own Escape paths (the host and the anchor). */
  protected onDocumentEscape(): void {
    if (this.pinned()) this.dismiss();
  }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/hint.spec.ts --include src/app/ui/layout.spec.ts`
Expected: PASS. `layout.spec.ts` holds the drawer tests with hints inside a `<dialog>`, whose Escape now also reaches every pinned hint.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/hint.ts frontend/src/app/ui/hint.spec.ts
git commit -m "feat(v247): Hint openPinned() and above placement for anchor labels"
```

### Task V247-7: `sbLongPress` directive

**Model:** sonnet — a new shared gesture directive with timers, pointer bookkeeping and event-phase ordering (the click swallow must run before `RouterLink`); no cross-package judgement.

**Files:**
- Create: `frontend/src/app/ui/long-press.ts`
- Create: `frontend/src/app/ui/long-press.spec.ts`
- Modify: `frontend/src/styles.css` (append one rule after the `.sb-hit::after` rule, ~line 291)

**Interfaces:**
- Consumes: nothing from V247-5/6. The directive knows nothing of `sb-hint` (spec v240 §6: "emits on its own (no hint coupling), so it is testable alone").
- Produces (consumed by V247-9 on the rail links and V247-13 on the phone tabs):
  - `export const LONG_PRESS_MS = 500`
  - `export const LONG_PRESS_SLOP_PX = 10`
  - `@Directive({ selector: '[sbLongPress]' }) export class LongPress { readonly longPress = output<void>() }`. Hosts wire it as `<a ... sbLongPress (longPress)="hint.openPinned()">`.
  - Host class `sb-long-press` (set by the directive). Its global rule in `styles.css` turns off the iOS/Android link preview callout and text selection.

Behaviour (index Global Constraints, "Long-press"):

- A press counts only for pointer type `touch` or `pen`. A mouse never fires one: hover covers mouse (spec §9).
- `longPress` fires once, `LONG_PRESS_MS` after the `pointerdown`, and not before.
- Each of these cancels a pending press: a `pointermove` of the same pointer more than `LONG_PRESS_SLOP_PX` (Euclidean) from the start, where exactly 10px still fires; a second pointer going down anywhere in the document; `pointerup` before 500ms; `pointercancel` (the browser took the touch for a scroll); the directive being destroyed.
- The `click` after a fired press is swallowed: `preventDefault()` + `stopImmediatePropagation()` in a **capture** listener on the host. At the target, capture listeners run before bubble listeners (DOM spec; jsdom 28 too), so `RouterLink`'s own click handler and a template `(click)` never see it, and the press navigates nowhere. The swallow flag clears on that click or on the next `pointerdown`, whichever comes first. A browser that sends no click after a hold therefore never eats a later real tap.
- `contextmenu` is prevented only when the last `pointerdown` on the host was `touch`/`pen`. A mouse right-click and the keyboard menu key (no pointerdown before it) keep the native menu.
- No `preventDefault()` on `pointerdown`: that would kill scrolling the rail or tab bar and the focus the anchor gets.

- [ ] **Step 1: Write the failing tests.** Create `frontend/src/app/ui/long-press.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, RouterLink, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LONG_PRESS_MS, LONG_PRESS_SLOP_PX, LongPress } from './long-press';

/** A press host: an anchor with no href, so jsdom never tries to navigate. */
@Component({
  imports: [LongPress],
  template: `
    <a class="target" tabindex="0" sbLongPress (longPress)="presses = presses + 1" (click)="clicks = clicks + 1">
      <span class="icon">i</span>
    </a>
    <span class="outside">Elsewhere</span>
  `,
})
class Host {
  presses = 0;
  clicks = 0;
}

/** The real consumer shape: a routed nav link (rail link, phone tab). */
@Component({
  imports: [LongPress, RouterLink],
  template: `<a routerLink="/trades" class="tab" sbLongPress (longPress)="presses = presses + 1">Trades</a>`,
})
class RouterHost {
  presses = 0;
}

/** jsdom has no PointerEvent: a MouseEvent carrying pointerType and pointerId
 *  is what the directive reads (line-chart.spec.ts does the same). */
function pointer(
  type: string,
  init: { pointerType?: string; pointerId?: number; x?: number; y?: number } = {},
): MouseEvent {
  const event = new MouseEvent(type, {
    bubbles: true,
    cancelable: true,
    clientX: init.x ?? 100,
    clientY: init.y ?? 100,
  });
  Object.defineProperty(event, 'pointerType', { value: init.pointerType ?? 'touch' });
  Object.defineProperty(event, 'pointerId', { value: init.pointerId ?? 1 });
  return event;
}

const click = () => new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
const contextMenu = () => new MouseEvent('contextmenu', { bubbles: true, cancelable: true });

describe('LongPress (v247)', () => {
  let fixture: ComponentFixture<Host>;

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const target = () => el().querySelector('a.target') as HTMLAnchorElement;
  const presses = () => fixture.componentInstance.presses;
  const clicks = () => fixture.componentInstance.clicks;
  const down = (init: Parameters<typeof pointer>[1] = {}) => target().dispatchEvent(pointer('pointerdown', init));
  /** A held press that fires, then the finger lifting. */
  const hold = () => {
    down();
    vi.advanceTimersByTime(LONG_PRESS_MS);
    target().dispatchEvent(pointer('pointerup'));
  };

  it('pins the gesture constants', () => {
    expect(LONG_PRESS_MS).toBe(500);
    expect(LONG_PRESS_SLOP_PX).toBe(10);
  });

  it('gives its host the sb-long-press class', () => {
    expect(target().classList.contains('sb-long-press')).toBe(true);
  });

  it('fires once at 500ms of a held touch, not before', () => {
    down();
    vi.advanceTimersByTime(LONG_PRESS_MS - 1);
    expect(presses()).toBe(0);
    vi.advanceTimersByTime(1);
    expect(presses()).toBe(1);
    vi.advanceTimersByTime(5 * LONG_PRESS_MS);
    expect(presses()).toBe(1);
  });

  it('fires for a pen', () => {
    down({ pointerType: 'pen' });
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(1);
  });

  it('ignores a mouse held down: hover covers mouse', () => {
    down({ pointerType: 'mouse' });
    vi.advanceTimersByTime(2 * LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('is cancelled by lifting the finger before 500ms', () => {
    down();
    vi.advanceTimersByTime(300);
    target().dispatchEvent(pointer('pointerup'));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('is cancelled by pointercancel (the browser took the touch for a scroll)', () => {
    down();
    target().dispatchEvent(pointer('pointercancel'));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('survives a move of exactly 10px', () => {
    down({ x: 100, y: 100 });
    target().dispatchEvent(pointer('pointermove', { x: 106, y: 108 }));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(1);
  });

  it('is cancelled by a move over 10px', () => {
    down({ x: 100, y: 100 });
    target().dispatchEvent(pointer('pointermove', { x: 100, y: 111 }));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('ignores the move of another pointer', () => {
    down({ pointerId: 1, x: 100, y: 100 });
    target().dispatchEvent(pointer('pointermove', { pointerId: 7, x: 300, y: 300 }));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(1);
  });

  it('is cancelled by a second finger on the host', () => {
    down({ pointerId: 1 });
    down({ pointerId: 2 });
    vi.advanceTimersByTime(2 * LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('is cancelled by a second finger anywhere in the document', () => {
    down({ pointerId: 1 });
    el().querySelector('.outside')!.dispatchEvent(pointer('pointerdown', { pointerId: 2 }));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('swallows the click that follows a fired press, and only that one', () => {
    hold();
    const first = click();
    target().dispatchEvent(first);
    expect(first.defaultPrevented).toBe(true);
    expect(clicks()).toBe(0);
    target().dispatchEvent(click());
    expect(clicks()).toBe(1);
  });

  it('swallows the click when it lands on a child of the host (the icon)', () => {
    hold();
    el().querySelector('.icon')!.dispatchEvent(click());
    expect(clicks()).toBe(0);
  });

  it('lets a short tap click through', () => {
    down();
    vi.advanceTimersByTime(120);
    target().dispatchEvent(pointer('pointerup'));
    const tap = click();
    target().dispatchEvent(tap);
    expect(tap.defaultPrevented).toBe(false);
    expect(clicks()).toBe(1);
  });

  it('never eats a later tap when the browser sent no click after the hold', () => {
    hold();
    down();
    target().dispatchEvent(pointer('pointerup'));
    target().dispatchEvent(click());
    expect(clicks()).toBe(1);
  });

  it('prevents the context menu of a touch press', () => {
    down();
    const menu = contextMenu();
    target().dispatchEvent(menu);
    expect(menu.defaultPrevented).toBe(true);
  });

  it('keeps the context menu of a mouse right-click', () => {
    down({ pointerType: 'mouse' });
    const menu = contextMenu();
    target().dispatchEvent(menu);
    expect(menu.defaultPrevented).toBe(false);
  });

  it('keeps the context menu with no pointer before it (the keyboard menu key)', () => {
    const menu = contextMenu();
    target().dispatchEvent(menu);
    expect(menu.defaultPrevented).toBe(false);
  });

  it('does not fire after its host is destroyed', () => {
    down();
    fixture.destroy();
    expect(() => vi.advanceTimersByTime(LONG_PRESS_MS)).not.toThrow();
    expect(presses()).toBe(0);
  });
});

describe('LongPress on a routed link (v247)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const setup = () => {
    const fixture = TestBed.createComponent(RouterHost);
    fixture.detectChanges();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    const link = (fixture.nativeElement as HTMLElement).querySelector('a.tab') as HTMLAnchorElement;
    return { fixture, navigate, link };
  };

  it('a plain tap navigates (the control for the next test)', () => {
    const { navigate, link } = setup();
    link.dispatchEvent(click());
    expect(navigate).toHaveBeenCalledTimes(1);
  });

  it('a held press emits and navigates nowhere', () => {
    const { fixture, navigate, link } = setup();
    link.dispatchEvent(pointer('pointerdown'));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    link.dispatchEvent(pointer('pointerup'));
    link.dispatchEvent(click());
    expect(fixture.componentInstance.presses).toBe(1);
    expect(navigate).not.toHaveBeenCalled();
  });
});

describe('sb-long-press global rule (v247, spec v240 §6)', () => {
  // Source text: jsdom computes no -webkit-touch-callout (hit-area.spec.ts reads styles.css the same way).
  const GLOBAL = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');
  const rule = GLOBAL.match(/^\.sb-long-press\s*\{[^}]*\}/m)?.[0] ?? '';

  it('exists at the top level of styles.css', () => {
    expect(rule).not.toBe('');
  });

  it('turns off the link preview callout', () => {
    expect(rule).toContain('-webkit-touch-callout: none;');
  });

  it('turns off text selection, prefixed and unprefixed', () => {
    expect(rule).toContain('-webkit-user-select: none;');
    expect(rule).toMatch(/(^|\s)user-select: none;/m);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/long-press.spec.ts`
Expected: FAIL. The build cannot resolve `./long-press`.

- [ ] **Step 3: Implement the directive.** Create `frontend/src/app/ui/long-press.ts`:

```ts
import { DestroyRef, Directive, ElementRef, inject, output } from '@angular/core';

/** How long a touch is held before it counts as a press-and-hold (spec v240 §6). */
export const LONG_PRESS_MS = 500;
/** How far (px, Euclidean) the finger may drift before the hold is a scroll. */
export const LONG_PRESS_SLOP_PX = 10;

/** Pointer types a hold can come from. A mouse has hover instead (spec §9). */
const PRESS_POINTERS: ReadonlySet<string> = new Set(['touch', 'pen']);

/**
 * Press and hold (v247, spec v240 §5/§6): emits `longPress` when a touch or
 * pen is held on the host for LONG_PRESS_MS without drifting more than
 * LONG_PRESS_SLOP_PX. It emits and does nothing else: the host template wires
 * it, as on the rail and the phone tab bar,
 *
 *   <a ... sbLongPress (longPress)="hint.openPinned()">
 *
 * so the gesture is testable alone and sb-hint keeps owning tooltips.
 *
 * Cancelled by lifting early, pointercancel (the browser took the touch for a
 * scroll), a drift over the slop, a second pointer anywhere, or destroy. The
 * click after a fired press is swallowed in a CAPTURE listener on the host:
 * at the target, capture runs before bubble listeners, so RouterLink never
 * navigates. The swallow clears on that click or the next pointerdown, so a
 * browser that sends no click after a hold never eats a later tap.
 *
 * The OS must not fight it: the host gets class `sb-long-press`, whose global
 * rule (styles.css) turns off the link preview callout and text selection, and
 * a touch-originated contextmenu is prevented. A mouse right-click and the
 * keyboard menu key keep the native menu. pointerdown is never prevented: the
 * rail and the tab bar still scroll, and the anchor still takes focus.
 */
@Directive({
  selector: '[sbLongPress]',
  host: {
    class: 'sb-long-press',
    '(pointerdown)': 'onPointerDown($event)',
    '(pointermove)': 'onPointerMove($event)',
    '(pointerup)': 'cancel()',
    '(pointercancel)': 'cancel()',
    '(contextmenu)': 'onContextMenu($event)',
    '(document:pointerdown)': 'onDocumentPointerDown($event)',
  },
})
export class LongPress {
  readonly longPress = output<void>();

  private timer: ReturnType<typeof setTimeout> | null = null;
  private pointerId: number | null = null;
  private startX = 0;
  private startY = 0;
  private lastPointerType = '';
  private swallowClick = false;

  constructor() {
    const host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
    const onClick = (event: MouseEvent) => this.onClickCapture(event);
    host.addEventListener('click', onClick, true);
    inject(DestroyRef).onDestroy(() => {
      host.removeEventListener('click', onClick, true);
      this.cancel();
    });
  }

  /** The host's own pointerdown. A second pointer while one is held cancels
   *  the press, and does not start a new one. */
  protected onPointerDown(event: PointerEvent): void {
    this.lastPointerType = event.pointerType;
    this.swallowClick = false;
    if (this.timer !== null) {
      this.cancel();
      return;
    }
    if (!PRESS_POINTERS.has(event.pointerType)) return;
    this.pointerId = event.pointerId;
    this.startX = event.clientX;
    this.startY = event.clientY;
    this.timer = setTimeout(() => this.fire(), LONG_PRESS_MS);
  }

  /** A second finger that lands outside the host. The host's own pointerdown
   *  bubbles here after onPointerDown, with the held pointer's id: a no-op. */
  protected onDocumentPointerDown(event: PointerEvent): void {
    if (this.timer !== null && event.pointerId !== this.pointerId) this.cancel();
  }

  protected onPointerMove(event: PointerEvent): void {
    if (this.timer === null || event.pointerId !== this.pointerId) return;
    const drift = Math.hypot(event.clientX - this.startX, event.clientY - this.startY);
    if (drift > LONG_PRESS_SLOP_PX) this.cancel();
  }

  protected onContextMenu(event: MouseEvent): void {
    if (PRESS_POINTERS.has(this.lastPointerType)) event.preventDefault();
  }

  /** Drops a pending press. Never touches swallowClick: the pointerup after a
   *  fired press runs this too, and its click must still be swallowed. */
  protected cancel(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.pointerId = null;
  }

  private fire(): void {
    this.timer = null;
    this.pointerId = null;
    this.swallowClick = true;
    this.longPress.emit();
  }

  private onClickCapture(event: MouseEvent): void {
    if (!this.swallowClick) return;
    this.swallowClick = false;
    event.preventDefault();
    event.stopImmediatePropagation();
  }
}
```

- [ ] **Step 4: Add the global rule.** In `frontend/src/styles.css`, directly after the closing `}` of the `.sb-hit::after` rule (~line 291), insert:

```css

/* v247 (spec v240 §6) -- the host of every sbLongPress (ui/long-press.ts sets
 * the class). A held touch on a link otherwise opens the iOS/Android link
 * preview or starts a text selection, which fights the press-and-hold
 * tooltip. Global, because the class lands on links inside the shell's and
 * the tab bar's templates. */
.sb-long-press {
  -webkit-touch-callout: none;
  -webkit-user-select: none;
  user-select: none;
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/long-press.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/all-sources.spec.ts`
Expected: PASS. `hit-area.spec.ts` and `all-sources.spec.ts` read `styles.css` as source text, and they must stay green with the new rule in it.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/long-press.ts frontend/src/app/ui/long-press.spec.ts frontend/src/styles.css
git commit -m "feat(v247): sbLongPress directive -- touch/pen hold, click swallow, OS callout off"
```

