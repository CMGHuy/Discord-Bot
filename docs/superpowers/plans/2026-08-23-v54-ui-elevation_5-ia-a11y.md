# UI Elevation (v54) — Part 5: Navigation, accessibility, motion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Index:** `2026-08-23-v54-ui-elevation_0-index.md` — read its Global Constraints first.
**Spec:** `docs/superpowers/specs/2026-08-23-v54-ui-elevation-design.md` (decision D6)

**Goal:** Eight workspaces navigable at a glance; push updates announced once, not continuously; focus that goes somewhere sensible; and motion that fires only when a value actually changed.

**Runs after `_2` merges** (needs the `sb-async` host for `aria-busy`). **Parallel with `_4`.**

## Read this before Task 42

While writing this plan I measured the contrast pairs. **One already fails, and fixing it collides with a Global Constraint.** Task 42 surfaces the decision rather than resolving it silently — do not skip its Step 3.

---

### Task 38: Group the navigation

**Files:**
- Modify: `frontend/src/app/shell/shell.ts` (the `nav` array), `shell.html`, `shell.css`
- Test: `frontend/src/app/shell/shell.spec.ts` (extend or create)

**Interfaces:**
- Produces: `nav` becomes `NavGroup[]` where `interface NavGroup { label: string; entries: NavEntry[] }`.

A flat list of eight stops communicating. This is also the most severable item in the whole plan — if it is disliked, cutting it unravels nothing else.

- [ ] **Step 1: Write the failing test**

```ts
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { Shell } from './shell';

describe('shell navigation', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
  });

  it('groups the eight workspaces into three named groups', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const labels = [...el.querySelectorAll('.nav-group-label')].map((n) => n.textContent?.trim());
    expect(labels).toEqual(['MONITOR', 'REVIEW', 'SYSTEM']);
    expect(el.querySelectorAll('.nav a').length).toBe(8);
  });

  it('keeps each group a real list so the grouping reaches assistive tech', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const groups = (f.nativeElement as HTMLElement).querySelectorAll('ul[aria-labelledby]');
    expect(groups.length).toBe(3);
  });
});
```

- [ ] **Step 2: Run and watch it fail.**

- [ ] **Step 3: Restructure the `nav` array in `shell.ts`**

```ts
export interface NavEntry { path: string; label: string; icon: string }
export interface NavGroup { id: string; label: string; entries: NavEntry[] }

/**
 * Three groups, because eight flat entries stopped communicating.
 *
 * The split is by QUESTION, not by data type:
 *   MONITOR  what is happening right now
 *   REVIEW   what already happened
 *   SYSTEM   what the bot itself is doing
 *
 * The /ui gallery is deliberately absent — it is a developer surface,
 * reachable by URL.
 */
protected readonly navGroups: NavGroup[] = [
  {
    id: 'nav-monitor',
    label: 'MONITOR',
    entries: [
      { path: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
      { path: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
      { path: '/risk', label: 'Risk', icon: 'risk' },
    ],
  },
  {
    id: 'nav-review',
    label: 'REVIEW',
    entries: [
      { path: '/trades', label: 'Trades', icon: 'trades' },
      { path: '/calendar', label: 'Calendar', icon: 'calendar' },
      { path: '/analytics', label: 'Analytics', icon: 'analytics' },
    ],
  },
  {
    id: 'nav-system',
    label: 'SYSTEM',
    entries: [
      { path: '/system', label: 'System', icon: 'system' },
      { path: '/versions', label: 'Versions', icon: 'versions' },
    ],
  },
];
```

Copy the existing `path`, `label` and `icon` values from the current `nav` array rather than inventing them — the icon names must match `ui/icon.ts`'s registry or they render blank.

- [ ] **Step 4: Update `shell.html`**

```html
    @for (group of navGroups; track group.id) {
      <p class="nav-group-label" [id]="group.id">{{ group.label }}</p>
      <ul class="nav" [attr.aria-labelledby]="group.id">
        @for (entry of group.entries; track entry.path) {
          <li>
            … the existing <a> block, unchanged …
          </li>
        }
      </ul>
    }
```

- [ ] **Step 5: Style the label, and hide it on the rail**

In `shell.css`:

```css
/* The group label rides the same `.label` clip rule the nav entries use, so
   it disappears on the collapsed rail where 52px has no room for it and the
   icons already group visually by their gaps. */
.nav-group-label {
  padding: var(--space-8) var(--space-10) var(--space-4);
  color: var(--text-muted);
  font-size: var(--text-micro);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.railed .nav-group-label { display: none; }
```

- [ ] **Step 6: Check the rail and the phone overlay**

Run: `cd frontend && npm start`. Collapse the sidebar — the labels must vanish and the icons must not shift. Narrow below 640px — the overlay must still list all eight.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/shell
git commit -m "feat(v54): group the sidebar into MONITOR, REVIEW and SYSTEM"
```

---

### Task 39: One live region per workspace

**Files:**
- Modify: `frontend/src/app/ui/async.ts` (add the region)
- Test: `frontend/src/app/ui/async.spec.ts` (extend)

**Interfaces:**
- Consumes: `Async` from `_1` T10.
- Produces: `Async` gains `announce = input<string | null>(null)`.

`aria-live` currently appears in **one** file and `aria-busy` in two, in an app whose whole premise is pushed updates. But a live region **per cell** is worse than none: on a push-driven UI it produces continuous announcement that a screen-reader user cannot read through. One per workspace, `polite`, carrying a summary.

- [ ] **Step 1: Write the failing test**

```ts
it('exposes one polite live region for pushed updates', () => {
  const { el } = render();
  const region = el.querySelector('[aria-live]')!;
  expect(region.getAttribute('aria-live')).toBe('polite');
  expect(el.querySelectorAll('[aria-live]').length).toBe(1);
});

it('announces only what the caller gives it', () => {
  const f = TestBed.createComponent(Host);
  f.detectChanges();
  const host = f.debugElement.query((n) => n.name === 'sb-async');
  host.componentInstance.announce = '3 trades updated';
  f.detectChanges();
  expect((f.nativeElement as HTMLElement).querySelector('[aria-live]')!.textContent)
    .toContain('3 trades updated');
});
```

(Adjust the second test to however the host component exposes the input — `componentRef.setInput` on a directly-created `Async` fixture is simpler if the wrapper makes this awkward.)

- [ ] **Step 2: Run, watch it fail, implement**

Add to `async.ts`'s template, as the first child:

```html
    <!-- One region per sb-async, and therefore one per fetch-backed surface.
         Per-CELL live regions on a push-driven UI announce continuously,
         which is unusable — worse than silence. The caller supplies a
         summary ("3 trades updated"), not a running commentary. -->
    <span class="sr-only" aria-live="polite" aria-atomic="true">{{ announce() }}</span>
```

Add the input and a visually-hidden class:

```ts
  /** A short summary of what just changed, or null. Announced politely. */
  readonly announce = input<string | null>(null);
```

```css
    .sr-only {
      position: absolute;
      width: 1px; height: 1px;
      margin: -1px; padding: 0;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }
```

- [ ] **Step 3: Bind it in the workspaces that push**

Dashboard, trades, watchlist and risk receive pushed updates. Bind `[announce]` to a computed summary in each — e.g. `` `${store.updatedCount()} positions updated` ``. Leave it null where nothing pushes; a live region that never changes is harmless, one that announces noise is not.

- [ ] **Step 4: Run and commit**

```bash
git add frontend/src/app
git commit -m "feat(v54): one polite live region per fetch-backed surface"
```

---

### Task 40: Focus goes somewhere on navigation

**Files:**
- Create: `frontend/src/app/shell/route-focus.ts`
- Modify: `frontend/src/app/app.ts` or `shell.ts` (wire it)
- Test: `frontend/src/app/shell/route-focus.spec.ts`

**Interfaces:**
- Produces: `provideRouteFocus()` — call it in `app.config.ts`.

In an SPA, a route change moves nothing for a keyboard or screen-reader user: focus stays on the nav link they just activated, and the new page is never announced.

- [ ] **Step 1: Write the failing test**

```ts
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { describe, expect, it } from 'vitest';

import { focusWorkspaceHeading } from './route-focus';

describe('focusWorkspaceHeading', () => {
  it('moves focus to the workspace heading', () => {
    document.body.innerHTML = '<main class="workspace"><h1>Trades</h1></main>';
    focusWorkspaceHeading(document);
    expect(document.activeElement?.tagName).toBe('H1');
  });

  it('makes the heading programmatically focusable without adding a tab stop', () => {
    document.body.innerHTML = '<main class="workspace"><h1>Trades</h1></main>';
    focusWorkspaceHeading(document);
    expect(document.querySelector('h1')!.getAttribute('tabindex')).toBe('-1');
  });

  it('does nothing when the workspace has no heading yet', () => {
    document.body.innerHTML = '<main class="workspace"></main>';
    expect(() => focusWorkspaceHeading(document)).not.toThrow();
  });
});
```

- [ ] **Step 2: Run, watch it fail, implement**

```ts
/**
 * Move focus to the new workspace's heading after a route change.
 *
 * In an SPA nothing moves focus on navigation: it stays on the nav link that
 * was just activated, so a screen-reader user is told nothing about the page
 * that replaced the one they were on, and a keyboard user's next Tab
 * continues through the sidebar rather than into the content.
 *
 * `tabindex="-1"` makes the heading focusable programmatically WITHOUT
 * putting it in the tab order — a heading that became a tab stop would be a
 * new obstacle on every page.
 */
export function focusWorkspaceHeading(doc: Document): void {
  const heading = doc.querySelector<HTMLElement>('.workspace h1');
  if (!heading) return;
  heading.setAttribute('tabindex', '-1');
  heading.focus({ preventScroll: true });
}
```

Wire it to the router's `NavigationEnd`, after the view has rendered (an `afterNextRender` or a microtask — the heading does not exist at `NavigationEnd` itself). If focus lands on nothing, that is the bug to fix, not a reason to drop the feature.

- [ ] **Step 3: Verify by keyboard**

Run: `cd frontend && npm start`. Tab to a nav link, press Enter, then press Tab again — the next stop must be inside the content, not the next nav link.

- [ ] **Step 4: Commit** `feat(v54): move focus to the workspace heading on navigation`.

---

### Task 41: Focus trap and restore in drawer and dialog

**Files:**
- Modify: `frontend/src/app/ui/layout.ts` (`sb-drawer`), `ui/confirm-dialog.ts`
- Test: `frontend/src/app/ui/focus-trap.spec.ts`

**Interfaces:**
- Produces: a `sbFocusTrap` directive in `ui/focus-trap.ts`, applied by both.

- [ ] **Step 1: Write the failing test** — cover three behaviours: focus moves into the panel on open; Tab from the last focusable wraps to the first; focus returns to the invoking element on close.

```ts
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { FocusTrap } from './focus-trap';

@Component({
  imports: [FocusTrap],
  template: `
    <button id="opener" (click)="open.set(true)">Open</button>
    @if (open()) {
      <div sbFocusTrap>
        <button id="first">First</button>
        <button id="last">Last</button>
      </div>
    }
  `,
})
class Host { open = signal(false); }

describe('FocusTrap', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('moves focus into the panel when it opens', () => {
    const f = TestBed.createComponent(Host);
    f.detectChanges();
    f.componentInstance.open.set(true);
    f.detectChanges();
    expect(document.activeElement?.id).toBe('first');
  });

  it('returns focus to whatever opened it', () => {
    const f = TestBed.createComponent(Host);
    f.detectChanges();
    document.getElementById('opener')!.focus();
    f.componentInstance.open.set(true);
    f.detectChanges();
    f.componentInstance.open.set(false);
    f.detectChanges();
    expect(document.activeElement?.id).toBe('opener');
  });
});
```

- [ ] **Step 2: Run, watch it fail, implement the directive**, then apply `sbFocusTrap` to the drawer panel and the dialog panel. Escape must close both — check whether they already handle it before adding a second handler.

- [ ] **Step 3: Verify by keyboard in `/ui`**, then commit `feat(v54): trap and restore focus in drawer and dialog`.

---

### Task 42: The contrast audit — and a decision the plan cannot make

**Gate:** G5.

**Files:**
- Create: `frontend/src/app/ui/contrast.spec.ts`
- Possibly modify: `frontend/src/styles/tokens.css`

- [ ] **Step 1: Write the audit**

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

function token(name: string): string {
  return CSS.match(new RegExp(`^\\s*${name}:\\s*(#[0-9a-fA-F]{6});`, 'm'))![1];
}

/** WCAG 2.1 relative luminance. */
function luminance(hex: string): number {
  const ch = (i: number) => {
    const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * ch(0) + 0.7152 * ch(1) + 0.0722 * ch(2);
}

function ratio(fg: string, bg: string): number {
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

const SURFACES = ['--bg', '--surface', '--surface-raised', '--surface-overlay'];

/**
 * Tokens that are NOT text and are exempt.
 *
 * `--text-faint` measures ~2.3:1 on --surface. It is a RULE AND DIVIDER
 * colour, never text that must be read — that is decision D6's binding rule,
 * and `no-text-uses-text-faint` below is what enforces it.
 */
const NON_TEXT = new Set(['--text-faint']);

describe('WCAG AA on every text/surface pair', () => {
  for (const fg of ['--text', '--text-secondary', '--text-muted']) {
    for (const bg of SURFACES) {
      it(`${fg} on ${bg} clears 4.5:1`, () => {
        expect(ratio(token(fg), token(bg))).toBeGreaterThanOrEqual(4.5);
      });
    }
  }

  for (const name of NON_TEXT) {
    it(`${name} is documented as non-text`, () => {
      expect(CSS).toMatch(new RegExp(`${name}[\\s\\S]{0,400}?rule and divider`, 'i'));
    });
  }
});
```

- [ ] **Step 2: Run it. Expect a failure — this is a real finding, not a bug in the test.**

Run: `cd frontend && npm test -- --include src/app/ui/contrast.spec.ts`

Measured while writing this plan:

| Pair | Ratio | AA 4.5:1 |
|---|---|---|
| `--text` on `--surface` | ~15.9 | pass |
| `--text-secondary` on `--surface` | ~8.3 | pass |
| **`--text-muted` on `--surface`** | **~4.14** | **FAIL** |
| `--text-faint` on `--surface` | ~2.25 | non-text |

- [ ] **Step 3: STOP. Surface the decision — do not resolve it in this task.**

`--text-muted` fails AA, and every way out collides with something:

| Option | Cost |
|---|---|
| **Lighten `--text-muted`** (≈`#7b83a0` clears 4.5:1) | Violates the Global Constraint *"no existing token changes value"* — the constraint the whole no-silent-breakage argument rests on. It is also used in ~30 places, all of which shift slightly. |
| Exempt it as "large text" | Does not apply. It is used at `--text-micro` (11px); AA's 3:1 large-text allowance needs 24px, or 18.66px bold. |
| Exempt it as non-text | False. It carries readable labels, including the new nav group labels in Task 38. |
| Lower the gate to 3:1 | Loosens an acceptance gate. Not available — CLAUDE.md is explicit that a profit or convenience motive never moves a threshold. |

**Recommendation: lighten `--text-muted` to `#7b83a0` and record it as the one deliberate exception to the no-token-churn constraint,** amending the spec's Non-goals section in the same commit. The constraint exists to prevent *silent* breakage; a documented, tested, single-token change with a measured reason is the opposite of silent. The alternative is shipping a UI whose secondary labels are unreadable, in a plan whose stated purpose is legibility.

**Ask the human partner before proceeding.** This is a spec amendment, not an implementation detail.

- [ ] **Step 4: Once decided, implement, run, and commit** with the decision in the message.

---

### Task 43: `[sbFlash]` — motion that means something

**Files:**
- Create: `frontend/src/app/ui/flash.ts`
- Test: `frontend/src/app/ui/flash.spec.ts`

**Interfaces:**
- Produces: `<td [sbFlash]="row.pnl">` — flashes only when the bound value changes.

`tokens.css` already rules out a card-level flash on every push ("a permanent flicker"). This implements the part it left open: motion scoped to the cell whose value actually changed, which is feedback rather than noise.

- [ ] **Step 1: Write the failing test**

```ts
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Flash } from './flash';

@Component({
  imports: [Flash],
  template: `<span [sbFlash]="value()">{{ value() }}</span>`,
})
class Host { value = signal(1); }

function setup() {
  const f = TestBed.createComponent(Host);
  f.detectChanges();
  return { f, span: (f.nativeElement as HTMLElement).querySelector('span')! };
}

describe('Flash', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('does not flash on first render', () => {
    // Everything is "new" on arrival; flashing every cell would be a
    // full-screen strobe on load.
    expect(setup().span.classList.contains('flash-up')).toBe(false);
  });

  it('flashes up when the value rises', () => {
    const { f, span } = setup();
    f.componentInstance.value.set(2);
    f.detectChanges();
    expect(span.classList.contains('flash-up')).toBe(true);
  });

  it('flashes down when the value falls', () => {
    const { f, span } = setup();
    f.componentInstance.value.set(0);
    f.detectChanges();
    expect(span.classList.contains('flash-down')).toBe(true);
  });

  it('does not flash when a re-render reports the same value', () => {
    const { f, span } = setup();
    f.componentInstance.value.set(1);
    f.detectChanges();
    expect(span.className).toBe('');
  });
});
```

- [ ] **Step 2: Run, watch it fail, implement**

```ts
import { Directive, effect, ElementRef, inject, input } from '@angular/core';

/**
 * Flash a cell when its value actually changed.
 *
 * `tokens.css` already rules out the thing this must not become: a CARD flash
 * on every push event, which under real-time updates is a permanent flicker
 * rather than feedback. What it left open is motion scoped to the specific
 * cell whose number moved, which is the useful half.
 *
 * Two rules make it feedback instead of noise:
 *   - never on first render (everything is new on arrival — that is a strobe)
 *   - never when a re-render reports the same value (a re-render is not a
 *     change, and Angular does plenty of them)
 *
 * The colours are --pos-soft / --neg-soft, and `prefers-reduced-motion`
 * already zeroes the durations globally, so this needs no separate guard.
 */
@Directive({ selector: '[sbFlash]' })
export class Flash {
  readonly sbFlash = input.required<number | null | undefined>();

  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  private previous: number | null | undefined;
  private seen = false;

  constructor() {
    effect(() => {
      const next = this.sbFlash();
      const prior = this.previous;
      this.previous = next;

      if (!this.seen) { this.seen = true; return; }
      if (next === prior) return;
      if (typeof next !== 'number' || typeof prior !== 'number') return;

      const cls = next > prior ? 'flash-up' : 'flash-down';
      this.host.classList.remove('flash-up', 'flash-down');
      // Force a reflow so a second change within the animation restarts it
      // rather than being swallowed.
      void this.host.offsetWidth;
      this.host.classList.add(cls);
      this.host.addEventListener(
        'animationend',
        () => this.host.classList.remove(cls),
        { once: true },
      );
    });
  }
}
```

Add the keyframes to `styles.css`:

```css
/* Cell-level value feedback. Scoped to the cell, never the card — see
   tokens.css on why a card flash under real-time push is a flicker. */
@keyframes flash-up { from { background: var(--pos-soft); } to { background: transparent; } }
@keyframes flash-down { from { background: var(--neg-soft); } to { background: transparent; } }
.flash-up { animation: flash-up var(--dur-base) var(--ease-out); }
.flash-down { animation: flash-down var(--dur-base) var(--ease-out); }
```

- [ ] **Step 3: Apply it** to the live P&L, price and R columns on dashboard, trades and risk. **Not** to a whole row and **not** to a card.

- [ ] **Step 4: Watch it during a live session** with the market open, or by replaying events. If the screen looks busy, the directive is on too many columns — cut columns, not the duration.

- [ ] **Step 5: Commit** `feat(v54): flash a cell only when its value actually changed`.

---

### Task 44: Gallery, gates and wave close-out

**Files:** Modify `frontend/src/app/workspaces/gallery/gallery.ts`.

- [ ] Add an **Accessibility and motion** section: a `[sbFlash]` demo with a button that changes the value, the live-region behaviour, and a focus-trap demo in a drawer.
- [ ] Run `cd frontend && npm test` → green, including `gallery.spec.ts` (G8).
- [ ] Run `python scripts/dev/testrun.py full` → `1686 passed, 66 skipped, 0 failed`. (G10)
- [ ] Keyboard-only pass over all eight workspaces: Tab from the top, confirm every control is reachable, the focus ring is visible on `--surface` and `--surface-overlay`, and no trap exists outside drawer and dialog.
- [ ] Commit `docs(v54): show a11y and motion in the gallery`.

## Wave 5 done when

- [ ] Nav shows three groups and eight entries; labels hide on the rail.
- [ ] One `aria-live="polite"` region per fetch-backed surface — **not** one per cell.
- [ ] Focus lands in the content after navigation; Tab continues into the page.
- [ ] Drawer and dialog trap focus and restore it to the invoking element.
- [ ] Contrast: every text pair clears 4.5:1 **or** the `--text-muted` decision from Task 42 has been taken by the human partner and recorded in the spec.
- [ ] `--text-faint` used for no readable text anywhere.
- [ ] Cells flash only on a real change, never on first render, never a whole card.
- [ ] Python suite unchanged.

## Plan close-out (after this wave merges)

1. `git mv` the six plan files and the spec into `implemented/`.
2. Bump `VERSION.json`'s `ui` line (minor); leave `bot` alone.
3. `git worktree remove` the `2026-08-23-v54-ui-elevation` worktree, then `git branch -d` its branch — `-d`, never `-D`.
4. Regenerate `version_history`.
