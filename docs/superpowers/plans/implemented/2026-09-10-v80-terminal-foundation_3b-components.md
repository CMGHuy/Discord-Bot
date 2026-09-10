# v80 — Terminal foundation, part 3b: canonical components (F17–F20)

Part of `2026-09-10-v80-terminal-foundation_0-index.md`. Read its Global
Constraints and the v77 precondition before starting any task here.

# Phase 2 — Canonical components (continued)

## Parallelisation

- **Group A (parallel, after F3), continued.** F17–F20 run alongside F4–F16
  (parts 2a, 2b, 3a). Every task here creates two new files and touches
  nothing else:

  | Task | Files |
  |---|---|
  | F17 | new `panel-grid.ts`, new `panel-grid.spec.ts` |
  | F18 | new `status.ts`, new `status.spec.ts` |
  | F19 | new `hint.ts`, new `hint.spec.ts` |
  | F20 | new `pnl-cell.ts`, new `pnl-cell.spec.ts` |

- **No contract dependency.**
  - F20 consumes `Flash`, `pct` and `money`, and F18 consumes `ABSENT`; no
    Group A task changes any of them.
  - F19 consumes the global `.elev-overlay` class, which no task changes.
- **Known interim red:** each task adds an `sb-` selector that
  `gallery.spec.ts` expects in the gallery. Those cases stay red until F25.

---

### Task F17: `sb-panel-grid`, two track widths

**Files:**
- Create: `frontend/src/app/ui/panel-grid.ts`
- Create: `frontend/src/app/ui/panel-grid.spec.ts`

**Interfaces:**
- Consumes: `--space-14` (existing).
- Produces:
  - `PanelGrid` (`selector: 'sb-panel-grid'`) with `track = input<PanelTrack>('narrow')`;
  - `PanelTrack = 'narrow' | 'wide'` (220px and 320px);
  - the track is set as a host class.

  F25 renders both tracks.

**Why a viewport query against D3's "container queries".** `container-type`
on this host would make its width independent of its content, and a grid that
is itself a flex item collapses to nothing. Like F7's `sb-control-row`, this
uses `breakpoints.ts`'s 640 floor via `@media`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/panel-grid.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Panel } from './layout';
import { PanelGrid, PanelTrack } from './panel-grid';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/panel-grid.ts'), 'utf8');

@Component({
  imports: [PanelGrid, Panel],
  template: `
    <sb-panel-grid [track]="track">
      <sb-panel heading="One" />
      <sb-panel heading="Two" />
      <sb-panel heading="Three" />
    </sb-panel-grid>
  `,
})
class Host {
  track: PanelTrack = 'narrow';
}

function render(track?: PanelTrack): HTMLElement {
  const f = TestBed.createComponent(Host);
  if (track) f.componentInstance.track = track;
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('sb-panel-grid') as HTMLElement;
}

describe('PanelGrid (v80 D4)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('defaults to the narrow track', () => {
    expect(render().classList).toContain('narrow');
  });

  it('takes the wide track when asked', () => {
    const grid = render('wide');
    expect(grid.classList).toContain('wide');
    expect(grid.classList).not.toContain('narrow');
  });

  it('lays its panels out as grid items, directly', () => {
    const grid = render();
    expect(getComputedStyle(grid).display).toBe('grid');
    expect([...grid.children].map((c) => c.tagName.toLowerCase())).toEqual(['sb-panel', 'sb-panel', 'sb-panel']);
  });

  it('offers exactly two track widths, 220px and 320px', () => {
    const widths = [...SOURCE.matchAll(/minmax\(min\((\d+)px, 100%\), 1fr\)/g)].map(([, px]) => px);
    expect(widths).toEqual(['220', '320']);
  });

  it('collapses to one column below 640px', () => {
    expect(SOURCE).toMatch(
      /@media \(max-width: 639px\) \{\s*:host, :host\(\.wide\) \{ grid-template-columns: minmax\(0, 1fr\); \}/,
    );
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/panel-grid.spec.ts')`

Expected: FAIL. `./panel-grid` does not exist.

- [ ] **Step 3: Implement**

Create `frontend/src/app/ui/panel-grid.ts`:

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** The two track widths a panel grid may use. */
export type PanelTrack = 'narrow' | 'wide';

/**
 * A responsive grid of panels -- spec v80 D4.
 *
 * Six screens hand-picked six minimum widths between 140px and 300px, which is
 * why no two grids of panels line up. There are two now: `narrow` (220px, a
 * figure or a short list) and `wide` (320px, a table or a chart). Tracks fill
 * the row and wrap. `min(…, 100%)` stops one track forcing a scrollbar in a
 * box narrower than the track itself.
 *
 * One column below 640px. A viewport query, not a container query, because
 * `container-type` on this host would make its width independent of its
 * content, and a grid that is itself a flex item would collapse to nothing.
 */
@Component({
  selector: 'sb-panel-grid',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[class]': 'track()' },
  template: `<ng-content />`,
  styles: `
    :host {
      display: grid;
      gap: var(--space-14);
      grid-template-columns: repeat(auto-fill, minmax(min(220px, 100%), 1fr));
    }
    :host(.wide) { grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr)); }
    /* 640 is breakpoints.ts's sm floor, repeated as a literal because @media
       cannot evaluate var(). */
    @media (max-width: 639px) {
      :host, :host(.wide) { grid-template-columns: minmax(0, 1fr); }
    }
  `,
})
export class PanelGrid {
  readonly track = input<PanelTrack>('narrow');
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/panel-grid.spec.ts')`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/panel-grid.ts frontend/src/app/ui/panel-grid.spec.ts
git commit -m "feat(v80): sb-panel-grid with two track widths, one column on a phone"
```

---

### Task F18: `sb-status`, state carried by shape

**Files:**
- Create: `frontend/src/app/ui/status.ts`
- Create: `frontend/src/app/ui/status.spec.ts`

**Interfaces:**
- Consumes: `ABSENT` from `format.ts`.
- Produces: `Status` (`selector: 'sb-status'`) and
  `StatusShape = 'pending' | 'active' | 'partial' | 'closed' | 'unknown'`. Inputs:
  - `status = input.required<string | null>()`, the API spelling, case-insensitive;
  - `label = input<string | null>(null)`, which overrides the sentence-case word.

  F25 renders all four states.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/status.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Status } from './status';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/status.ts'), 'utf8');

function render(status: string | null, label: string | null = null): HTMLElement {
  const f = TestBed.createComponent(Status);
  f.componentRef.setInput('status', status);
  f.componentRef.setInput('label', label);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

const text = (el: HTMLElement) => el.textContent!.replace(/\s+/g, ' ').trim();

describe('Status (v80 D4)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  for (const [status, shape, word] of [
    ['PENDING', 'pending', 'Pending'],
    ['ACTIVE', 'active', 'Active'],
    ['PARTIAL', 'partial', 'Partial'],
    ['CLOSED', 'closed', 'Closed'],
  ]) {
    it(`draws ${status} as the ${shape} marker beside the word "${word}"`, () => {
      const el = render(status);
      expect(el.querySelector('.status')!.classList).toContain(shape);
      expect(el.querySelector('.marker')).not.toBeNull();
      expect(text(el)).toBe(word);
    });
  }

  it('reads the status case-insensitively', () => {
    expect(render('partial').querySelector('.status')!.classList).toContain('partial');
  });

  it('names itself by the word; the marker is hidden from assistive tech', () => {
    const el = render('ACTIVE');
    const marker = el.querySelector('.marker')!;
    expect(marker.getAttribute('aria-hidden')).toBe('true');
    expect(marker.textContent).toBe('');
    expect(el.querySelector('.word')!.textContent!.trim()).toBe('Active');
  });

  it('lets a caller rename the word without changing the shape', () => {
    const el = render('ACTIVE', 'Open');
    expect(text(el)).toBe('Open');
    expect(el.querySelector('.status')!.classList).toContain('active');
  });

  it('draws no marker for a status it has no shape for', () => {
    const el = render('EXPIRED');
    expect(el.querySelector('.marker')).toBeNull();
    expect(el.querySelector('.status')!.classList).toContain('unknown');
    expect(text(el)).toBe('Expired');
  });

  it('is an em dash when there is no status', () => {
    expect(text(render(null))).toBe('—');
  });

  it('tells the states apart by fill and shape, not by hue', () => {
    expect(SOURCE).toMatch(/\.pending \.marker \{ background: transparent; \}/);
    expect(SOURCE).toMatch(/\.active \.marker \{ background: currentColor; \}/);
    expect(SOURCE).toMatch(/\.partial \.marker \{ background: linear-gradient\(to right, currentColor 50%, transparent 50%\); \}/);
    expect(SOURCE).toMatch(/\.closed \.marker \{[^}]*border-radius: 1px/);
  });

  it('never uses the gain or loss colour: a status is not an outcome', () => {
    expect(SOURCE).not.toContain('--pos');
    expect(SOURCE).not.toContain('--neg');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/status.spec.ts')`

Expected: FAIL. `./status` does not exist.

- [ ] **Step 3: Implement**

Create `frontend/src/app/ui/status.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { ABSENT } from './format';

/** The four trade states a marker can draw, plus the case it cannot. */
export type StatusShape = 'pending' | 'active' | 'partial' | 'closed' | 'unknown';

const SHAPES: Record<string, StatusShape> = {
  PENDING: 'pending',
  ACTIVE: 'active',
  PARTIAL: 'partial',
  CLOSED: 'closed',
};

/**
 * A trade's status as a marker and a word -- spec v80 D4.
 *
 * The marker's SHAPE carries the state, so the column reads without colour:
 *  - pending: an outline ring (nothing has filled);
 *  - active: a filled disc;
 *  - partial: a half-filled disc (half the position banked);
 *  - closed: a small muted square (done, and a shape no open state uses).
 *
 * The word is always there and is the accessible name. The marker is
 * aria-hidden: announcing "filled circle" adds nothing the word does not say.
 *
 * Text tokens only. Green and red mean P&L, and a status is not an outcome.
 */
@Component({
  selector: 'sb-status',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="status" [class]="shape()">
      @if (shape() !== 'unknown') {
        <span class="marker" aria-hidden="true"></span>
      }
      <span class="word">{{ word() }}</span>
    </span>
  `,
  styles: `
    .status {
      display: inline-flex;
      align-items: center;
      gap: var(--space-6);
      color: var(--text);
      font-size: var(--text-table);
      white-space: nowrap;
    }
    .marker {
      flex: 0 0 auto;
      box-sizing: border-box;
      width: 8px;
      height: 8px;
      border: 1.5px solid currentColor;
      border-radius: 50%;
    }
    .pending .marker { background: transparent; }
    .active .marker { background: currentColor; }
    .partial .marker { background: linear-gradient(to right, currentColor 50%, transparent 50%); }
    .closed { color: var(--text-muted); }
    .closed .marker { width: 7px; height: 7px; border-radius: 1px; background: currentColor; }
    .unknown { color: var(--text-muted); }
  `,
})
export class Status {
  /** A plan or trade status as the API spells it: PENDING, ACTIVE, PARTIAL,
   *  CLOSED. Case-insensitive. */
  readonly status = input.required<string | null>();
  /** Replaces the default word, which is the status in sentence case. */
  readonly label = input<string | null>(null);

  protected readonly shape = computed<StatusShape>(
    () => SHAPES[(this.status() ?? '').trim().toUpperCase()] ?? 'unknown',
  );

  protected readonly word = computed(() => {
    const label = this.label();
    if (label) return label;
    const raw = (this.status() ?? '').trim();
    return raw ? raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase() : ABSENT;
  });
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/status.spec.ts')`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/status.ts frontend/src/app/ui/status.spec.ts
git commit -m "feat(v80): sb-status -- trade state carried by marker shape, named by its word"
```

---

### Task F19: `sb-hint`, an info popover for hover, focus and tap

**Files:**
- Create: `frontend/src/app/ui/hint.ts`
- Create: `frontend/src/app/ui/hint.spec.ts`

**Interfaces:**
- Consumes: the global `.elev-overlay` class (L3 surface, strong border, the
  one shadow); `--control-h` (F3).
- Produces: `Hint` (`selector: 'sb-hint'`) with inputs
  `text = input.required<string>()` and `label = input('More information')`
  (the trigger's accessible name). No outputs. Phone screens adopts it; F25
  renders it.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/hint.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Hint } from './hint';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/hint.ts'), 'utf8');

@Component({
  imports: [Hint],
  template: `
    <div>
      <span class="outside">Expectancy</span>
      <sb-hint text="Average R per closed trade, after costs." label="About expectancy" />
    </div>
  `,
})
class Host {}

describe('Hint (v80 D4)', () => {
  let fixture: ComponentFixture<Host>;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const hint = () => el().querySelector('sb-hint') as HTMLElement;
  const trigger = () => el().querySelector('sb-hint button') as HTMLButtonElement;
  const pop = () => el().querySelector('sb-hint [role=tooltip]') as HTMLElement;
  const fire = (target: Element, event: Event) => {
    target.dispatchEvent(event);
    fixture.detectChanges();
  };
  const isOpen = () => !pop().hidden;

  it('is closed at rest, and already describes its trigger', () => {
    expect(isOpen()).toBe(false);
    expect(trigger().getAttribute('aria-expanded')).toBe('false');
    expect(trigger().getAttribute('aria-label')).toBe('About expectancy');
    expect(trigger().getAttribute('aria-describedby')).toBe(pop().id);
    expect(pop().textContent!.trim()).toBe('Average R per closed trade, after costs.');
  });

  it('opens on hover and closes when the pointer leaves', () => {
    fire(hint(), new MouseEvent('mouseenter'));
    expect(isOpen()).toBe(true);
    expect(trigger().getAttribute('aria-expanded')).toBe('true');
    fire(hint(), new MouseEvent('mouseleave'));
    expect(isOpen()).toBe(false);
  });

  it('opens on keyboard focus and closes when focus leaves', () => {
    fire(trigger(), new FocusEvent('focusin', { bubbles: true }));
    expect(isOpen()).toBe(true);
    fire(trigger(), new FocusEvent('focusout', { bubbles: true, relatedTarget: null }));
    expect(isOpen()).toBe(false);
  });

  it('stays open after a tap, past the emulated hover ending, until tapped again', () => {
    // A phone tap fires mouseenter and focus before the click.
    fire(hint(), new MouseEvent('mouseenter'));
    fire(trigger(), new FocusEvent('focusin', { bubbles: true }));
    fire(trigger(), new MouseEvent('click', { bubbles: true }));
    expect(isOpen()).toBe(true);
    fire(hint(), new MouseEvent('mouseleave'));
    expect(isOpen()).toBe(true);
    fire(trigger(), new MouseEvent('click', { bubbles: true }));
    expect(isOpen()).toBe(false);
  });

  it('closes on Escape however it was opened', () => {
    fire(trigger(), new MouseEvent('click', { bubbles: true }));
    expect(isOpen()).toBe(true);
    fire(trigger(), new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(isOpen()).toBe(false);
  });

  it('closes on a tap outside, and not on a tap inside the popover', () => {
    fire(trigger(), new MouseEvent('click', { bubbles: true }));
    fire(pop(), new MouseEvent('pointerdown', { bubbles: true }));
    expect(isOpen()).toBe(true);
    fire(el().querySelector('.outside')!, new MouseEvent('pointerdown', { bubbles: true }));
    expect(isOpen()).toBe(false);
  });

  it('floats as an overlay, the one surface allowed a shadow', () => {
    expect(pop().classList).toContain('elev-overlay');
  });

  it('gives the trigger a 44px target on touch and narrow screens', () => {
    const block = SOURCE.match(/@media \(pointer: coarse\), \(max-width: 639px\) \{([\s\S]*?)\n    \}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain('min-width: var(--control-h)');
    expect(block![1]).toContain('min-height: var(--control-h)');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/hint.spec.ts')`

Expected: FAIL. `./hint` does not exist.

- [ ] **Step 3: Implement**

Create `frontend/src/app/ui/hint.ts`:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';

let nextId = 0;

/**
 * An info popover -- spec v80 D4.
 *
 * Thirty-five `title` tooltips carry real explanation today, and a `title`
 * opens only on mouse hover: a phone never shows it and a keyboard user never
 * reaches it. This opens on hover, on keyboard focus and on tap, and closes on
 * Escape or a tap anywhere else. Phone screens adopts it.
 *
 * Three reasons to be open, kept separate so one ending cannot close a hint
 * another still holds. Hover and focus hold it only while they last. A click
 * PINS it; a click on a pinned hint closes it. The order matters on a phone:
 * a tap fires an emulated mouseenter and a focus BEFORE its click, so a plain
 * toggle would open on the hover and close again on the click.
 *
 * The trigger is a real button with `aria-expanded`, and the popover is
 * `role="tooltip"` referenced by `aria-describedby`, so a screen reader reads
 * the text on focus without opening anything.
 */
@Component({
  selector: 'sb-hint',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '(mouseenter)': 'hovered.set(true)',
    '(mouseleave)': 'hovered.set(false)',
    '(focusin)': 'focused.set(true)',
    '(focusout)': 'onFocusOut($event)',
    '(keydown.escape)': 'close()',
    '(document:pointerdown)': 'onDocumentPointer($event)',
  },
  template: `
    <button
      type="button"
      class="trigger"
      [attr.aria-label]="label()"
      [attr.aria-expanded]="open()"
      [attr.aria-describedby]="id"
      (click)="toggle()"
    >
      <span class="glyph" aria-hidden="true">i</span>
    </button>
    <span class="pop elev-overlay" role="tooltip" [id]="id" [hidden]="!open()">{{ text() }}</span>
  `,
  styles: `
    :host { position: relative; display: inline-flex; vertical-align: middle; }
    .trigger {
      display: inline-grid;
      place-items: center;
      padding: 0;
      background: none;
      border: 0;
      color: var(--text-muted);
      cursor: help;
    }
    .trigger:hover, .trigger[aria-expanded='true'] { color: var(--text); }
    .trigger:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    .glyph {
      display: inline-grid;
      place-items: center;
      width: 14px;
      height: 14px;
      border: 1px solid currentColor;
      border-radius: 50%;
      font-family: var(--font-mono);
      font-size: var(--text-micro);
      line-height: 1;
    }
    .pop {
      position: absolute;
      top: calc(100% + var(--space-4));
      left: 50%;
      z-index: 20;
      width: max-content;
      max-width: min(280px, 90vw);
      padding: var(--space-8) var(--space-10);
      transform: translateX(-50%);
      color: var(--text);
      font-size: var(--text-chip);
      line-height: 1.5;
      text-align: left;
      white-space: normal;
    }
    /* A fingertip needs 44px around a 14px glyph (v80 D4). */
    @media (pointer: coarse), (max-width: 639px) {
      .trigger { min-width: var(--control-h); min-height: var(--control-h); }
    }
  `,
})
export class Hint {
  readonly text = input.required<string>();
  /** The trigger's accessible name. Name what it explains: "About expectancy". */
  readonly label = input('More information');

  protected readonly id = `sb-hint-${nextId++}`;
  protected readonly pinned = signal(false);
  protected readonly hovered = signal(false);
  protected readonly focused = signal(false);
  protected readonly open = computed(() => this.pinned() || this.hovered() || this.focused());

  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;

  protected toggle(): void {
    if (this.pinned()) this.close();
    else this.pinned.set(true);
  }

  protected close(): void {
    this.pinned.set(false);
    this.hovered.set(false);
    this.focused.set(false);
  }

  /** Focus moving between the trigger and anything inside the popover is not
   *  focus leaving the hint. */
  protected onFocusOut(event: FocusEvent): void {
    const next = event.relatedTarget as Node | null;
    if (!next || !this.host.contains(next)) this.focused.set(false);
  }

  protected onDocumentPointer(event: Event): void {
    if (!this.host.contains(event.target as Node)) this.close();
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/hint.spec.ts')`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/hint.ts frontend/src/app/ui/hint.spec.ts
git commit -m "feat(v80): sb-hint -- info popover that opens on hover, focus or tap"
```

---

### Task F20: `sb-pnl-cell`, percent and amount in one cell

**Files:**
- Create: `frontend/src/app/ui/pnl-cell.ts`
- Create: `frontend/src/app/ui/pnl-cell.spec.ts`

**Interfaces:**
- Consumes: `Flash` (`ui/flash.ts`); `ABSENT`, `pct`, `money` (`ui/format.ts`);
  the global `.pos`/`.neg` classes.
- Produces: `PnlCell` (`selector: 'sb-pnl-cell'`) with inputs:
  - `pct = input.required<number | null>()`;
  - `amount = input<number | null>(null)`;
  - `currency = input.required<string>()`.

  It renders `+4.20% (+9.80 €)`, coloured by the sign of `pct` and flashing
  when `pct` changes. F25's cell-contract row renders it, and Migration moves
  `trades.ts:327` and `dashboard.ts:475` onto it.

**Deviation from the two templates, recorded in the spec (D4, P&L).** Both
templates print `% (amount)` unconditionally, so an unsized trade renders
`+4.20% (—)`. This cell leaves an unknown amount out instead (`+4.20%`), and
shows `—` only when there is nothing to price (`pct === null`).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/pnl-cell.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { PnlCell } from './pnl-cell';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/pnl-cell.ts'), 'utf8');

@Component({
  imports: [PnlCell],
  template: `<sb-pnl-cell [pct]="pct()" [amount]="amount()" currency="€" />`,
})
class Host {
  readonly pct = signal<number | null>(4.2);
  readonly amount = signal<number | null>(9.8);
}

describe('PnlCell (v80 cell contract)', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const text = () => el().textContent!.replace(/\s+/g, ' ').trim();
  const cell = () => el().querySelector('.pnl') as HTMLElement;
  const set = (p: number | null, a: number | null) => {
    host.pct.set(p);
    host.amount.set(a);
    fixture.detectChanges();
  };

  it('reads the percentage and the amount together', () => {
    expect(text()).toBe('+4.20% (+9.80 €)');
  });

  it('colours a gain green', () => {
    expect(cell().classList).toContain('pos');
  });

  it('colours a loss red, with both figures signed', () => {
    set(-1.35, -6.1);
    expect(text()).toBe('-1.35% (-6.10 €)');
    expect(cell().classList).toContain('neg');
  });

  it('leaves an exact zero uncoloured', () => {
    set(0, 0);
    expect(text()).toBe('0.00% (0.00 €)');
    expect(cell().classList).not.toContain('pos');
    expect(cell().classList).not.toContain('neg');
  });

  it('is an em dash when there is nothing to price', () => {
    set(null, null);
    expect(text()).toBe('—');
    expect(cell()).toBeNull();
  });

  it('leaves an unknown amount out rather than printing "(—)"', () => {
    set(4.2, null);
    expect(text()).toBe('+4.20%');
    expect(el().querySelector('.amount')).toBeNull();
  });

  it('flashes when the percentage changes, never on first render', () => {
    expect(cell().classList).not.toContain('flash-up');
    set(5, 11.2);
    expect(cell().classList).toContain('flash-up');
  });

  it('keeps both figures on one line', () => {
    expect(SOURCE).toMatch(/\.pnl \{[^}]*white-space: nowrap/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/pnl-cell.spec.ts')`

Expected: FAIL. `./pnl-cell` does not exist.

- [ ] **Step 3: Implement**

Create `frontend/src/app/ui/pnl-cell.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Flash } from './flash';
import { ABSENT, money, pct } from './format';

/**
 * P&L as one cell holding both figures -- the v80 cell contract.
 *
 * `+4.20% (+9.80 €)`: the percentage says how good the trade was, the amount
 * says how much money that was, and neither answers the other's question.
 * Extracted from the identical templates in `trades.ts` and `dashboard.ts`.
 * Migration moves both here, and Ticker detail gains the amount.
 *
 * Coloured by the sign of the percentage through the global .pos/.neg (the
 * valence law's one green and one red), and flashing when the percentage
 * changes through the same [sbFlash] the templates used.
 *
 * An em dash when there is no percentage to price. An unknown amount is left
 * out, not shown as "(—)": a bracketed dash beside a real percentage reads as
 * a rendering fault, not as "size unknown".
 */
@Component({
  selector: 'sb-pnl-cell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Flash],
  template: `
    @if (pct() !== null) {
      <span class="pnl num" [sbFlash]="pct()" [class]="tone()">
        {{ pctText() }}
        @if (amount() !== null) {
          <span class="amount"> ({{ amountText() }})</span>
        }
      </span>
    } @else {
      <span class="absent">{{ absent }}</span>
    }
  `,
  styles: `
    .pnl { font-family: var(--font-mono); font-size: var(--text-table); white-space: nowrap; }
    /* The amount is the second figure: same colour, one step smaller. */
    .amount { font-size: var(--text-chip); }
    .absent { color: var(--text-muted); }
  `,
})
export class PnlCell {
  readonly pct = input.required<number | null>();
  readonly amount = input<number | null>(null);
  /** From `ConnectionStore.currency()`, never a literal -- see `money()`. */
  readonly currency = input.required<string>();

  protected readonly absent = ABSENT;
  protected readonly pctText = computed(() => pct(this.pct()));
  protected readonly amountText = computed(() => money(this.amount(), this.currency()));

  /** Exactly zero is neither a gain nor a loss. */
  protected readonly tone = computed(() => {
    const value = this.pct();
    if (value === null || value === 0) return '';
    return value > 0 ? 'pos' : 'neg';
  });
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/pnl-cell.spec.ts' --include='**/flash.spec.ts')`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/pnl-cell.ts frontend/src/app/ui/pnl-cell.spec.ts
git commit -m "feat(v80): sb-pnl-cell -- percent and amount in one signed, flashing cell"
```
