# v194 — UI integrity, part 1: `sb-hint` in the top layer, layout-audit `hint` check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V194-2:" -A 400 <this file>`.

**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md) — sections A1, A2
**Index:** [2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md](2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md) — Global Constraints, `### Standard task close`, Handoff, Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks V194-1, V194-1b, V194-2, V194-2b, V194-3. The ledger's V194-1 and
V194-2 each ran past the 400-line task ceiling once written in full, so each
is split in two here (`b` rows; the controller adds them to the ledger, and
no other part consumes anything that moved). V194-1 creates the worktree
`.claude/worktrees/2026-10-25-v194-ui-tooltips-and-data-truth`; every task
runs in it. `WT` below is that worktree's absolute path
(`E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v194-ui-tooltips-and-data-truth`).
V194-1 → V194-1b → V194-2 → V194-2b are sequential (all edit
`hint.spec.ts`, the last three `hint.ts`); V194-3 is file-disjoint
(`frontend/scripts/` only) and may run beside any later lane.

# Phase 1 — `sb-hint` opens above everything

### Task V194-1: Worktree; global popover polyfill for the unit-test DOM

**Model:** sonnet — a test-only polyfill on an existing pattern (`dialog-polyfill.ts`), behaviour fixed by spec A1's Test environment paragraph.

**Files:**
- Create: `frontend/src/app/testing/popover-polyfill.ts`
- Modify: `frontend/src/test-setup.ts:1` (import) and append after `:66`
- Modify: `frontend/src/app/ui/hint.spec.ts:7` (one import), new `describe` at the end
- Test: `frontend/src/app/ui/hint.spec.ts`

**Interfaces:**
- Consumes: nothing new; `installDialogPolyfill` (`frontend/src/app/testing/dialog-polyfill.ts`) is the pattern copied, not imported.
- Produces: worktree branch `2026-10-25-v194-ui-tooltips-and-data-truth`; `installPopoverPolyfill(): void` (idempotent; patches `HTMLElement.prototype.showPopover/hidePopover/togglePopover` when absent, reflects state as attribute `data-popover-open`, throws `InvalidStateError` on a double show or hide or a disconnected element, `NotSupportedError` without a `popover` attribute) and `POPOVER_OPEN_ATTR = 'data-popover-open'`, both from `frontend/src/app/testing/popover-polyfill.ts`; installed for every spec from `src/test-setup.ts`.

- [ ] **Step 1: Create the worktree and install the frontend**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch origin
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-25-v194-ui-tooltips-and-data-truth -b 2026-10-25-v194-ui-tooltips-and-data-truth main
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v194-ui-tooltips-and-data-truth
npm --prefix "$WT/frontend" ci
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/hint.spec.ts
```

Expected: `status --short` is empty before the add (stop and ask if not); the
hint spec is green on the untouched branch (8 tests). If `git worktree list`
already shows this worktree, reuse it and skip the `add`.

- [ ] **Step 2: Write the failing tests**

`frontend/src/app/ui/hint.spec.ts:7` — after `import { Hint } from './hint';`
insert:

```ts
import { POPOVER_OPEN_ATTR, installPopoverPolyfill } from '../testing/popover-polyfill';
```

Append at the end of the file (after the outer `describe`'s closing `});`):

```ts

describe('popover polyfill (test environment, v194 A1)', () => {
  const make = () => {
    const element = document.createElement('div');
    element.setAttribute('popover', 'manual');
    document.body.appendChild(element);
    return element;
  };
  const errorName = (fn: () => unknown): string => {
    try {
      fn();
    } catch (error) {
      return (error as DOMException).name;
    }
    return 'no error';
  };

  it('is installed for every spec from test-setup.ts', () => {
    expect(typeof HTMLElement.prototype.showPopover).toBe('function');
  });

  it('reflects the open state as data-popover-open', () => {
    const element = make();
    element.showPopover();
    expect(element.hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    element.hidePopover();
    expect(element.hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
    element.remove();
  });

  it('throws InvalidStateError on a double show, a double hide and a disconnected element', () => {
    const element = make();
    element.showPopover();
    expect(errorName(() => element.showPopover())).toBe('InvalidStateError');
    element.hidePopover();
    expect(errorName(() => element.hidePopover())).toBe('InvalidStateError');
    element.remove();
    expect(errorName(() => element.showPopover())).toBe('InvalidStateError');
  });

  it('throws NotSupportedError on an element without a popover attribute', () => {
    const element = document.createElement('div');
    document.body.appendChild(element);
    expect(errorName(() => element.showPopover())).toBe('NotSupportedError');
    element.remove();
  });

  it('togglePopover flips the state, honours force, and returns the new state', () => {
    const element = make();
    expect(element.togglePopover()).toBe(true);
    expect(element.togglePopover(true)).toBe(true);
    expect(element.hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    expect(element.togglePopover()).toBe(false);
    expect(element.hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
    element.remove();
  });

  it('is idempotent: a second install keeps the installed methods', () => {
    const before = HTMLElement.prototype.showPopover;
    installPopoverPolyfill();
    expect(HTMLElement.prototype.showPopover).toBe(before);
  });
});
```

The DOM lib types `togglePopover(options?: boolean | TogglePopoverOptions)`;
a boolean argument satisfies it, so `togglePopover(true)` compiles.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/hint.spec.ts`
Expected: FAIL — `../testing/popover-polyfill` cannot be resolved.

- [ ] **Step 4: Create the polyfill**

Write `frontend/src/app/testing/popover-polyfill.ts` (Write tool):

```ts
/**
 * Teaches jsdom the Popover API, which it does not implement (spec v194 A1).
 *
 * `sb-hint` shows its popover with `showPopover()` so the browser puts it in
 * the top layer, outside every ancestor's transform, overflow clip and
 * stacking context. jsdom 28 has neither the methods nor the `:popover-open`
 * state, and every `sb-panel` heading renders an `sb-hint`, so any page spec
 * that hovers a heading would throw "showPopover is not a function". That is
 * why this is installed once, globally, from `src/test-setup.ts` -- not per
 * spec the way `installDialogPolyfill()` is.
 *
 * What this stands in for is only the open/closed bookkeeping. jsdom cannot
 * match `:popover-open`, so the state is reflected as the attribute
 * `data-popover-open`, which specs read instead. The top layer, its geometry
 * and the UA display rule are not simulated and must not be asserted
 * against: the layout audit's `hint` check (spec A2) proves those in a real
 * browser.
 *
 * It is deliberately strict, the way engines are: showing an open popover,
 * hiding a closed one, or touching a disconnected one throws
 * `InvalidStateError`, and an element without a `popover` attribute throws
 * `NotSupportedError`. A component that forgets its guards fails its spec
 * here instead of in a user's console.
 *
 * Idempotent, and a no-op in any environment that has the real thing.
 */
export const POPOVER_OPEN_ATTR = 'data-popover-open';

interface PopoverMethods {
  showPopover(): void;
  hidePopover(): void;
  togglePopover(force?: boolean): boolean;
}

function checkPopover(element: HTMLElement): void {
  if (!element.hasAttribute('popover')) throw new DOMException('Not a popover element', 'NotSupportedError');
  if (!element.isConnected) throw new DOMException('Popover is not connected', 'InvalidStateError');
}

export function installPopoverPolyfill(): void {
  const proto = HTMLElement.prototype as unknown as Partial<PopoverMethods>;
  if (typeof proto.showPopover === 'function') return;

  proto.showPopover = function showPopover(this: HTMLElement): void {
    checkPopover(this);
    if (this.hasAttribute(POPOVER_OPEN_ATTR)) throw new DOMException('Popover is already open', 'InvalidStateError');
    this.setAttribute(POPOVER_OPEN_ATTR, '');
  };

  proto.hidePopover = function hidePopover(this: HTMLElement): void {
    checkPopover(this);
    if (!this.hasAttribute(POPOVER_OPEN_ATTR)) throw new DOMException('Popover is not open', 'InvalidStateError');
    this.removeAttribute(POPOVER_OPEN_ATTR);
  };

  proto.togglePopover = function togglePopover(this: HTMLElement, force?: boolean): boolean {
    const open = this.hasAttribute(POPOVER_OPEN_ATTR);
    const want = force ?? !open;
    const methods = this as unknown as PopoverMethods;
    if (want && !open) methods.showPopover();
    else if (!want && open) methods.hidePopover();
    return want;
  };
}
```

- [ ] **Step 5: Install it globally**

`frontend/src/test-setup.ts:1` — after the `resolve-token` import insert:

```ts
import { installPopoverPolyfill } from './app/testing/popover-polyfill';
```

Append after line 66:

```ts

/**
 * The Popover API, for every spec (spec v194 A1).
 *
 * sb-hint shows its popover through showPopover(), and every sb-panel heading
 * renders an sb-hint, so a page spec that hovers any heading needs the API.
 * Per-spec installation (the dialog polyfill's pattern) would leave that
 * failure waiting in whichever page spec first hovers a panel. Patching
 * HTMLElement.prototype from here is safe under `ng test` for the reason the
 * motion default above records: prototypes are shared, only module
 * singletons are not. See app/testing/popover-polyfill.ts for what it does
 * and does not simulate.
 */
installPopoverPolyfill();
```

`frontend/vitest.config.ts:34` (`setupFiles: ['./src/test-setup.ts']`) already
loads this file for every spec; nothing to change there.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/hint.spec.ts`
Expected: PASS (8 existing + 6 polyfill = 14). If "is installed for every
spec" fails, the spec ran without `src/test-setup.ts`; if "reflects the open
state" fails while the methods exist, the installed jsdom ships its own
Popover API and the polyfill stood down. Stop and report that case: V194-1b's
`isOpen()` depends on the attribute.

Close: standard (test: frontend/src/app/ui/hint.spec.ts); one frontend commit `test(v194): global Popover API polyfill for the unit-test DOM (V194-1)` naming `frontend/src/app/testing/popover-polyfill.ts`, `frontend/src/test-setup.ts`, `frontend/src/app/ui/hint.spec.ts`. Close step 1's main-tree check runs after Step 1 has created the worktree.

### Task V194-1b: `sb-hint` shows in the top layer, with feature detection and guarded calls

**Model:** sonnet — one component's open/close path moved onto a browser API, behaviour fixed by spec A1 and its robustness rules.

**Files:**
- Modify: `frontend/src/app/ui/hint.ts:1-10` (imports), `:12` (insert after), `:28-31` (docblock), `:54-63` (`.pop` span), `:94-101` (`.pop` comment and rule head), `:111` (insert after), `:150` (insert after), `:168-184` (constructor), `:206` (insert after)
- Modify: `frontend/src/app/ui/hint.spec.ts:5-7` (imports), `:40` (`isOpen`, as V194-1 left the file), new tests
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts:472` (one assertion, Step 6; outside the ledger's file list for this row, flagged to the controller)
- Test: `frontend/src/app/ui/hint.spec.ts`

**Interfaces:**
- Consumes: `installPopoverPolyfill`, `POPOVER_OPEN_ATTR` (V194-1).
- Produces: `supportsPopover(): boolean` (exported from `frontend/src/app/ui/hint.ts`); `.pop` carries `popover="manual"` when the API exists and the template ref `#pop`; its `[hidden]` binding is gone; open state is shown through `showPopover()` / `hidePopover()`; without the API, `.fallback-closed` hides it. V194-2 and V194-2b build on `Hint`'s new private `pop` view child, its constructor effect, and the `show` / `hide` helpers.

- [ ] **Step 1: Write the failing tests**

`hint.spec.ts:5-7` — old → new:

```ts
import { beforeEach, describe, expect, it } from 'vitest';

import { Hint } from './hint';
```

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Hint, supportsPopover } from './hint';
```

`hint.spec.ts:40` — old → new:

```ts
  const isOpen = () => !pop().hidden;
```

```ts
  // The polyfill reflects :popover-open as an attribute (jsdom cannot match the pseudo-class).
  const isOpen = () => pop().hasAttribute(POPOVER_OPEN_ATTR);
```

Inside `describe('Hint (v80 D4)', ...)`, after its last `it` (the 44px test,
ending line 101), insert:

```ts

  describe('top layer (v194 A1)', () => {
    afterEach(() => vi.restoreAllMocks());

    it('carries popover="manual" and no hidden attribute', () => {
      expect(supportsPopover()).toBe(true);
      expect(pop().getAttribute('popover')).toBe('manual');
      expect(pop().hasAttribute('hidden')).toBe(false);
    });

    it('opens and closes through showPopover() and hidePopover() on the popover element', () => {
      const show = vi.spyOn(HTMLElement.prototype, 'showPopover');
      const hide = vi.spyOn(HTMLElement.prototype, 'hidePopover');
      fire(hint(), new MouseEvent('mouseenter'));
      expect(show).toHaveBeenCalledTimes(1);
      expect(show.mock.contexts[0]).toBe(pop());
      expect(hide).not.toHaveBeenCalled();
      fire(hint(), new MouseEvent('mouseleave'));
      expect(hide).toHaveBeenCalledTimes(1);
      expect(hide.mock.contexts[0]).toBe(pop());
    });

    it('never shows twice or hides twice while open reasons overlap', () => {
      const show = vi.spyOn(HTMLElement.prototype, 'showPopover');
      const hide = vi.spyOn(HTMLElement.prototype, 'hidePopover');
      // A phone tap: emulated hover, then focus, then the pinning click.
      fire(hint(), new MouseEvent('mouseenter'));
      fire(trigger(), new FocusEvent('focusin', { bubbles: true }));
      fire(trigger(), new MouseEvent('click', { bubbles: true }));
      fire(hint(), new MouseEvent('mouseleave'));
      fire(trigger(), new FocusEvent('focusout', { bubbles: true, relatedTarget: null }));
      expect(isOpen()).toBe(true);
      expect(show).toHaveBeenCalledTimes(1);
      expect(hide).not.toHaveBeenCalled();
      fire(trigger(), new MouseEvent('click', { bubbles: true }));
      expect(isOpen()).toBe(false);
      expect(hide).toHaveBeenCalledTimes(1);
      // The strict polyfill throws on a double call, so reaching here also proves the guards.
    });

    it('tears down an open hint without throwing', () => {
      fire(trigger(), new MouseEvent('click', { bubbles: true }));
      expect(isOpen()).toBe(true);
      expect(() => fixture.destroy()).not.toThrow();
    });
  });
```

Before V194-1's `describe('popover polyfill ...')` at the end of the file,
insert:

```ts

describe('Hint without the Popover API (v194 A1 fallback)', () => {
  const NAMES = ['showPopover', 'hidePopover', 'togglePopover'] as const;
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  const saved: Record<string, unknown> = {};
  let fixture: ComponentFixture<Host>;

  beforeEach(() => {
    for (const name of NAMES) {
      saved[name] = proto[name];
      delete proto[name];
    }
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
  });

  afterEach(() => {
    for (const name of NAMES) proto[name] = saved[name];
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const hint = () => el().querySelector('sb-hint') as HTMLElement;
  const pop = () => el().querySelector('sb-hint [role=tooltip]') as HTMLElement;
  const fire = (target: Element, event: Event) => {
    target.dispatchEvent(event);
    fixture.detectChanges();
  };

  it('keeps the fixed-position path: no popover attribute, hidden by class until open', () => {
    expect(supportsPopover()).toBe(false);
    expect(pop().hasAttribute('popover')).toBe(false);
    expect(pop().classList).toContain('fallback-closed');
    fire(hint(), new MouseEvent('mouseenter'));
    expect(pop().classList).not.toContain('fallback-closed');
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
    fire(hint(), new MouseEvent('mouseleave'));
    expect(pop().classList).toContain('fallback-closed');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/hint.spec.ts`
Expected: FAIL — `supportsPopover` is not exported by `./hint` (compile
error). Past that, every `isOpen()`-true assertion would fail, because
nothing calls `showPopover` yet.

- [ ] **Step 3: Implement the native path in `hint.ts`**

`hint.ts:9` — after `  signal,` in the `@angular/core` import list insert
`  viewChild,`.

After line 12 (`let nextId = 0;`) insert:

```ts

/**
 * Whether this engine has the Popover API (spec v194 A1, feature detection).
 * Without it the hint keeps the old position: fixed path, so an old browser
 * loses only the cases an ancestor transform clips -- never every hint.
 */
export function supportsPopover(): boolean {
  return typeof HTMLElement !== 'undefined' && typeof HTMLElement.prototype.showPopover === 'function';
}
```

`hint.ts:30` — after the docblock's line
` * the text on focus without opening anything.` insert:

```ts
 *
 * Since v194 the popover is a native `popover="manual"` element shown with
 * `showPopover()`: the browser paints it in the top layer, outside every
 * ancestor's containing block, overflow clip and stacking context. An
 * `.sb-lift` card's hover transform (`motion.css`) made the old
 * `position: fixed` popover position against the card and clip with it,
 * which is how a hint on a tile or panel heading opened invisibly. `open`
 * stays the single source of truth; the effect below maps it onto the API,
 * guarded, because engines throw `InvalidStateError` on a double show or
 * hide.
```

`hint.ts:54-63` — the `.pop` span's opening tag, old → new (`[hidden]`
removed; the template ref, the fallback class and the popover attribute
added; the `@if` body after it is unchanged):

```ts
    <span
      class="pop elev-overlay"
      [class.wide]="wide()"
      [class.xl]="xl()"
      [class.align-left]="align() === 'left'"
      role="tooltip"
      [id]="id"
      [hidden]="!open()"
      [style.top.px]="popTop()"
      [style.left.px]="popLeft()"
```

```ts
    <span
      #pop
      class="pop elev-overlay"
      [class.wide]="wide()"
      [class.xl]="xl()"
      [class.align-left]="align() === 'left'"
      [class.fallback-closed]="!native && !open()"
      [attr.popover]="native ? 'manual' : null"
      role="tooltip"
      [id]="id"
      [style.top.px]="popTop()"
      [style.left.px]="popLeft()"
```

`hint.ts:94-101` — replace the comment above `.pop` (lines 94-98) and the
rule's first two declarations (lines 100-101) with the following; lines
102-111 of the rule are unchanged:

```css
    /* Native path (v194 A1): popover="manual" puts this box in the top
       layer, whose containing block is the viewport whatever the ancestors
       do, so popTop/popLeft -- measured from the trigger's viewport rect --
       are exact. The UA's [popover] rules (inset: 0, margin: auto,
       overflow: auto) are reset here; .elev-overlay's border and background
       are author styles and already win over the UA's. Fallback path (no
       Popover API): the same position: fixed box, which an ancestor
       transform can still clip -- the pre-v194 behaviour, hidden by
       .fallback-closed instead of the UA's popover display rule. */
    .pop {
      position: fixed;
      inset: auto;
      margin: 0;
      overflow: visible;
      z-index: 20;
```

After line 111 (the `.pop` rule's closing `}`) insert:

```css
    .pop.fallback-closed { display: none; }
```

After line 150 (the `open` computed) insert:

```ts

  /** Read once: an engine does not gain or lose the Popover API mid-session. */
  protected readonly native = supportsPopover();
  private readonly pop = viewChild.required<ElementRef<HTMLElement>>('pop');
  /** This instance showed its popover and has not hidden it yet. Tracked
   *  here rather than read back from :popover-open, so the guards hold the
   *  same way under the test polyfill (jsdom cannot match that selector). */
  private shown = false;
```

`hint.ts:168-184` (the constructor) becomes, in full — the comment is
rewritten, and `const pop`, `this.show(pop)` and `this.hide(pop)` are the
three new statements:

```ts
  constructor() {
    /** Open -> show the popover (top layer, or the fallback's fixed box),
     *  then place it from the trigger's viewport rect: once on open, and on
     *  every scroll/resize while open -- a panel body scrolls its content
     *  (layout.ts's .body { overflow-y: auto }) without moving the window,
     *  which a plain window-resize listener would miss. Closed -> the
     *  cleanup hides it. */
    effect((onCleanup) => {
      if (!this.open()) return;
      const pop = this.pop().nativeElement;
      this.show(pop);
      this.reposition();
      window.addEventListener('scroll', this.reposition, { capture: true, passive: true });
      window.addEventListener('resize', this.reposition, { passive: true });
      onCleanup(() => {
        window.removeEventListener('scroll', this.reposition, true);
        window.removeEventListener('resize', this.reposition);
        this.hide(pop);
      });
    });
  }
```

After `onDocumentPointer` (its closing `}` is line 206, before the class's
closing `}`) insert:

```ts

  /** Guarded (v194 A1): showPopover() throws InvalidStateError on a
   *  disconnected or already-open popover on some engines. */
  private show(pop: HTMLElement): void {
    if (!this.native || this.shown || !pop.isConnected) return;
    pop.showPopover();
    this.shown = true;
  }

  /** Guarded the same way. A popover removed from the document was already
   *  hidden by the browser, so only a connected one is hidden here. */
  private hide(pop: HTMLElement): void {
    if (!this.shown) return;
    this.shown = false;
    if (pop.isConnected) pop.hidePopover();
  }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/hint.spec.ts`
Expected: PASS (14 from V194-1 + 4 top-layer + 1 fallback = 19).
If an `isOpen()` assertion right after `fire(...)` reads false although the
handler ran, the component effect has not flushed yet: add
`await fixture.whenStable()` after `fixture.detectChanges()` in `fire` (and
make the affected tests `async`) rather than changing the component.

- [ ] **Step 5: Run the neighbour that renders a hint in every heading**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/layout.spec.ts`
Expected: PASS.

- [ ] **Step 6: Keep the Dashboard help assertion meaningful**

`frontend/src/app/workspaces/dashboard/dashboard.spec.ts:472` asserts the
tooltip's `.hidden` is false after a hover. With `[hidden]` gone that holds
at rest too, so the test would no longer prove the hint opened. Old → new:

```ts
    expect(el.querySelector<HTMLElement>('sb-hint.lifecycle-hint [role="tooltip"]')!.hidden).toBe(false);
```

```ts
    expect(el.querySelector<HTMLElement>('sb-hint.lifecycle-hint [role="tooltip"]')!.hasAttribute('data-popover-open')).toBe(true);
```

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: PASS. (The file is otherwise V194-4's and V194-13's; V194-1b runs
before both, so the one-line edit cannot collide.)

Close: standard (test: frontend/src/app/ui/hint.spec.ts); one frontend commit `feat(v194): sb-hint shows in the top layer through the Popover API, with a fixed-position fallback (V194-1b)` naming `frontend/src/app/ui/hint.ts`, `frontend/src/app/ui/hint.spec.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`. The whole-frontend run in Close step 2 is the check that no other `sb-hint` consumer depended on `[hidden]`.

### Task V194-2: `sb-hint` viewport clamp (flip above, shift sideways, 8px)

**Model:** sonnet — a pure geometry function with table tests, wired into one existing method.

**Files:**
- Modify: `frontend/src/app/ui/hint.ts` — the line numbers below are the **original** file's. V194-1b moved all of them down, so find each edit by its quoted old text: the `[class.align-left]` line in the `.pop` span (orig `:58`), the `transform` line of the `.pop` rule (orig `:105`), the `.align-left` comment and rule (orig `:116-120`), the `align` input's docblock (orig `:140-143`), `reposition` (orig `:156-166`), and the constructor's effect (V194-1b's version)
- Modify: `frontend/src/app/ui/hint.spec.ts` (the `./hint` import; a new `describe` at the end)
- Test: `frontend/src/app/ui/hint.spec.ts`

**Interfaces:**
- Consumes: V194-1b's `pop` view child, `supportsPopover`, constructor effect.
- Produces: `clampPopover(trigger: { top: number; bottom: number; left: number; right: number; width: number }, pop: { width: number; height: number }, viewport: { width: number; height: number }, align: 'center' | 'left', margin = 8): { top: number; left: number; above: boolean }`, exported from `frontend/src/app/ui/hint.ts`. `left` is the popover's own left edge, so no CSS transform remains.

**The rule.** The popover sits 4px below the trigger. When it would cross the
bottom margin it flips 4px above, if it fits there or if there is more room
above than below. Either way its top is clamped into
`[margin, viewport.height - margin - height]`, and the top margin wins when
the popover is taller than the viewport. Horizontally it centres under the
trigger (`'center'`) or ends at the trigger's right edge (`'left'`), then it
is clamped into `[margin, viewport.width - margin - width]`; the left margin
wins when it is wider than the viewport. The viewport is
`document.documentElement`'s client box, which is the top layer's containing
block.

- [ ] **Step 1: Write the failing tests**

`hint.spec.ts` — the `./hint` import, as V194-1b left it, old → new:

```ts
import { Hint, supportsPopover } from './hint';
```

```ts
import { Hint, clampPopover, supportsPopover } from './hint';
```

Append at the end of `hint.spec.ts`:

```ts

describe('clampPopover (v194 A1)', () => {
  const DESKTOP = { width: 1440, height: 900 };
  const PHONE = { width: 390, height: 844 };
  const POP = { width: 200, height: 50 };
  /** A 14px trigger whose top-left corner is at (left, top). */
  const trig = (left: number, top: number) => ({ top, bottom: top + 14, left, right: left + 14, width: 14 });

  it('sits 4px under the trigger, centred, when there is room', () => {
    expect(clampPopover(trig(200, 100), POP, DESKTOP, 'center')).toEqual({ top: 118, left: 107, above: false });
  });

  it("align 'left' ends the popover at the trigger's right edge", () => {
    expect(clampPopover(trig(400, 100), POP, DESKTOP, 'left')).toEqual({ top: 118, left: 214, above: false });
  });

  it('flips above the trigger when there is no room below', () => {
    expect(clampPopover(trig(200, 860), POP, DESKTOP, 'center')).toEqual({ top: 806, left: 107, above: true });
  });

  it('shifts left instead of running off the right edge, keeping 8px', () => {
    expect(clampPopover(trig(1420, 100), POP, DESKTOP, 'center').left).toBe(1440 - 8 - 200);
  });

  it('shifts right instead of running off the left edge, keeping 8px', () => {
    expect(clampPopover(trig(4, 100), POP, PHONE, 'center').left).toBe(8);
    expect(clampPopover(trig(20, 100), POP, PHONE, 'left').left).toBe(8);
  });

  it('pins a popover wider than the viewport to the left margin', () => {
    expect(clampPopover(trig(180, 100), { width: 500, height: 50 }, PHONE, 'center').left).toBe(8);
  });

  it('with no room either way, takes the larger side and keeps its top inside the margin', () => {
    const tall = { width: 200, height: 700 };
    const short = { width: 1440, height: 600 };
    // 300px above the trigger, 286px below it: above wins, then the top clamps to 8.
    expect(clampPopover(trig(200, 300), tall, short, 'center')).toEqual({ top: 8, left: 107, above: true });
    // 100px above, 486px below: stays below, clamped to 8 because it is taller than the viewport.
    expect(clampPopover(trig(200, 100), tall, short, 'center')).toEqual({ top: 8, left: 107, above: false });
  });

  it('takes the margin as a parameter', () => {
    expect(clampPopover(trig(1420, 100), POP, DESKTOP, 'center', 0).left).toBe(1240);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/hint.spec.ts`
Expected: FAIL — `clampPopover` is not exported by `./hint` (compile error).

- [ ] **Step 3: Add the clamp to `hint.ts`**

After V194-1b's `supportsPopover` function (just below `let nextId = 0;`)
insert:

```ts

/** Space between the trigger and the popover, either side. */
const POP_GAP = 4;

const clamp = (value: number, min: number, max: number): number => Math.max(min, Math.min(value, max));

/**
 * Where an open popover goes (spec v194 A1): 4px under its trigger, flipped
 * above when it would cross the bottom margin and there is room above (or
 * more room above than below), and shifted sideways rather than run off
 * either edge -- `margin` px from every viewport edge, the top and left
 * margins winning for a popover larger than the viewport. `left` is the
 * popover's own left edge. Pure: jsdom has no layout, so this is the part of
 * the geometry a unit test can prove; the layout audit's `hint` check proves
 * the rest in a browser.
 */
export function clampPopover(
  trigger: { top: number; bottom: number; left: number; right: number; width: number },
  pop: { width: number; height: number },
  viewport: { width: number; height: number },
  align: 'center' | 'left',
  margin = 8,
): { top: number; left: number; above: boolean } {
  const fitsBelow = trigger.bottom + POP_GAP + pop.height <= viewport.height - margin;
  const fitsAbove = trigger.top - POP_GAP - pop.height >= margin;
  const above = !fitsBelow && (fitsAbove || trigger.top > viewport.height - trigger.bottom);
  const rawTop = above ? trigger.top - POP_GAP - pop.height : trigger.bottom + POP_GAP;
  const rawLeft = align === 'left' ? trigger.right - pop.width : trigger.left + trigger.width / 2 - pop.width / 2;
  return {
    top: clamp(rawTop, margin, viewport.height - margin - pop.height),
    left: clamp(rawLeft, margin, viewport.width - margin - pop.width),
    above,
  };
}
```

- [ ] **Step 4: Position from the clamp and drop the transforms**

Template: delete the `.pop` span's line
`      [class.align-left]="align() === 'left'"` (no CSS reads the class any
more; nothing outside `hint.ts` uses it — `git grep -n "align-left" frontend/src`).

CSS: in the `.pop` rule delete the line `      transform: translateX(-50%);`.

CSS: the `.align-left` comment and rule, old → new:

```css
    /* Anchors the popover's RIGHT edge to the trigger instead of centring
       under it, so it opens leftward. "left" (popLeft, above) is set to
       the trigger's own right edge when this is active -- see the
       reposition() method below. */
    .pop.align-left { transform: translateX(-100%); }
```

```css
    /* No transform: popLeft is the popover's own left edge, already
       centred (or right-aligned for align="left") and clamped inside the
       viewport by clampPopover() -- see reposition() below. */
```

The `align` input's docblock, old → new:

```ts
  /** 'center' (default) sits the popover under the trigger's midpoint;
   *  'left' opens it leftward from the trigger's right edge instead, for a
   *  trigger sitting close enough to the panel's own right edge that a
   *  centred popover would run off it. */
```

```ts
  /** 'center' (default) sits the popover under the trigger's midpoint;
   *  'left' ends it at the trigger's right edge instead. Since v194 the
   *  viewport clamp keeps either inside the screen, so 'left' is no longer
   *  needed to stop a popover running off an edge; the input stays for the
   *  callers that set it. */
```

`reposition` (orig `:156-166`) becomes, in full:

```ts
  private readonly reposition = (): void => {
    const trigger = this.host.querySelector('.trigger');
    if (!trigger) return;
    const pop = this.pop().nativeElement;
    const root = document.documentElement;
    const place = clampPopover(
      trigger.getBoundingClientRect(),
      { width: pop.offsetWidth, height: pop.offsetHeight },
      { width: root.clientWidth, height: root.clientHeight },
      this.align(),
    );
    this.popTop.set(place.top);
    this.popLeft.set(place.left);
  };
```

- [ ] **Step 5: Re-measure once the popover is laid out**

The effect runs before the template's bindings refresh. On the fallback path
`.fallback-closed` is therefore still set at the first `reposition`, and the
popover measures 0×0. One re-measure on the next frame fixes that on both
paths. In the constructor's effect (V194-1b's version), old → new:

```ts
      this.reposition();
      window.addEventListener('scroll', this.reposition, { capture: true, passive: true });
```

```ts
      this.reposition();
      const frame = requestAnimationFrame(this.reposition);
      window.addEventListener('scroll', this.reposition, { capture: true, passive: true });
```

and in its `onCleanup`, old → new:

```ts
      onCleanup(() => {
        window.removeEventListener('scroll', this.reposition, true);
```

```ts
      onCleanup(() => {
        cancelAnimationFrame(frame);
        window.removeEventListener('scroll', this.reposition, true);
```

If the spec run reports `requestAnimationFrame is not defined`, guard both
calls with `typeof requestAnimationFrame === 'function'`. Do not polyfill
it.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/hint.spec.ts`
Expected: PASS (V194-1b's 19 + 8 clamp = 27).

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/layout.spec.ts`
Expected: PASS.

The clamp is not checked in a real browser here (the ancestor-transform case
and the 390 / 768 / 1440 geometry). V194-3 builds the layout audit's `hint`
check and V194-17 runs it against the replica (Global Constraints).

Close: standard (test: frontend/src/app/ui/hint.spec.ts); one frontend commit `feat(v194): sb-hint clamps its popover inside the viewport, flipping above when needed (V194-2)` naming `frontend/src/app/ui/hint.ts`, `frontend/src/app/ui/hint.spec.ts`.

### Task V194-2b: `sb-hint` closes when its `<dialog>` host starts closing

**Model:** sonnet — an event hand-off between three existing components, specified by A1's Host close rule.

**Files:**
- Modify: `frontend/src/app/ui/hint.ts` (a constant after V194-2's `clampPopover`; the constructor's effect as V194-2 left it; a method after V194-1b's `hide`)
- Modify: `frontend/src/app/ui/hint.spec.ts` (imports; new `describe` blocks at the end)
- Modify: `frontend/src/app/ui/layout.ts:18` (import), `:639-644` (`Drawer.requestClose`)
- Modify: `frontend/src/app/ui/confirm-dialog.ts:15` (insert after), `:143-148` (`ConfirmDialog.requestClose`)
- Test: `frontend/src/app/ui/hint.spec.ts`

**Interfaces:**
- Consumes: `requestClose` (`Drawer`, `layout.ts:639`; `ConfirmDialog`, `confirm-dialog.ts:143`); `installDialogPolyfill` (`frontend/src/app/testing/dialog-polyfill.ts`); `provideMotion` (`frontend/src/app/ui/motion/motion.service.ts:51`); `POPOVER_OPEN_ATTR` (V194-1); V194-1b's constructor effect.
- Produces: `DIALOG_CLOSING_EVENT = 'sb-dialog-closing'` (exported from `frontend/src/app/ui/hint.ts`), a non-bubbling `Event` that `Drawer.requestClose` and `ConfirmDialog.requestClose` dispatch on their `<dialog>` the moment the exit starts; a hint inside a `<dialog>` closes on it, and on that dialog's native `close`.

- [ ] **Step 1: Write the failing tests**

`hint.spec.ts` imports, as V194-2 left them, old → new:

```ts
import { Component, provideZonelessChangeDetection } from '@angular/core';
```

```ts
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
```

and

```ts
import { Hint, clampPopover, supportsPopover } from './hint';
```

```ts
import { DIALOG_CLOSING_EVENT, Hint, clampPopover, supportsPopover } from './hint';
import { ConfirmDialog } from './confirm-dialog';
import { Drawer } from './layout';
import { provideMotion } from './motion/motion.service';
import { installDialogPolyfill } from '../testing/dialog-polyfill';
```

Append at the end of `hint.spec.ts`:

```ts

@Component({
  imports: [Drawer, Hint],
  template: `
    <sb-drawer [open]="open()" heading="AAPL">
      <sb-hint text="Leg 1 of 2 of one plan." label="About legs" />
    </sb-drawer>
  `,
})
class DrawerHost {
  readonly open = signal(true);
}

describe('Hint inside a closing dialog host (v194 A1)', () => {
  let fixture: ComponentFixture<DrawerHost>;

  beforeEach(() => {
    installDialogPolyfill();
    // Motion on, so the drawer's exit is still running when we look: the hint
    // must hide when the close STARTS, not when the dialog finally closes.
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('on')] });
    fixture = TestBed.createComponent(DrawerHost);
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const dialog = () => el().querySelector('sb-drawer dialog') as HTMLDialogElement;
  const trigger = () => el().querySelector('sb-hint button') as HTMLButtonElement;
  const pop = () => el().querySelector('sb-hint [role=tooltip]') as HTMLElement;
  /** Twice: the host's close sets the hint's signals, which need their own pass. */
  const settle = () => {
    fixture.detectChanges();
    fixture.detectChanges();
  };

  it('hides a pinned hint as soon as the drawer starts its exit', () => {
    trigger().click();
    settle();
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    (el().querySelector('sb-drawer button.close') as HTMLButtonElement).click();
    settle();
    expect(dialog().hasAttribute('open')).toBe(true); // the exit animation is still running
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
    expect(trigger().getAttribute('aria-expanded')).toBe('false');
  });

  it('hides a pinned hint when the drawer is closed without its exit', () => {
    trigger().click();
    settle();
    fixture.componentInstance.open.set(false);
    settle();
    expect(dialog().hasAttribute('open')).toBe(false);
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
  });

  it('ignores a closing event on some other dialog', () => {
    trigger().click();
    settle();
    const other = document.createElement('dialog');
    document.body.appendChild(other);
    other.dispatchEvent(new Event(DIALOG_CLOSING_EVENT));
    settle();
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    other.remove();
  });
});

@Component({
  imports: [ConfirmDialog],
  template: `<sb-confirm-dialog [open]="true" title="Close AAPL" consequence="The paper trade closes at the last price." />`,
})
class ConfirmHost {}

describe('ConfirmDialog announces its close (v194 A1)', () => {
  it('dispatches a non-bubbling sb-dialog-closing on its <dialog> when Cancel starts the exit', () => {
    installDialogPolyfill();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('on')] });
    const fixture = TestBed.createComponent(ConfirmHost);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const seen: Event[] = [];
    root.querySelector('dialog')!.addEventListener(DIALOG_CLOSING_EVENT, (event) => seen.push(event));
    const cancel = [...root.querySelectorAll('button')].find((b) => b.textContent!.trim() === 'Cancel')!;
    cancel.click();
    fixture.detectChanges();
    expect(seen).toHaveLength(1);
    expect(seen[0].bubbles).toBe(false);
    expect(DIALOG_CLOSING_EVENT).toBe('sb-dialog-closing');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/hint.spec.ts`
Expected: FAIL — `DIALOG_CLOSING_EVENT` is not exported by `./hint`
(compile error).

- [ ] **Step 3: The hint listens to its host dialog**

`hint.ts` — after V194-2's `clampPopover` function insert:

```ts

/** Fired (non-bubbling) on a modal <dialog> host the moment it starts to
 *  close -- sb-drawer and sb-confirm-dialog, from requestClose(). A hint
 *  inside listens and closes, because a pinned manual popover is not hidden
 *  by its ancestor dialog closing and would stay painted through the exit. */
export const DIALOG_CLOSING_EVENT = 'sb-dialog-closing';
```

In the constructor's effect (as V194-2 left it), old → new:

```ts
      const frame = requestAnimationFrame(this.reposition);
```

```ts
      const frame = requestAnimationFrame(this.reposition);
      const unwatch = this.watchHostDialog();
```

and in its `onCleanup`, old → new:

```ts
        cancelAnimationFrame(frame);
```

```ts
        cancelAnimationFrame(frame);
        unwatch();
```

After V194-1b's `hide` helper (the class's last method) insert:

```ts

  /** A hint inside a modal <dialog> host (sb-drawer, sb-confirm-dialog)
   *  closes when that dialog starts closing (v194 A1). A pinned manual
   *  popover is not hidden by its ancestor dialog closing, so it would stay
   *  painted in the top layer through the drawer's exit animation. `close`
   *  covers a host shut without its exit (the drawer's [open] input going
   *  false). Looked up on open, not in the constructor: a projected hint is
   *  not inside its dialog yet when it is created. Returns the remover. */
  private watchHostDialog(): () => void {
    const dialog = this.host.closest('dialog');
    if (!dialog) return () => undefined;
    const onClosing = (): void => this.close();
    dialog.addEventListener(DIALOG_CLOSING_EVENT, onClosing);
    dialog.addEventListener('close', onClosing);
    return () => {
      dialog.removeEventListener(DIALOG_CLOSING_EVENT, onClosing);
      dialog.removeEventListener('close', onClosing);
    };
  }
```

- [ ] **Step 4: The two dialog hosts announce their close**

`frontend/src/app/ui/layout.ts:18` — old → new:

```ts
import { Hint } from './hint';
```

```ts
import { DIALOG_CLOSING_EVENT, Hint } from './hint';
```

`layout.ts:639-644` (`Drawer.requestClose`) — after
`    this.closing.set(true);` (line 642) insert:

```ts
    // Hints inside close now, not after the exit (v194 A1; hint.ts).
    element.dispatchEvent(new Event(DIALOG_CLOSING_EVENT));
```

`frontend/src/app/ui/confirm-dialog.ts:15` — after
`import { FocusTrap } from './focus-trap';` insert:

```ts
import { DIALOG_CLOSING_EVENT } from './hint';
```

`confirm-dialog.ts:143-148` (`ConfirmDialog.requestClose`) — after
`    this.closing.set(true);` (line 146) insert:

```ts
    // Hints inside close now, not after the fade (v194 A1; hint.ts).
    element.dispatchEvent(new Event(DIALOG_CLOSING_EVENT));
```

`ConfirmDialog` projects no content today, so no hint can sit in it yet. It
announces anyway, because spec A1 names both hosts, and a future hint in its
consequence line then needs no change. `hint.ts` imports neither host, so
the new imports add no cycle.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/hint.spec.ts`
Expected: PASS (V194-2's 27 + 3 dialog host + 1 confirm = 31). If the "exit
is still running" test sees the dialog already closed,
`provideMotion('on')` has not reached the drawer's `MotionService`. Check
`motion.active()` in the drawer. Do not switch the test to `'off'`: then it
no longer proves that the hint closes when the exit *starts*.

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/layout.spec.ts`
Expected: PASS (the drawer's header, swipe and close tests are unchanged).

Close: standard (test: frontend/src/app/ui/hint.spec.ts); one frontend commit `feat(v194): sb-hint closes when its drawer or confirm dialog starts closing (V194-2b)` naming `frontend/src/app/ui/hint.ts`, `frontend/src/app/ui/hint.spec.ts`, `frontend/src/app/ui/layout.ts`, `frontend/src/app/ui/confirm-dialog.ts`.

# Phase 2 — The layout audit opens every hint

### Task V194-3: Layout audit `hint` check: pure `hintVerdict`, eighth `CHECKS` entry, Playwright hover/tap

**Model:** sonnet — a pure verdict function with table tests plus a Playwright loop in an existing script, shape fixed by spec A2 and the ledger.

**Files:**
- Modify: `frontend/scripts/layout-audit-lib.mjs:29` (`CHECKS`), insert after `:126` (`hintVerdict`, after `vcenterGeometry`)
- Modify: `frontend/scripts/layout-audit-lib.test.mjs:9-12` (imports), `:40-42` (the `CHECKS` test), `:170-173` (`countByCheck` test), new tests at the end
- Modify: `frontend/scripts/layout-audit.mjs:8` and `:16-17` (header doc), `:41-44` (imports), insert before `:253` (`measureHint`, `hintFinding`, `closeHint`, `auditHints`), `:351-352` (`auditWidth` loop)
- Test: `frontend/scripts/layout-audit-lib.test.mjs`

**Interfaces:**
- Consumes: `CHECKS`, `vcenterGeometry`, `TOUCH_MAX_WIDTH` (`frontend/scripts/layout-audit-lib.mjs`); `auditPage`, `auditWidth` (`frontend/scripts/layout-audit.mjs`); the `sb-hint` DOM from V194-1b (`sb-hint > button.trigger` with `aria-label` and `aria-describedby` naming the `role="tooltip"` popover's id).
- Produces: `hintVerdict(rect: { left, top, width, height }, viewport: { width, height }, hits: { center: boolean, corner: boolean }) -> { ok: boolean, reason: 'zero-size' | 'off-screen' | 'covered-center' | 'covered-corner' | null }` (exported from `layout-audit-lib.mjs`); `CHECKS` gains `'hint'` (eighth, last); findings `{ route, width, check: 'hint', selector, text, detail }` with the trigger's `aria-label` in `text` and `detail`. V194-17 runs it.

**Decision order.** A popover with no area is `zero-size`: it never opened, or
it opened as an empty box. A popover any part of which lies outside the
viewport (0.5px tolerance for sub-pixel rects) is `off-screen`. The topmost
element at its centre not being inside it means something paints over it, or
an ancestor clips it: `covered-center`. The same at its top-left + 8px is
`covered-corner`. Otherwise it passes. The first failing rule is the
reason. Allow-list rules are unchanged: `validateAllow` still accepts any
`CHECKS` entry, and per spec A2 a `hint` finding is fixed, never allowed.

- [ ] **Step 1: Write the failing tests**

`layout-audit-lib.test.mjs:9-12` — old → new (add `hintVerdict`):

```js
import {
  CHECKS, FULL_WIDTHS, ROUTES, classify, countByCheck, dedupe, formatFinding, inScope, isVisuallyHidden, parseArgs, pickIds,
  resolveRoute, slug, validateAllow, vcenterGeometry,
} from './layout-audit-lib.mjs';
```

```js
import {
  CHECKS, FULL_WIDTHS, ROUTES, classify, countByCheck, dedupe, formatFinding, hintVerdict, inScope, isVisuallyHidden, parseArgs,
  pickIds, resolveRoute, slug, validateAllow, vcenterGeometry,
} from './layout-audit-lib.mjs';
```

`:40-42` — old → new:

```js
test('CHECKS are the spec six plus vcenter, in order', () => {
  assert.deepEqual([...CHECKS], ['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter']);
});
```

```js
test('CHECKS are the spec six plus vcenter and hint (v194 A2), in order', () => {
  assert.deepEqual([...CHECKS], ['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter', 'hint']);
});
```

`:172` (inside the `countByCheck` test) — old → new:

```js
    { overflow: 0, offscreen: 1, clipped: 0, tap: 2, text: 0, baseline: 0, vcenter: 0 });
```

```js
    { overflow: 0, offscreen: 1, clipped: 0, tap: 2, text: 0, baseline: 0, vcenter: 0, hint: 0 });
```

Append at the end of the file:

```js

// hintVerdict (v194 A2): an opened sb-hint popover's rect, the viewport, and whether the
// topmost element at its centre and at its top-left + 8px lies inside it.
const VIEW = { width: 1440, height: 900 };
const box = (left, top, width = 200, height = 60) => ({ left, top, width, height });
const BOTH = { center: true, corner: true };

test('hintVerdict: a popover inside the viewport and on top passes', () => {
  assert.deepEqual(hintVerdict(box(100, 100), VIEW, BOTH), { ok: true, reason: null });
  assert.deepEqual(hintVerdict(box(8, 8, 1424, 884), VIEW, BOTH), { ok: true, reason: null });
});

test('hintVerdict: clipped by an ancestor or painted over at its centre fails covered-center', () => {
  // The v194 regression: an .sb-lift card's transform made the card the containing block, and the
  // card's overflow clip left the card itself, not the popover, topmost at the popover's centre.
  assert.deepEqual(hintVerdict(box(100, 100), VIEW, { center: false, corner: true }), { ok: false, reason: 'covered-center' });
  assert.deepEqual(hintVerdict(box(100, 100), VIEW, { center: false, corner: false }), { ok: false, reason: 'covered-center' });
});

test('hintVerdict: covered only at the top-left corner fails covered-corner', () => {
  assert.deepEqual(hintVerdict(box(100, 100), VIEW, { center: true, corner: false }), { ok: false, reason: 'covered-corner' });
});

test('hintVerdict: past any viewport edge fails off-screen, before the hit test', () => {
  for (const rect of [box(-20, 100), box(100, -20), box(1300, 100), box(100, 870)]) {
    assert.deepEqual(hintVerdict(rect, VIEW, BOTH), { ok: false, reason: 'off-screen' }, JSON.stringify(rect));
  }
  assert.equal(hintVerdict(box(1300, 100), VIEW, { center: false, corner: false }).reason, 'off-screen');
});

test('hintVerdict: sub-pixel rects within half a pixel of an edge are inside', () => {
  assert.equal(hintVerdict(box(-0.4, 0, 200, 60), VIEW, BOTH).ok, true);
  assert.equal(hintVerdict(box(1240.3, 100, 200, 60), VIEW, BOTH).ok, true);
  assert.equal(hintVerdict(box(1241, 100, 200, 60), VIEW, BOTH).reason, 'off-screen');
});

test('hintVerdict: a popover with no area fails zero-size, whatever else is true', () => {
  assert.deepEqual(hintVerdict(box(0, 0, 0, 0), VIEW, { center: false, corner: false }), { ok: false, reason: 'zero-size' });
  assert.deepEqual(hintVerdict(box(100, 100, 200, 0), VIEW, BOTH), { ok: false, reason: 'zero-size' });
  assert.deepEqual(hintVerdict(box(-500, 100, 0, 60), VIEW, BOTH), { ok: false, reason: 'zero-size' });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test "$WT/frontend/scripts/layout-audit-lib.test.mjs"`
Expected: FAIL. The module does not export `hintVerdict`, so the import is a
`SyntaxError`, and every test in the file fails to load.

- [ ] **Step 3: Implement in `layout-audit-lib.mjs`**

`:29` — old → new:

```js
export const CHECKS = Object.freeze(['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter']);
```

```js
export const CHECKS = Object.freeze(['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter', 'hint']);
```

After `vcenterGeometry` (its closing `}` is line 126) insert:

```js

/** Sub-pixel slack for the hint check's viewport test: a rect at -0.4px is a rounding artefact, not off-screen. */
const HINT_EDGE_SLACK_PX = 0.5;

/**
 * The hint check's verdict (spec v194 A2) on one opened sb-hint popover: its
 * viewport rect, the viewport size, and whether the topmost element at its
 * centre and at its top-left + 8px is inside it (layout-audit.mjs
 * measureHint). The first failing rule is the reason: zero-size (never
 * opened), off-screen (any edge past the viewport), covered-center (an
 * ancestor clips it or something paints over it), covered-corner. Runs in
 * Node on the measured numbers, so unlike vcenterGeometry it is never
 * shipped into the page.
 */
export function hintVerdict(rect, viewport, hits) {
  if (!(rect.width > 0 && rect.height > 0)) return { ok: false, reason: 'zero-size' };
  const inside = rect.left >= -HINT_EDGE_SLACK_PX && rect.top >= -HINT_EDGE_SLACK_PX
    && rect.left + rect.width <= viewport.width + HINT_EDGE_SLACK_PX
    && rect.top + rect.height <= viewport.height + HINT_EDGE_SLACK_PX;
  if (!inside) return { ok: false, reason: 'off-screen' };
  if (!hits.center) return { ok: false, reason: 'covered-center' };
  if (!hits.corner) return { ok: false, reason: 'covered-corner' };
  return { ok: true, reason: null };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test "$WT/frontend/scripts/layout-audit-lib.test.mjs"`
Expected: PASS, every test (the existing ones unchanged apart from the two
edited assertions, plus 6 new).

- [ ] **Step 5: Drive it from `layout-audit.mjs`**

Header doc, `:8` — old → new:

```js
 * headless, on browse.mjs's persistent profile, and reports seven checks:
```

```js
 * headless, on browse.mjs's persistent profile, and reports eight checks:
```

After `:17` (the second `vcenter` line) insert:

```js
 *   hint       an sb-hint popover that, opened the way the device opens it (hover at 1440, tap at
 *              <= 1023), is zero-size, past a viewport edge, or not topmost at its centre and at
 *              its top-left + 8px (spec v194 A2; the trigger's aria-label names it). Never allowed.
```

Imports, `:41-44` — old → new (add `hintVerdict`):

```js
  classify, countByCheck, dedupe, formatFinding, inScope, isVisuallyHidden, parseArgs, pickIds, resolveRoute, slug, validateAllow, vcenterGeometry,
```

```js
  classify, countByCheck, dedupe, formatFinding, hintVerdict, inScope, isVisuallyHidden, parseArgs, pickIds, resolveRoute, slug,
  validateAllow, vcenterGeometry,
```

Before `:253` (`/** Same page-ready rule as browse.mjs ...`) insert:

```js
/** How long an opened hint gets to show and be placed (one frame plus the reposition) before it is measured. */
const HINT_SETTLE_MS = 150;

/** Runs inside the page (page.evaluate): the opened popover's geometry for hintVerdict. Self-contained. */
function measureHint(id) {
  const root = document.documentElement;
  const viewport = { width: root.clientWidth, height: root.clientHeight };
  const pop = id ? document.getElementById(id) : null;
  if (!pop) return { rect: { left: 0, top: 0, width: 0, height: 0 }, viewport, hits: { center: false, corner: false } };
  const r = pop.getBoundingClientRect();
  const on = (x, y) => {
    const hit = document.elementFromPoint(x, y);
    return Boolean(hit && pop.contains(hit));
  };
  return {
    rect: { left: r.left, top: r.top, width: r.width, height: r.height },
    viewport,
    hits: { center: on(r.left + r.width / 2, r.top + r.height / 2), corner: on(r.left + 8, r.top + 8) },
  };
}

const hintFinding = (label, reason, rect) => ({
  check: 'hint',
  selector: `sb-hint > button[aria-label="${label}"]`,
  text: label,
  detail: `"${label}" popover ${reason} at ${Math.round(rect.left)},${Math.round(rect.top)} `
    + `${Math.round(rect.width)}x${Math.round(rect.height)}`,
});

/** Escape closes a hint however it opened (hover, focus or a tap's pin); the mouse then leaves it. */
async function closeHint(page, trigger, touch) {
  await trigger.press('Escape', { timeout: 2000 }).catch(() => undefined);
  if (!touch) await page.mouse.move(0, 0);
}

/**
 * The hint check (spec v194 A2): open every visible sb-hint the way the device would -- hover at
 * desktop widths, tap at or below TOUCH_MAX_WIDTH -- and judge its popover with hintVerdict.
 * Playwright-side, not in auditPage, because hover and tap must be real input events. A trigger
 * Playwright cannot hover or tap (detached by a re-render, or covered) is logged, not reported:
 * the tap check owns hit areas.
 */
async function auditHints(page, width) {
  const touch = width <= TOUCH_MAX_WIDTH;
  const triggers = page.locator('sb-hint > button.trigger');
  const findings = [];
  for (let i = 0, n = await triggers.count(); i < n; i += 1) {
    const trigger = triggers.nth(i);
    if (!(await trigger.isVisible())) continue;
    const label = (await trigger.getAttribute('aria-label')) ?? '';
    try {
      await (touch ? trigger.tap({ timeout: 2000 }) : trigger.hover({ timeout: 2000 }));
    } catch (error) {
      console.error(`  hint "${label}" @${width}: cannot ${touch ? 'tap' : 'hover'} (${String(error).split('\n')[0]})`);
      continue;
    }
    await page.waitForTimeout(HINT_SETTLE_MS);
    const geometry = await page.evaluate(measureHint, await trigger.getAttribute('aria-describedby'));
    const verdict = hintVerdict(geometry.rect, geometry.viewport, geometry.hits);
    if (!verdict.ok) findings.push(hintFinding(label, verdict.reason, geometry.rect));
    await closeHint(page, trigger, touch);
  }
  return findings;
}

```

`auditWidth`, `:351-352` — old → new (hints run after the screenshot, so no
shot shows an open popover):

```js
      await screenshot(page, join(opts.out, `${slug(route)}@${width}.png`), width);
      console.error(`${route} @${width}: ${raw.length} raw finding(s)`);
```

```js
      await screenshot(page, join(opts.out, `${slug(route)}@${width}.png`), width);
      const hints = await auditHints(page, width);
      findings.push(...hints.map((f) => ({ route, width, ...f })));
      console.error(`${route} @${width}: ${raw.length + hints.length} raw finding(s)`);
```

`report()` and `countByCheck` take the new check from `CHECKS`, so they need
no edit. Neither does `validateAllow`: allow-list rules are unchanged.

- [ ] **Step 6: Syntax-check the driver**

Run: `node --check "$WT/frontend/scripts/layout-audit.mjs"`
Expected: exit 0, no output. The browser half is proven by the replica
audit run in V194-17 (spec A2, Verification), not here. That run needs the
built bundle, the local replica and a signed-in profile, which V194-17 sets
up. The hover/tap pass adds roughly 0.2s per visible hint per route and
width; V194-17 records the measured run time.

Close: standard (test: frontend/scripts/layout-audit-lib.test.mjs); one frontend commit `feat(v194): layout audit hint check -- opens every sb-hint and fails one that is clipped, covered or off-screen (V194-3)` naming `frontend/scripts/layout-audit-lib.mjs`, `frontend/scripts/layout-audit-lib.test.mjs`, `frontend/scripts/layout-audit.mjs`. `docs/claude/ui-design.md` § Checklist lists the audit's checks in prose and does not yet name `hint`; that doc edit (with its `AGENTS.md` mirror) is left to the controller (see the hand-back), not done here.

