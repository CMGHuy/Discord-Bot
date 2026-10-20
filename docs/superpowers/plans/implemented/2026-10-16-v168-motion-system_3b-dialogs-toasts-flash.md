# v168 Motion system, part 3b: dialogs, toasts and the flash (MO12..MO14)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `grep -n "^### Task MO12:" -A 600 docs/superpowers/plans/2026-10-16-v168-motion-system_3b-dialogs-toasts-flash.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v168-motion-system-design.md`](../specs/2026-10-16-v168-motion-system-design.md) (its `## Amendments from the plan brief` bind and override earlier sections).
**Index:** [`2026-10-16-v168-motion-system_0-index.md`](2026-10-16-v168-motion-system_0-index.md): `## Global Constraints`, `## Where to work` (`$WT`, `$R`, the narrow-run command, `GATES`), `## Parallelisation` and the `## Task ledger` apply to every task below and are not repeated.

**Why a separate file:** part 3 (`_3-animations.md`, MO9..MO11) would have passed the 1500-line cap with MO12 in it; tasks are never split or compressed, so MO12..MO14 live here whole. Ids, files and contracts are the ledger's, unchanged.

**Consumed from earlier tasks (index ledger contracts):**
- MO3, `frontend/src/styles/motion.css`: `.sb-drawer-in` / `.sb-drawer-out` (below 640px `sb-drawer dialog.sb-drawer-in|out` switch to `sb-sheet-in|out`), `.sb-pop-in`, `.sb-fade-out`, the backdrop fade on `sb-drawer dialog[open]::backdrop` / `sb-confirm-dialog dialog[open]::backdrop`, the Reduced fade and the Off/pending `animation: none` on all of them; `.flash-up` / `.flash-down` at `calc(1100ms * var(--motion-scale))` with `--flash-*-text`.
- MO4: `MotionService` (`mode`, `full`, `active`), `provideMotion`, `MotionStarts.record/count/entries` from `frontend/src/app/ui/motion/motion.service.ts` and `frontend/src/app/ui/motion/motion-starts.ts`; every spec runs under `provideMotion('off')` unless it provides its own.
- MO10 edited `frontend/src/app/ui/layout.ts` (`.panel` gained `sb-lift`) before MO12 edits its Drawer.

**Line numbers below are pre-v167.** Every edit is anchored on quoted text, never on a line number alone. If an anchor is missing, stop and report it rather than guessing.

---

### Task MO12: Drawer and ConfirmDialog in and out; phone bottom sheet; tablet 85vw

**Model:** sonnet — two dialog components share one exit helper, flows fixed by spec §3a

**Files:**
- Create: `frontend/src/app/ui/motion/exit.ts`
- Create: `frontend/src/app/ui/motion/exit.spec.ts`
- Modify: `frontend/src/app/ui/layout.ts` (the `Drawer` component: template, styles, class; today `:330-443`)
- Modify: `frontend/src/app/ui/layout.spec.ts` (the drawer phone case, today `:112-119`)
- Modify: `frontend/src/app/ui/confirm-dialog.ts` (template `:36-60`, class `:97-131`)
- Modify: `frontend/src/app/ui/controls.spec.ts` (two new `describe` blocks at the end)

**Interfaces:**
- Consumes: MO4's `MotionService.active` (`true` under `on` and `reduced`) and `provideMotion`; MO3's `.sb-drawer-in` / `.sb-drawer-out` (phone: `sb-drawer dialog.sb-drawer-in|out` switch to `sb-sheet-in|out`), `.sb-pop-in`, `.sb-fade-out`, the backdrop fade on `sb-drawer dialog[open]::backdrop` / `sb-confirm-dialog dialog[open]::backdrop`, and their Reduced (fade) / Off and pending (`animation: none`) rules. v167's `--panel-radius`, `--radius-sm`. `installDialogPolyfill()` (`frontend/src/app/testing/dialog-polyfill.ts`: `showModal`/`close` only, no `cancel` event, no `animationend`).
- Produces: `export const EXIT_FALLBACK_MS = 300`; `export function playExit(element: HTMLElement, cls: string, animate: boolean, done: () => void): () => void` (no animation → `done()` at once and a no-op cancel; else adds `cls`, waits for an `animationend` whose target is `element` itself or the fallback timer, removes `cls`, calls `done()` exactly once; the returned function cancels: removes `cls`, never calls `done`). `Drawer` and `ConfirmDialog` gain `protected readonly closing = signal(false)` and `protected requestClose(): void`; the close button, Escape (`(cancel)` with `preventDefault()`) and, on the Drawer, the backdrop click all go through it; it animates when `motion.active()`. Drawer phone geometry `margin: auto 0 0; width: 100vw; height: auto; max-height: 85dvh` with a top `--panel-radius` and a `.drag-handle`; tablet `width: 85vw`.

**Not in this task:** a parent that closes a dialog by setting `open` to `false` still closes it at once (its body is `@if (open())`, destroyed with the input, so there is nothing left to animate); only the component's own close paths play the exit. `ConfirmDialog` gains no backdrop-click dismissal (it has none today; a destructive gate keeps its two explicit buttons and Escape). `ConfirmDialog` still emits `cancelled` on every native `close`, as today.

- [ ] **Step 1: Write the failing helper spec**

Create `frontend/src/app/ui/motion/exit.spec.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EXIT_FALLBACK_MS, playExit } from './exit';

/* jsdom runs no CSS animation and never fires animationend on its own, so
 * every case dispatches it by hand or lets the fallback timer finish. */
describe('playExit (v168 §3a)', () => {
  afterEach(() => vi.useRealTimers());

  const element = () => document.createElement('div');
  const end = (target: Element) => target.dispatchEvent(new Event('animationend', { bubbles: true }));

  it('finishes at once, adding nothing, when it must not animate', () => {
    const el = element();
    const done = vi.fn();
    playExit(el, 'sb-fade-out', false, done);
    expect(done).toHaveBeenCalledTimes(1);
    expect(el.className).toBe('');
  });

  it('plays the class until its own animationend, then removes it and finishes once', () => {
    const el = element();
    const done = vi.fn();
    playExit(el, 'sb-fade-out', true, done);
    expect(el.classList).toContain('sb-fade-out');
    expect(done).not.toHaveBeenCalled();
    end(el);
    expect(done).toHaveBeenCalledTimes(1);
    expect(el.classList).not.toContain('sb-fade-out');
    end(el);
    expect(done).toHaveBeenCalledTimes(1);
  });

  it('ignores an animationend bubbling up from a child', () => {
    const el = element();
    const child = el.appendChild(document.createElement('span'));
    const done = vi.fn();
    playExit(el, 'sb-drawer-out', true, done);
    end(child);
    expect(done).not.toHaveBeenCalled();
    expect(el.classList).toContain('sb-drawer-out');
  });

  it('falls back to a timer when animationend never comes', () => {
    vi.useFakeTimers();
    const el = element();
    const done = vi.fn();
    playExit(el, 'sb-drawer-out', true, done);
    vi.advanceTimersByTime(EXIT_FALLBACK_MS - 1);
    expect(done).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(done).toHaveBeenCalledTimes(1);
    expect(el.classList).not.toContain('sb-drawer-out');
  });

  it('does not finish twice when the timer fires after animationend', () => {
    vi.useFakeTimers();
    const el = element();
    const done = vi.fn();
    playExit(el, 'sb-fade-out', true, done);
    end(el);
    vi.advanceTimersByTime(EXIT_FALLBACK_MS);
    expect(done).toHaveBeenCalledTimes(1);
  });

  it('cancels without finishing', () => {
    vi.useFakeTimers();
    const el = element();
    const done = vi.fn();
    const cancel = playExit(el, 'sb-fade-out', true, done);
    cancel();
    expect(el.classList).not.toContain('sb-fade-out');
    end(el);
    vi.advanceTimersByTime(EXIT_FALLBACK_MS);
    expect(done).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Write the failing dialog specs**

In `frontend/src/app/ui/controls.spec.ts`:

1. Change the vitest import to `import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';` and add below `import { ControlRow, Drawer, Tab, TabBar } from './layout';`:

```ts
import { EXIT_FALLBACK_MS } from './motion/exit';
import { provideMotion } from './motion/motion.service';
```

2. Append at the end of the file:

```ts
/* -- v168 §3a: dialogs play their exit before closing ---------------------
 *
 * The global test default is Motion = Off (src/test-setup.ts), under which
 * every close is immediate and the cases above hold unchanged. These opt in.
 * jsdom never fires animationend, so each case dispatches it on the dialog
 * (or lets EXIT_FALLBACK_MS run out). */
describe('dialog exits under Motion = On (v168 §3a)', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('on')] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => vi.useRealTimers());

  const el = (): HTMLElement => fixture.nativeElement;
  const q = <T extends Element>(selector: string) => el().querySelector(selector) as T;
  const end = (target: Element) => target.dispatchEvent(new Event('animationend'));
  const escape = (target: Element) => {
    const event = new Event('cancel', { cancelable: true });
    target.dispatchEvent(event);
    return event;
  };

  function openDrawer(): HTMLDialogElement {
    host.drawerOpen.set(true);
    fixture.detectChanges();
    return q<HTMLDialogElement>('sb-drawer dialog');
  }

  function openConfirm(): HTMLDialogElement {
    host.confirmOpen.set(true);
    fixture.detectChanges();
    return q<HTMLDialogElement>('sb-confirm-dialog dialog');
  }

  it('slides the drawer in while it is open', () => {
    expect(openDrawer().classList).toContain('sb-drawer-in');
  });

  it('plays the drawer exit, keeping the body mounted, then closes on animationend', () => {
    const drawer = openDrawer();
    q<HTMLButtonElement>('sb-drawer .close').click();
    fixture.detectChanges();
    expect(drawer.open).toBe(true);
    expect(drawer.classList).toContain('sb-drawer-out');
    expect(drawer.classList).not.toContain('sb-drawer-in');
    expect(q('sb-drawer .drawer-content')).not.toBeNull();
    expect(host.drawerOpen()).toBe(true);

    end(drawer);
    fixture.detectChanges();
    expect(drawer.open).toBe(false);
    expect(host.drawerOpen()).toBe(false);
    expect(drawer.classList).not.toContain('sb-drawer-out');
  });

  it('sends Escape down the same path instead of the native close', () => {
    const drawer = openDrawer();
    const event = escape(drawer);
    fixture.detectChanges();
    expect(event.defaultPrevented).toBe(true);
    expect(drawer.open).toBe(true);
    expect(drawer.classList).toContain('sb-drawer-out');
    end(drawer);
    fixture.detectChanges();
    expect(host.drawerOpen()).toBe(false);
  });

  it('sends a backdrop click down the same path', () => {
    const drawer = openDrawer();
    // jsdom's rect is all zeros, so any point with a positive x is outside it.
    drawer.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 600, clientY: 300 }));
    fixture.detectChanges();
    expect(drawer.classList).toContain('sb-drawer-out');
    end(drawer);
    fixture.detectChanges();
    expect(drawer.open).toBe(false);
  });

  it('closes on the fallback timer if animationend never arrives', () => {
    const drawer = openDrawer();
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    q<HTMLButtonElement>('sb-drawer .close').click();
    vi.advanceTimersByTime(EXIT_FALLBACK_MS);
    fixture.detectChanges();
    expect(drawer.open).toBe(false);
    expect(host.drawerOpen()).toBe(false);
  });

  it('pops the confirm dialog in and fades it out before cancelling, once', () => {
    const dialog = openConfirm();
    expect(dialog.classList).toContain('sb-pop-in');
    const cancel = q<HTMLButtonElement>('sb-confirm-dialog button');
    cancel.click();
    cancel.click();
    fixture.detectChanges();
    expect(dialog.classList).toContain('sb-fade-out');
    expect(dialog.open).toBe(true);
    expect(host.cancelled).toBe(0);

    end(dialog);
    fixture.detectChanges();
    expect(host.cancelled).toBe(1);
    expect(host.confirmed).toBe(0);
    expect(dialog.open).toBe(false);
  });

  it('sends Escape on the confirm dialog down the same path', () => {
    const dialog = openConfirm();
    const event = escape(dialog);
    fixture.detectChanges();
    expect(event.defaultPrevented).toBe(true);
    expect(dialog.classList).toContain('sb-fade-out');
    end(dialog);
    fixture.detectChanges();
    expect(host.cancelled).toBe(1);
  });

  it('plays the in-animation again when reopened after an exit', () => {
    const drawer = openDrawer();
    q<HTMLButtonElement>('sb-drawer .close').click();
    end(drawer);
    fixture.detectChanges();
    openDrawer();
    expect(drawer.classList).toContain('sb-drawer-in');
    expect(drawer.classList).not.toContain('sb-drawer-out');
  });
});

describe('dialog exits under Motion = Off (v168 §3a)', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('off')] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('closes at once on Escape and on a backdrop click, adding no exit class', () => {
    host.drawerOpen.set(true);
    fixture.detectChanges();
    const drawer = (fixture.nativeElement as HTMLElement).querySelector<HTMLDialogElement>('sb-drawer dialog')!;
    const event = new Event('cancel', { cancelable: true });
    drawer.dispatchEvent(event);
    fixture.detectChanges();
    expect(event.defaultPrevented).toBe(true);
    expect(drawer.open).toBe(false);
    expect(drawer.classList).not.toContain('sb-drawer-out');

    host.drawerOpen.set(true);
    fixture.detectChanges();
    drawer.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 600, clientY: 300 }));
    fixture.detectChanges();
    expect(drawer.open).toBe(false);
    expect(host.drawerOpen()).toBe(false);
  });
});
```

3. In `frontend/src/app/ui/layout.spec.ts`, in `describe('sb-control-row and sb-drawer on a phone (v80 D4)', ...)`, replace

```ts
  it('takes the full width on a phone', () => expect(SOURCE).toMatch(/@media \(max-width: 639px\) \{\s*\.drawer \{ width: 100vw; \}/));
```

with

```ts
  /* v168 §3a: below 640px the drawer is a bottom sheet, a geometry change
   * and not only a keyframe; from 640 to 1023px it takes 85vw from the right. */
  it('becomes a bottom sheet on a phone', () => {
    // Anchored on the .drawer rule: the control row has its own 639px block
    // earlier in the file.
    const phone = SOURCE.match(
      /@media \(max-width: 639px\) \{\s*\.drawer \{ margin: auto 0 0; width: 100vw; height: auto; max-height: 85dvh; \}([\s\S]*?)\n    \}/,
    );
    expect(phone).not.toBeNull();
    expect(phone![1]).toMatch(/\.drawer\.elev-overlay \{ border-radius: var\(--panel-radius\) var\(--panel-radius\) 0 0; border-width: 1px 0 0; \}/);
    expect(phone![1]).toMatch(/\.drag-handle \{ display: block;/);
    expect(rule('.drag-handle')).toContain('display: none');
  });
  it('takes 85vw from the right on a tablet', () =>
    expect(SOURCE).toMatch(/@media \(min-width: 640px\) and \(max-width: 1023px\) \{\s*\.drawer \{ width: 85vw; \}/));
```

- [ ] **Step 3: Run them to verify they fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/exit.spec.ts --include src/app/ui/controls.spec.ts --include src/app/ui/layout.spec.ts`
Expected: FAIL at build: `Could not resolve "./exit"` / `"./motion/exit"`. Once `exit.ts` exists: every `Motion = On` case fails (no exit class, the native close runs at once), the Off case fails on `defaultPrevented`, and both new `layout.spec.ts` cases fail. The cases of `describe('input and layout components', ...)` keep passing.

- [ ] **Step 4: Write the exit helper**

Create `frontend/src/app/ui/motion/exit.ts`:

```ts
/**
 * Longer than every exit in styles/motion.css (200ms), so a missed
 * animationend (a hidden tab, an animation the browser skipped) can never
 * strand an open dialog.
 */
export const EXIT_FALLBACK_MS = 300;

/**
 * Play an exit class on `element`, then call `done` exactly once (spec v168
 * §3a). A `<dialog>`'s close() removes it from rendering at once, so the exit
 * has to run first and the close follow it.
 *
 * - `animate` false (Motion Off or pending): `done()` runs now, nothing is
 *   added, and the returned cancel does nothing.
 * - Otherwise `cls` is added and `done()` runs on the element's OWN
 *   animationend (a child's bubbling one is ignored) or after
 *   EXIT_FALLBACK_MS, whichever is first; `cls` is removed before `done()`.
 *
 * The returned function cancels a running exit: it removes `cls` and `done`
 * never runs.
 */
export function playExit(element: HTMLElement, cls: string, animate: boolean, done: () => void): () => void {
  if (!animate) {
    done();
    return () => undefined;
  }
  let over = false;
  const stop = (): boolean => {
    if (over) return false;
    over = true;
    clearTimeout(timer);
    element.removeEventListener('animationend', onEnd);
    element.classList.remove(cls);
    return true;
  };
  const finish = () => {
    if (stop()) done();
  };
  const onEnd = (event: Event) => {
    if (event.target === element) finish();
  };
  element.classList.add(cls);
  element.addEventListener('animationend', onEnd);
  const timer = setTimeout(finish, EXIT_FALLBACK_MS);
  return () => {
    stop();
  };
}
```

- [ ] **Step 5: The Drawer**

In `frontend/src/app/ui/layout.ts`:

1. Add `inject`, `signal` and `untracked` to the existing `@angular/core` import (keep the names already there), and add below the other local imports:

```ts
import { playExit } from './motion/exit';
import { MotionService } from './motion/motion.service';
```

2. In the Drawer's class doc comment, after the paragraph ending `making the background inert.`, add:

```ts
 *
 * Its own close paths (the × button, Escape, a backdrop click) play an exit
 * first (spec v168 §3a): `requestClose()` sets `closing`, plays
 * `.sb-drawer-out` (a sinking sheet below 640px, styles/motion.css), and only
 * then closes the dialog, so the body stays mounted for the exit. Under Motion
 * Off or pending it closes at once, as before.
```

3. Replace the Drawer template

```html
    <dialog #dialog class="drawer elev-overlay" (close)="closed.emit()" (cancel)="closed.emit()"
            (click)="onDialogClick($event)">
      <!-- Only present while open, so sbFocusTrap's constructor/ngOnDestroy
           pair runs on exactly open and close -- see focus-trap.ts. -->
      @if (open()) {
        <div sbFocusTrap class="drawer-content">
          <header>
            <h2>{{ heading() }}</h2>
            <button type="button" class="close" aria-label="Close" (click)="dismiss()">×</button>
          </header>
```

with

```html
    <!-- (cancel) is Escape: it is prevented and routed through requestClose()
         so the exit plays; the native close then fires (close) once. -->
    <dialog #dialog class="drawer elev-overlay" [class.sb-drawer-in]="!closing()"
            (close)="onClosed()" (cancel)="onCancel($event)" (click)="onDialogClick($event)">
      <!-- Only present while open, so sbFocusTrap's constructor/ngOnDestroy
           pair runs on exactly open and close -- see focus-trap.ts. -->
      @if (open()) {
        <div sbFocusTrap class="drawer-content">
          <div class="drag-handle" aria-hidden="true"></div>
          <header>
            <h2>{{ heading() }}</h2>
            <button type="button" class="close" aria-label="Close" (click)="requestClose()">×</button>
          </header>
```

(the lines after `</header>` stay as they are).

4. In the Drawer `styles`, replace

```css
    @media (max-width: 639px) {
      .drawer { width: 100vw; }
    }
```

with

```css
    /* v168 §3a: below 640px the drawer is a bottom sheet rising from the
       foot of the screen, with a drag handle and rounded top corners (its
       other edges sit flush, as on desktop); 640-1023px it is 85vw from the
       right; from 1024px the width above. */
    .drag-handle { display: none; }
    @media (max-width: 639px) {
      .drawer { margin: auto 0 0; width: 100vw; height: auto; max-height: 85dvh; }
      .drawer.elev-overlay { border-radius: var(--panel-radius) var(--panel-radius) 0 0; border-width: 1px 0 0; }
      .drag-handle { display: block; width: 36px; height: 4px; margin: var(--space-8) auto 0; border-radius: var(--radius-sm); background: var(--border-strong); }
    }
    @media (min-width: 640px) and (max-width: 1023px) {
      .drawer { width: 85vw; }
    }
```

5. Replace the `Drawer` class body from `private readonly dialog = …` to the end of `dismiss()` with:

```ts
  protected readonly closing = signal(false);

  private readonly motion = inject(MotionService);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private cancelExit: () => void = () => undefined;

  constructor() {
    effect(() => {
      const element = this.dialog().nativeElement;
      if (this.open() && !element.open) {
        untracked(() => this.stopExit());
        element.showModal();
      } else if (!this.open() && element.open) element.close();
    });
  }

  /** A click on the scrim lands on the dialog element itself; one inside the
   *  panel lands on a descendant. Checking the rect too keeps a click on the
   *  dialog's own (padding-free) surface from closing it. */
  protected onDialogClick(event: MouseEvent): void {
    const element = this.dialog().nativeElement;
    if (event.target !== element) return;
    const box = element.getBoundingClientRect();
    const inside = event.clientX >= box.left && event.clientX <= box.right
      && event.clientY >= box.top && event.clientY <= box.bottom;
    if (!inside) this.requestClose();
  }

  /** The × button, Escape and the backdrop: one path, exit first. */
  protected requestClose(): void {
    const element = this.dialog().nativeElement;
    if (this.closing() || !element.open) return;
    this.closing.set(true);
    this.cancelExit = playExit(element, 'sb-drawer-out', this.motion.active(), () => element.close());
  }

  protected onCancel(event: Event): void {
    event.preventDefault();
    this.requestClose();
  }

  /** The native close, whoever caused it: report it once. */
  protected onClosed(): void {
    this.stopExit();
    this.closed.emit();
  }

  private stopExit(): void {
    this.cancelExit();
    this.cancelExit = () => undefined;
    this.closing.set(false);
  }
```

(`readonly open`, `readonly heading` and `readonly closed` above it stay.)

- [ ] **Step 6: The ConfirmDialog**

In `frontend/src/app/ui/confirm-dialog.ts`:

1. Change the `@angular/core` import to

```ts
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
```

and add below `import { ControlRow } from './layout';`:

```ts
import { playExit } from './motion/exit';
import { MotionService } from './motion/motion.service';
```

2. In the template, replace

```html
    <dialog #dialog class="elev-overlay" (close)="cancelled.emit()" (cancel)="cancelled.emit()">
```

with

```html
    <!-- v168 §3a: Cancel and Escape (cancel, prevented) play the fade-out
         first through requestClose(); the native close then emits once. -->
    <dialog #dialog class="elev-overlay" [class.sb-pop-in]="!closing()"
            (close)="onClosed()" (cancel)="onCancel($event)">
```

and in the Cancel button replace `(click)="close()"` with `(click)="requestClose()"`.

3. Replace the class body from `private readonly dialog = …` to the end of `close()` with:

```ts
  protected readonly closing = signal(false);

  private readonly motion = inject(MotionService);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private cancelExit: () => void = () => undefined;

  constructor() {
    effect(() => {
      const element = this.dialog().nativeElement;
      // showModal() twice throws, and close() on a closed dialog fires a
      // spurious `close` event that would look like a cancellation.
      if (this.open() && !element.open) {
        untracked(() => this.stopExit());
        element.showModal();
      } else if (!this.open() && element.open) element.close();
    });
  }

  /** Cancel and Escape: one path, the fade-out first (v168 §3a). The
   *  `cancelled` output still comes from the dialog's own close event. */
  protected requestClose(): void {
    const element = this.dialog().nativeElement;
    if (this.closing() || !element.open) return;
    this.closing.set(true);
    this.cancelExit = playExit(element, 'sb-fade-out', this.motion.active(), () => element.close());
  }

  protected onCancel(event: Event): void {
    event.preventDefault();
    this.requestClose();
  }

  protected onClosed(): void {
    this.stopExit();
    this.cancelled.emit();
  }

  private stopExit(): void {
    this.cancelExit();
    this.cancelExit = () => undefined;
    this.closing.set(false);
  }
```

- [ ] **Step 7: Run the specs and the gates**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/exit.spec.ts --include src/app/ui/controls.spec.ts --include src/app/ui/layout.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/motion-home.spec.ts --include src/app/ui/motion-css.spec.ts`
Expected: `Tests  N passed (N)`, 0 failed.

Then the consumers of both dialogs (twelve files use `sb-confirm-dialog`; dashboard and tuning specs drive it), all under the global Off default:

Run: `git -C $WT grep -l "sb-confirm-dialog\|sb-drawer" -- 'frontend/src/**/*.spec.ts'` and pass every listed spec to one `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec> …` run.
Expected: `Tests  N passed (N)`, 0 failed. A failure that counts `cancelled`/`closed` twice means a spec relied on today's double emit on Escape (`(cancel)` and `(close)` both emitted): it now emits once, by design; fix the count to 1 and name the spec. Any other failure is a regression: stop and report it. Quote both verdict lines.

- [ ] **Step 8: Commit**

```bash
git -C $WT add frontend/src/app/ui/motion/exit.ts frontend/src/app/ui/motion/exit.spec.ts frontend/src/app/ui/layout.ts frontend/src/app/ui/layout.spec.ts frontend/src/app/ui/confirm-dialog.ts frontend/src/app/ui/controls.spec.ts
git -C $WT commit -m "feat(ui): v168 drawer and confirm-dialog in and out, phone bottom sheet (MO12)

playExit(element, cls, animate, done) plays an exit class and calls done
once, on the element's own animationend or a 300ms fallback. Drawer and
ConfirmDialog route their close button, Escape (cancel, prevented) and the
drawer's backdrop click through requestClose(): sb-drawer-out / sb-fade-out
first, dialog.close() after, the body mounted throughout; immediate under
Motion Off or pending. Escape now emits closed/cancelled once, not twice.
Below 640px the drawer is a bottom sheet (85dvh, rounded top, drag handle);
640-1023px it is 85vw. layout.spec's phone case rewritten for the sheet.

<frontend verdict lines>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO13: Toasts enter and leave with `animate.enter` / `animate.leave`

**Model:** haiku — two template attributes and a new spec, mechanism fixed by the brief

**Files:**
- Modify: `frontend/src/app/shell/toast-host.ts` (the `@for` item, today `:10-14`)
- Create: `frontend/src/app/shell/toast-host.spec.ts`

**Interfaces:**
- Consumes: MO3's `.sb-pop-in` (450ms spring, `backwards`) and `.sb-fade-out` (200ms, `forwards`) in `motion.css`, with their Reduced fade and Off/pending `animation: none`. Angular 21.2's built-in `animate.enter` / `animate.leave` (from `@angular/core`; no provider; `@angular/animations` is not installed and stays so). `ToastService` (`frontend/src/app/shell/toast.service.ts`: `show(message, kind = 'info', ms = 4000): number`, `dismiss(id)`, `toasts`).
- Produces: `animate.enter="sb-pop-in"` and `animate.leave="sb-fade-out"` on the toast `<button>`. Nothing later consumes it.

**How it behaves:** `animate.enter` adds `sb-pop-in` when the toast is created and removes it when its animation ends; `animate.leave` adds `sb-fade-out` when the toast leaves the `@for` and keeps the element until that animation ends (Angular caps the wait). Under Motion Off or pending the classes resolve to `animation: none`, so Angular finds no animation and removes the toast at once. In jsdom (no `getAnimations`) and under `TestBed`'s disabled animations a leaving toast is removed immediately, which is what the spec asserts; the attributes themselves are asserted as source text.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/shell/toast-host.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ToastHost } from './toast-host';
import { ToastService } from './toast.service';

describe('ToastHost', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  afterEach(() => vi.useRealTimers());

  function mount() {
    const fixture = TestBed.createComponent(ToastHost);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const shown = () => [...el.querySelectorAll<HTMLButtonElement>('.toast')];
    return { fixture, shown, toasts: TestBed.inject(ToastService) };
  }

  it('renders each toast as an overlay button carrying its kind', () => {
    const { fixture, shown, toasts } = mount();
    toasts.show('Scan triggered');
    toasts.show('Could not close trade', 'error');
    fixture.detectChanges();
    expect(shown().map((button) => button.textContent!.trim())).toEqual(['Scan triggered', 'Could not close trade']);
    expect(shown()[0].classList).toContain('toast');
    expect(shown()[0].classList).toContain('elev-overlay');
    expect(shown()[0].classList).toContain('info');
    expect(shown()[1].classList).toContain('error');
  });

  it('removes a clicked toast; in jsdom the leave animation is skipped, so at once', async () => {
    const { fixture, shown, toasts } = mount();
    toasts.show('Scan triggered');
    fixture.detectChanges();
    shown()[0].click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(shown()).toEqual([]);
  });

  it('auto-dismisses an info toast after its time, and keeps an error', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, shown, toasts } = mount();
    toasts.show('Saved', 'info', 4000);
    toasts.show('Could not close trade', 'error');
    vi.advanceTimersByTime(4000);
    vi.useRealTimers();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(shown().map((button) => button.textContent!.trim())).toEqual(['Could not close trade']);
  });

  /* v168 §3a: the item pops in and fades out. Source text, because TestBed
   * disables animations and jsdom has no getAnimations(), so neither class
   * is ever observable on a rendered node here. */
  it('enters with sb-pop-in and leaves with sb-fade-out, both defined in motion.css', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/toast-host.ts'), 'utf8');
    const button = source.match(/<button class="toast elev-overlay"[^>]*>/)![0];
    expect(button).toContain('animate.enter="sb-pop-in"');
    expect(button).toContain('animate.leave="sb-fade-out"');
    const motion = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8');
    expect(motion).toMatch(/^\.sb-pop-in \{/m);
    expect(motion).toMatch(/^\.sb-fade-out \{/m);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/shell/toast-host.spec.ts`
Expected: FAIL in `enters with sb-pop-in and leaves with sb-fade-out` only (the attributes are missing). The other three describe today's behaviour and pass; they are kept as the regression net for Step 3. If a 60 s `Timeout waiting for worker` appears instead, re-run once (machine load).

- [ ] **Step 3: Add the two attributes**

In `frontend/src/app/shell/toast-host.ts`, replace

```html
        <button class="toast elev-overlay" [class]="toast.kind" (click)="toasts.dismiss(toast.id)">
```

with

```html
        <!-- v168 §3a: pops in, fades out before leaving the DOM. The classes
             are global (styles/motion.css); under Motion Off or pending they
             are animation: none, so Angular removes the toast at once. -->
        <button class="toast elev-overlay" [class]="toast.kind" animate.enter="sb-pop-in"
                animate.leave="sb-fade-out" (click)="toasts.dismiss(toast.id)">
```

No import is needed: `animate.enter` / `animate.leave` are template syntax of `@angular/core` 21.2.

- [ ] **Step 4: Run the spec and the shell specs**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/shell/toast-host.spec.ts --include src/app/shell/shell.spec.ts --include src/app/ui/motion-home.spec.ts`
Expected: `Tests  N passed (N)`, 0 failed. If the build rejects `animate.enter` ("Can't bind" or "unknown attribute"), stop and report the exact message with `npm --prefix $WT/frontend ls @angular/core`: the brief verified 21.2.21 exports it. Quote the verdict line.

- [ ] **Step 5: Commit**

```bash
git -C $WT add frontend/src/app/shell/toast-host.ts frontend/src/app/shell/toast-host.spec.ts
git -C $WT commit -m "feat(shell): v168 toasts pop in and fade out (MO13)

Angular 21's animate.enter / animate.leave on the toast item, with the
global sb-pop-in / sb-fade-out classes, so a dismissed toast plays its
exit before leaving the DOM; under Motion Off or pending the classes are
animation: none and the toast goes at once. First toast-host spec: kinds,
click and auto dismissal, and the two attributes (source text).

<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO14: Cell flash refinement: skip under Off, record the start, comment rewrite

**Model:** haiku — a guard, a record call and two spec opt-ins, all fixed by the spec

**Files:**
- Modify: `frontend/src/app/ui/flash.ts` (imports, doc comment `:3-18`, the effect `:28-48`)
- Modify: `frontend/src/app/ui/flash.spec.ts` (imports, the `beforeEach`, two new `describe` blocks)
- Modify: `frontend/src/app/ui/pnl-cell.spec.ts` (imports, the `beforeEach` at `:25`)

**Interfaces:**
- Consumes: MO4's `MotionService.mode` and `MotionStarts.record('flash', key)`, `provideMotion`; MO3's `.flash-up` / `.flash-down` (1.1s, scaled by `--motion-scale`, so 0s under Off).
- Produces: `Flash` injects `MotionService` and `MotionStarts`; when `motion.mode() === 'off'` it returns before touching the class list; otherwise, after adding the class, it records `MotionStarts.record('flash', 'flash')`. MO17's no-replay gate counts these (`'flash'` is an intended push reaction, never an entrance).

**Not in this task:** the two flash rules (never on first render, never on an unchanged value) and the remove/reflow/add restart stay exactly as they are. Under Reduced and pending the flash still plays (spec §1: the cell flash stays under Reduced; pending keeps `--motion-scale: 1`). The class names `flash-up` / `flash-down` do not change.

- [ ] **Step 1: Opt the two class-asserting specs into Motion = On**

The global test default is Off (`src/test-setup.ts`), under which the directive will add no class, so the existing class assertions must ask for On.

1. `frontend/src/app/ui/flash.spec.ts`: change the vitest import to `import { beforeEach, describe, expect, it } from 'vitest';` (unchanged if already so), add below `import { Flash } from './flash';`:

```ts
import { MotionStarts } from './motion/motion-starts';
import { provideMotion } from './motion/motion.service';
```

and change the `beforeEach` of `describe('Flash', ...)` to

```ts
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('on')] });
  });
```

2. `frontend/src/app/ui/pnl-cell.spec.ts`: add below `import { PnlCell } from './pnl-cell';`:

```ts
import { provideMotion } from './motion/motion.service';
```

and change its `TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });` to

```ts
    // The flash case below asserts the class; Motion = Off (the test
    // default) skips it by design (v168 §3 #8).
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('on')] });
```

- [ ] **Step 2: Write the failing cases**

Append to the end of `frontend/src/app/ui/flash.spec.ts`:

```ts
/* Spec v168 §3 #8: under Off --motion-scale is 0, so the flash would last 0s
 * and, with no animation running, animationend would never fire to remove the
 * class. The directive therefore adds nothing under Off. */
describe('Flash under Motion = Off', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('off')] });
  });

  it('adds no class when the value changes', () => {
    const { f, span } = setup();
    f.componentInstance.value.set(2);
    f.detectChanges();
    f.componentInstance.value.set(0);
    f.detectChanges();
    expect(span.className).toBe('');
    expect(TestBed.inject(MotionStarts).count('flash')).toBe(0);
  });
});

describe('Flash records its starts (v168 §4)', () => {
  it('records one flash per real change, none on first render or a repeat', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('on')] });
    const starts = TestBed.inject(MotionStarts);
    const { f } = setup();
    expect(starts.count('flash')).toBe(0);
    f.componentInstance.value.set(2);
    f.detectChanges();
    f.componentInstance.value.set(2);
    f.detectChanges();
    f.componentInstance.value.set(1);
    f.detectChanges();
    expect(starts.entries()).toEqual([
      { kind: 'flash', key: 'flash' },
      { kind: 'flash', key: 'flash' },
    ]);
  });

  it('still flashes under Reduced (the tint is colour, not movement)', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('reduced')] });
    const { f, span } = setup();
    f.componentInstance.value.set(2);
    f.detectChanges();
    expect(span.classList).toContain('flash-up');
  });
});
```

- [ ] **Step 3: Run them to verify they fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/flash.spec.ts --include src/app/ui/pnl-cell.spec.ts`
Expected: FAIL in `adds no class when the value changes` (the class is added) and `records one flash per real change` (no entries). The `describe('Flash', ...)` cases, the Reduced case and `pnl-cell.spec.ts` pass.

- [ ] **Step 4: Implement the guard and the record**

In `frontend/src/app/ui/flash.ts`:

1. Replace the import line with

```ts
import { Directive, effect, ElementRef, inject, input, untracked } from '@angular/core';

import { MotionStarts } from './motion/motion-starts';
import { MotionService } from './motion/motion.service';
```

2. Replace the doc comment (from `/**` through ` */` above `@Directive`) with

```ts
/**
 * Flash a cell when its value actually changed.
 *
 * Under real-time push a CARD flash on every event is a permanent flicker
 * rather than feedback, so v168 still forbids re-animating anything on a push
 * (styles/motion.css, spec v168 §4). What stays open is motion scoped to the
 * specific cell whose number moved, which is the useful half.
 *
 * Two rules make it feedback instead of noise:
 *   - never on first render (everything is new on arrival — that is a strobe)
 *   - never when a re-render reports the same value (a re-render is not a
 *     change, and Angular does plenty of them)
 *
 * The tint is --pos-soft / --neg-soft fading over 1.1s, with the text briefly
 * in --flash-up-text / --flash-down-text (styles/motion.css). Motion = Off
 * scales that duration to zero, and an animation that never runs never fires
 * animationend to take the class off again, so under Off this adds nothing.
 * Reduced keeps the flash: it is colour, not movement. Every flash it starts
 * is recorded in MotionStarts for the no-replay gate.
 */
```

3. In the class, add after `private readonly host = …;`:

```ts
  private readonly motion = inject(MotionService);
  private readonly starts = inject(MotionStarts);
```

4. In the effect, replace

```ts
      if (typeof next !== 'number' || typeof prior !== 'number') return;

      const cls = next > prior ? 'flash-up' : 'flash-down';
```

with

```ts
      if (typeof next !== 'number' || typeof prior !== 'number') return;
      // Read untracked: a mode change is not a value change and must not
      // re-run this effect.
      if (untracked(() => this.motion.mode()) === 'off') return;

      const cls = next > prior ? 'flash-up' : 'flash-down';
```

and after the `this.host.addEventListener('animationend', … { once: true });` statement (still inside the effect) add:

```ts
      this.starts.record('flash', 'flash');
```

- [ ] **Step 5: Confirm no other spec asserts a flash class**

Run: `git -C $WT grep -ln "flash-up\|flash-down" -- 'frontend/src/**/*.spec.ts'`
Expected: `frontend/src/app/ui/flash.spec.ts`, `frontend/src/app/ui/pnl-cell.spec.ts` and `frontend/src/app/ui/motion-css.spec.ts` (which reads CSS text, not classes). Any other file asserting the class on a rendered node needs `provideMotion('on')` in its providers the same way; add it, and name the file in the report and the commit body.

- [ ] **Step 6: Run the specs and the flash consumers**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/flash.spec.ts --include src/app/ui/pnl-cell.spec.ts --include src/app/shell/tape/tape.spec.ts --include 'src/app/workspaces/dashboard/**/*.spec.ts' --include 'src/app/workspaces/risk/**/*.spec.ts' --include 'src/app/workspaces/trades/**/*.spec.ts' --include 'src/app/workspaces/gallery/**/*.spec.ts' --include src/app/ui/motion-home.spec.ts`
Expected: `Tests  N passed (N)`, 0 failed. Then confirm the stale comment is gone: `git -C $WT grep -n "prefers-reduced-motion" -- frontend/src/app/ui/flash.ts` prints nothing. Quote the verdict line.

- [ ] **Step 7: Commit**

```bash
git -C $WT add frontend/src/app/ui/flash.ts frontend/src/app/ui/flash.spec.ts frontend/src/app/ui/pnl-cell.spec.ts
git -C $WT commit -m "feat(ui): v168 cell flash skips under Motion Off and records its start (MO14)

Under Off the flash's duration scales to 0, so animationend would never
fire to remove the class: the directive now adds nothing under Off (mode
read untracked). Reduced and pending keep the flash. Every flash started
is recorded as MotionStarts 'flash' for the no-replay gate. The doc
comment no longer leans on the deleted global reduced-motion block.
flash.spec and pnl-cell.spec opt into Motion = On for their class cases.

<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

