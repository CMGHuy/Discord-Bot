# UI Elevation (v54) — Part 1: The primitive layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Index:** `2026-08-23-v54-ui-elevation_0-index.md` — read its Global Constraints first.
**Spec:** `docs/superpowers/specs/2026-08-23-v54-ui-elevation-design.md` (decision D7)

**Goal:** Every shared part this plan needs exists in `ui/`, is visible at `/ui`, and is protected by a test that fails when someone hand-rolls it again.

**This is a solo wave.** It edits `ui/` and touches every workspace file. Nothing else runs beside it, and it merges to `main` before waves `_2`–`_5` begin.

## Why the order inside this wave matters

Tasks 1–2 extend primitives; tasks 3–4 migrate call sites onto them. Doing the migration first would force call sites onto controls that do not fit, or produce a fistful of allowlist exceptions — and a gate that starts life with a fistful of exceptions teaches everyone that exceptions are normal. Task 12's gate lands last, because it fails until 1–11 are done.

## File map

| File | Responsibility |
|---|---|
| `src/app/ui/button.ts` (modify) | gains `chip`, `segment`, `link` variants |
| `src/app/ui/form-controls.ts` (modify) | `sb-text-input` gains `date` |
| `src/app/ui/section-head.ts` (create) | `sb-section-head` — replaces `.head` in 7 workspaces |
| `src/app/ui/row-link.ts` (create) | `sb-row-link` — replaces `.row-link` in 4 |
| `src/app/ui/note.ts` (create) | `sb-note` — replaces `.note` in 3 |
| `src/app/ui/chip-row.ts` (create) | `sb-chip-row` — replaces `.chips` in 3 |
| `src/app/ui/async.ts` (create) | `sb-async` — the four honest states |
| `src/styles.css` (modify) | global `.pos` / `.neg` / `.muted` valence utilities |
| `src/app/workspaces/gallery/gallery.ts` (create) | the `/ui` route |
| `src/app/ui/testing/call-sites.ts` (create) | shared source-walker for every gate |
| `src/app/ui/primitives.spec.ts` (create) | the regression gate + justified allowlist |

---

### Task 1: `sb-button` gains `chip`, `segment` and `link` variants

**Files:**
- Modify: `frontend/src/app/ui/button.ts`
- Test: `frontend/src/app/ui/button.spec.ts` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'icon' | 'chip' | 'segment' | 'link'`. Task 3 binds `variant="chip" | "segment" | "link"`; Task 11 renders all eight.

`icon` already exists — do not re-add it. The three new variants are the ones `versions.ts` hand-rolled because nothing fitted.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/button.spec.ts`:

```ts
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Button, type ButtonVariant } from './button';

@Component({
  imports: [Button],
  template: `<button sb-button [variant]="variant">Label</button>`,
})
class Host {
  variant: ButtonVariant = 'secondary';
}

function render(variant: ButtonVariant): HTMLButtonElement {
  const f = TestBed.createComponent(Host);
  f.componentInstance.variant = variant;
  f.detectChanges();
  return f.nativeElement.querySelector('button')!;
}

describe('Button variants', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  for (const variant of ['primary', 'secondary', 'danger', 'ghost', 'icon',
                         'chip', 'segment', 'link'] as ButtonVariant[]) {
    it(`puts the ${variant} class on the native button`, () => {
      expect(render(variant).classList.contains(variant)).toBe(true);
    });
  }

  it('keeps the element a native button so disabled and submit still work', () => {
    const el = render('chip');
    expect(el.tagName).toBe('BUTTON');
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd frontend && npm test -- --include src/app/ui/button.spec.ts`
Expected: FAIL — the three new variant names are not assignable to `ButtonVariant`, so the spec does not compile.

- [ ] **Step 3: Widen the type**

In `button.ts`, replace the type alias:

```ts
export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'danger'
  | 'ghost'
  | 'icon'
  | 'chip'
  | 'segment'
  | 'link';
```

- [ ] **Step 4: Add the three styles**

Append inside the existing `styles:` template literal in `button.ts`, after the `.icon` rules:

```css
    /* A filter toggle. Reads as a chip, behaves as a button: versions/ had
       four of these hand-rolled because no variant covered a control that is
       a chip in appearance and a toggle in function. `.on` is the pressed
       state and pairs with aria-pressed at the call site. */
    :host(.chip) {
      min-height: 0;
      padding: var(--space-4) var(--space-8);
      border-color: var(--border);
      border-radius: var(--radius-chip);
      background: var(--surface-raised);
      color: var(--text-secondary);
      font-size: var(--text-chip);
      font-weight: 500;
    }
    :host(.chip:not([disabled]):hover) { border-color: var(--border-strong); color: var(--text); }
    :host(.chip.on) {
      border-color: var(--accent);
      background: var(--accent-soft);
      color: var(--text);
    }

    /* One cell of a segmented control. The group owns the outer border and
       the radius; a segment owns only its divider, so segments sit flush. */
    :host(.segment) {
      border-color: transparent;
      border-radius: 0;
      background: transparent;
      color: var(--text-secondary);
      font-weight: 500;
    }
    :host(.segment:not([disabled]):hover) { color: var(--text); }
    :host(.segment.current) { background: var(--surface-overlay); color: var(--text); }

    /* A button that must look like a link because it sits in running text.
       Still a button: it performs an action rather than navigating, and an
       <a> without an href is not focusable. */
    :host(.link) {
      min-height: 0;
      padding: 0;
      background: transparent;
      color: var(--accent);
      font-size: var(--text-table);
      font-weight: 500;
    }
    :host(.link:not([disabled]):hover) { text-decoration: underline; }
```

- [ ] **Step 5: Run the test and watch it pass**

Run: `cd frontend && npm test -- --include src/app/ui/button.spec.ts`
Expected: PASS, 9 tests. (A 60s worker timeout is the documented flake — re-run.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/button.ts frontend/src/app/ui/button.spec.ts
git commit -m "feat(v54): add chip, segment and link button variants"
```

---

### Task 2: `sb-text-input` gains `date`

**Files:**
- Modify: `frontend/src/app/ui/form-controls.ts:142` (the `type` input)
- Test: `frontend/src/app/ui/form-controls.spec.ts` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `TextInput.type` accepts `'date'`. Task 4 uses it for analytics' two range fields.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/form-controls.spec.ts`:

```ts
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { TextInput } from './form-controls';

function render(type: 'text' | 'search' | 'number' | 'password' | 'date') {
  const f = TestBed.createComponent(TextInput);
  f.componentRef.setInput('type', type);
  f.componentRef.setInput('ariaLabel', 'field');
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('input')!;
}

describe('TextInput', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders a native date picker for type=date', () => {
    expect(render('date').getAttribute('type')).toBe('date');
  });

  it('still renders the pre-existing types', () => {
    for (const t of ['text', 'search', 'number', 'password'] as const) {
      expect(render(t).getAttribute('type')).toBe(t);
    }
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd frontend && npm test -- --include src/app/ui/form-controls.spec.ts`
Expected: FAIL — `'date'` is not assignable to the `type` input.

- [ ] **Step 3: Widen the input**

In `form-controls.ts`, replace the `type` input declaration and extend the comment above it:

```ts
  /**
   * … existing comment about `number` retained verbatim …
   *
   * `date` was added for the Analytics range filter, which had two raw
   * `<input type="date">` because nothing here covered it. The native picker
   * is the right control — it is keyboard-accessible, localised by the
   * browser, and this app never needs a range calendar.
   */
  readonly type = input<'text' | 'search' | 'number' | 'password' | 'date'>('text');
```

- [ ] **Step 4: Run and watch it pass**

Run: `cd frontend && npm test -- --include src/app/ui/form-controls.spec.ts`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/form-controls.ts frontend/src/app/ui/form-controls.spec.ts
git commit -m "feat(v54): sb-text-input accepts type=date"
```

---

### Task 3: Migrate the 10 plain-migration buttons and 2 selects

**Files:**
- Modify: `frontend/src/app/shell/shell.html` (`menu-button`, `collapse`, the zoom `<select>`)
- Modify: `frontend/src/app/shell/profile-menu.ts` (`avatar` trigger, `menuitem`)
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts` (`reset`)
- Modify: `frontend/src/app/workspaces/system/logs-tab.ts` (the log-lines `<select>`)
- Modify: `frontend/src/app/workspaces/versions/versions.ts` (`chip`, `chip moved`, `segment`, `link`)
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts` (typeahead result button)
- Modify: `frontend/src/app/shell/login/login.html` (submit button only — its inputs are Task 4)

**Interfaces:**
- Produces: `callSites()` from `ui/testing/call-sites.ts`, consumed by Tasks 9, 12, 21, 24, 27 and 34.
- Consumes: `Button` variants from Task 1 (`chip`, `segment`, `link`, plus existing `icon`, `ghost`, `primary`); `Select` from `form-controls.ts`.
- Produces: nothing new. Task 12's gate depends on these being gone.

Each call site keeps its behaviour, its `aria-*` attributes and its event bindings. Only the paint moves.

- [ ] **Step 1: Write the shared helper**

`callSites()` lives in a plain module, **not** in a `.spec.ts`. Three later
specs (`async-coverage`, `numeric`, `register`) need it, and importing a spec
file re-executes its `describe` blocks inside the importer — every gate here
would run four times and be reported under the wrong filename.

Create `frontend/src/app/ui/testing/call-sites.ts`:

```ts
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const APP = join(process.cwd(), 'src/app');

/** Every template-bearing source outside `ui/`, which is where primitives
 *  are allowed to use raw elements because that is what they wrap. */
export function callSites(): { name: string; source: string }[] {
  const out: { name: string; source: string }[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) {
        if (entry !== 'ui' && entry !== 'testing') walk(full);
        continue;
      }
      if (!/\.(ts|html)$/.test(entry) || entry.endsWith('.spec.ts')) continue;
      out.push({ name: full.slice(APP.length + 1), source: readFileSync(full, 'utf8') });
    }
  };
  walk(APP);
  return out;
}
```

Then create `frontend/src/app/ui/primitives.spec.ts` with its first assertion
(Task 12 grows this file):

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { callSites } from './testing/call-sites';

describe('no call site hand-rolls a button', () => {
  for (const { name, source } of callSites()) {
    it(`${name} routes every button through sb-button`, () => {
      const raw = [...source.matchAll(/<button\b[^>]*>/gs)]
        .map(([tag]) => tag)
        .filter((tag) => !tag.includes('sb-button'));
      expect(raw).toEqual([]);
    });
  }
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd frontend && npm test -- --include src/app/ui/primitives.spec.ts`
Expected: FAIL for `shell/shell.html`, `shell/profile-menu.ts`, `shell/login/login.html`, `shell/toast-host.ts`, `workspaces/system/settings-tab.ts`, `workspaces/versions/versions.ts`, `workspaces/watchlist/watchlist.ts`.

`toast-host.ts` will still fail after this task — it is a permanent allowlist entry added in Task 12. That is expected here.

- [ ] **Step 3: Migrate the shell's two icon buttons**

In `shell.html`, the menu and collapse buttons keep every attribute and gain the variant:

```html
      <button sb-button variant="icon" class="menu-button" type="button"
              aria-label="Open navigation" (click)="openOverlay()">
        <sb-icon name="menu" />
      </button>
```

```html
        <button
          sb-button
          variant="icon"
          class="collapse"
          type="button"
          [attr.aria-label]="railed() ? 'Expand sidebar' : 'Collapse sidebar'"
          [attr.aria-pressed]="railed()"
          (click)="toggleSidebar()"
        >
          <sb-icon [name]="railed() ? 'expand' : 'collapse'" />
        </button>
```

Add `Button` to the `imports` array of `shell.ts`. Delete from `shell.css` any `background`, `border`, `color`, `padding` or `cursor` declaration on `.menu-button` / `.collapse` that the `icon` variant now supplies; keep only positioning rules (`position`, `grid-area`, `margin`, `align-self`).

- [ ] **Step 4: Migrate the shell's zoom select**

Replace the raw `<select>` in `shell.html` with the primitive, keeping the option-level `[selected]` binding — the comment above it explains why `[value]` on the host does not work and that reasoning is unchanged:

```html
      <sb-select
        class="zoom"
        label="Text"
        ariaLabel="Text size"
        (changed)="setZoom(+$event)"
      >
        @for (choice of zoomChoices; track choice) {
          <option [value]="choice" [selected]="choice === zoom()">{{ choice }}%</option>
        }
      </sb-select>
```

Read `form-controls.ts`'s `Select` before writing this: match its actual input and output names. If `Select` projects options via `<ng-content>`, the block above is correct as written; if it takes an options array input, pass `zoomChoices` and bind the selected value the way `Select` documents.

- [ ] **Step 5: Migrate the remaining seven buttons**

- `profile-menu.ts`: trigger → `sb-button variant="icon"`, keeping `#trigger`, `[attr.aria-expanded]` and the class; the `role="menuitem"` sign-out → `sb-button variant="ghost"`.
- `settings-tab.ts`: `class="reset"` → `sb-button variant="icon"`, keeping `[title]`.
- `versions.ts`: `class="chip"` and `class="chip moved"` → `sb-button variant="chip"` (keep `moved` and bind `[class.on]`); `class="segment"` → `sb-button variant="segment"` (keep `[class.current]`); `class="link"` → `sb-button variant="link"`.
- `watchlist.ts`: the typeahead hit → `sb-button variant="ghost"`, keeping `(mousedown)`.
- `login.html`: submit → `sb-button variant="primary"`, keeping `type="submit"` and `[disabled]`.

Add `Button` to each component's `imports`. In each component's `styles`, delete the declarations the variant now owns and keep only layout.

- [ ] **Step 6: Migrate the logs-tab select**

In `logs-tab.ts`, replace the raw `<select>` with `<sb-select>` following the same shape as Step 4, and add `Select` to its `imports`.

- [ ] **Step 7: Run the gate**

Run: `cd frontend && npm test -- --include src/app/ui/primitives.spec.ts`
Expected: PASS for every file except `shell/toast-host.ts`, which is allowlisted in Task 12.

- [ ] **Step 8: Run the whole frontend suite for regressions**

Run: `cd frontend && npm test`
Expected: green. The existing `tokens.spec.ts` "no workspace hand-rolls a control row" check must still pass — if a deleted flex rule trips it, the row genuinely became a control row and should use `sb-control-row`.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app
git commit -m "refactor(v54): route the last shell and workspace buttons through sb-button"
```

---

### Task 4: Migrate the remaining raw inputs; login drops `ngModel`

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (2× `type="date"`)
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts` (1× `type="text"`)
- Modify: `frontend/src/app/workspaces/system/logs-tab.ts` (1× `type="checkbox"`)
- Modify: `frontend/src/app/shell/login/login.html` and `login.ts` (2× `ngModel`)
- Test: `frontend/src/app/ui/primitives.spec.ts` (extend)

**Interfaces:**
- Consumes: `TextInput` with `date` (Task 2), `Checkbox` and `Select` from `form-controls.ts`.
- Produces: nothing new.

`form-controls.ts:5` records *"Nothing in this application uses Angular forms"*. Login is the single exception and it predates the primitives. **Login drops `ngModel` rather than the primitives gaining `ControlValueAccessor`** — adding CVA to three components to serve two fields in one template is the larger change and would contradict the recorded decision.

- [ ] **Step 1: Extend the gate to inputs and selects**

Append to `primitives.spec.ts`:

```ts
/**
 * Raw form controls that stay raw, each with the reason it cannot be wrapped.
 * Adding a name here is a claim about the control, so it needs a reason.
 */
const RAW_CONTROL_ALLOWLIST = new Map<string, string>([
  // A file input cannot be wrapped: the picker only opens from a real click
  // on the real element, and re-dispatching one loses the user-activation
  // that browsers require.
  ['workspaces/system/settings-tab.ts', 'type=file'],
]);

describe('no call site hand-rolls a form control', () => {
  for (const { name, source } of callSites()) {
    it(`${name} routes every input and select through a primitive`, () => {
      const allowed = RAW_CONTROL_ALLOWLIST.get(name);
      const raw = [...source.matchAll(/<(input|select)\b[^>]*>/gs)]
        .map(([tag]) => tag.replace(/\s+/g, ' '))
        .filter((tag) => !(allowed && tag.includes(allowed)));
      expect(raw).toEqual([]);
    });
  }
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd frontend && npm test -- --include src/app/ui/primitives.spec.ts`
Expected: FAIL for `analytics.ts` (2), `watchlist.ts` (1), `logs-tab.ts` (1), `login.html` (2). `settings-tab.ts` passes via the allowlist.

- [ ] **Step 3: Migrate analytics' date range**

```html
        <sb-text-input
          type="date"
          label="From"
          [value]="store.rangeFrom() ?? ''"
          (valueChange)="store.setRangeFrom($event)"
        />
        <sb-text-input
          type="date"
          label="To"
          [value]="store.rangeTo() ?? ''"
          (valueChange)="store.setRangeTo($event)"
        />
```

`TextInput` uses `model()`, so the binding is `[value]` + `(valueChange)` — or `[(value)]` where the store exposes a writable signal. Read `TextInput`'s declaration and match its actual model name. Delete `onRangeFrom` / `onRangeTo` from `analytics.ts` if they now only unwrap `$event.target.value`; keep them if they do anything else.

- [ ] **Step 4: Migrate watchlist's entry field and logs-tab's checkbox**

Watchlist keeps its Enter handling — bind `(keydown.enter)` on the `sb-text-input` host. Logs-tab:

```html
          <sb-checkbox
            [label]="level"
            [checked]="store.logLevels()[level]"
            (checkedChange)="store.setLogLevel(level, $event)"
          />
```

- [ ] **Step 5: Convert login off `ngModel`**

In `login.html`:

```html
      <sb-text-input
        label="Username"
        name="username"
        autocomplete="username"
        [value]="username()"
        (valueChange)="username.set($event)"
      />
      <sb-text-input
        label="Password"
        type="password"
        name="password"
        autocomplete="current-password"
        [value]="password()"
        (valueChange)="password.set($event)"
      />
```

In `login.ts`, remove `FormsModule` from `imports`. The `required` and `autofocus` attributes were doing real work — reproduce them: keep the submit button's existing `[disabled]="submitting() || incomplete()"` (which already covers `required`), and move focus in `ngAfterViewInit` via a `viewChild` on the first field rather than the `autofocus` attribute.

If `TextInput` does not forward `name` or `autocomplete` to its inner `<input>`, add pass-through inputs for both in `form-controls.ts` — a password manager needs them and dropping them is a real regression.

- [ ] **Step 6: Run the gate and the suite**

Run: `cd frontend && npm test`
Expected: green, and `primitives.spec.ts` now passes for every file except `toast-host.ts`.

- [ ] **Step 7: Manually verify login still works**

Run: `cd frontend && npm start`, open `/login`, confirm the browser's password manager still offers to fill, and that submitting signs in.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app
git commit -m "refactor(v54): route the last raw inputs through primitives; login drops ngModel"
```

---

### Task 5: `sb-section-head` — the header all seven workspaces hand-rolled

**Files:**
- Create: `frontend/src/app/ui/section-head.ts`
- Test: `frontend/src/app/ui/section-head.spec.ts`
- Modify (7): `workspaces/{analytics,dashboard,risk,system,trades,versions,watchlist}/*.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `<sb-section-head [heading]="'Trades'" [level]="1">` projecting actions into `[actions]`. Tasks 30–34 (`_4`) set the register class on it. Task 11 renders it.

Today's shape, identical in all seven: `<header class="head"><h1>Title</h1><sb-control-row class="head-actions">…</sb-control-row></header>` plus a four-line flex rule each.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/section-head.spec.ts`:

```ts
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { SectionHead } from './section-head';

@Component({
  imports: [SectionHead],
  template: `
    <sb-section-head [heading]="'Trades'" [level]="level">
      <button actions type="button">Export</button>
    </sb-section-head>
  `,
})
class Host {
  level: 1 | 2 = 1;
}

function render(level: 1 | 2 = 1) {
  const f = TestBed.createComponent(Host);
  f.componentInstance.level = level;
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('SectionHead', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders the heading at the requested level', () => {
    expect(render(1).querySelector('h1')!.textContent).toContain('Trades');
    expect(render(2).querySelector('h2')!.textContent).toContain('Trades');
  });

  it('projects actions beside the heading', () => {
    expect(render().querySelector('button')!.textContent).toContain('Export');
  });

  it('emits exactly one heading element', () => {
    expect(render().querySelectorAll('h1, h2').length).toBe(1);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd frontend && npm test -- --include src/app/ui/section-head.spec.ts`
Expected: FAIL — `./section-head` does not exist.

- [ ] **Step 3: Create the component**

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * The band at the top of a workspace or panel: a heading, and optionally the
 * controls that act on what it names.
 *
 * All seven workspaces hand-rolled this as `.head` with the same four-line
 * flex rule, which is how seven slightly different gaps and two different
 * heading sizes arrived. The level is an input rather than inferred, because
 * a panel inside a workspace needs an h2 under the workspace's h1 and only
 * the caller knows which it is — an inferred level would silently produce two
 * h1s on one page.
 */
@Component({
  selector: 'sb-section-head',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (level() === 1) {
      <h1>{{ heading() }}</h1>
    } @else {
      <h2>{{ heading() }}</h2>
    }
    <div class="actions"><ng-content select="[actions]" /></div>
  `,
  styles: `
    :host {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-10);
    }
    h1 { font-size: var(--text-title); font-weight: 600; }
    h2 { font-size: var(--text-subhead); font-weight: 600; }
    .actions { display: contents; }
  `,
})
export class SectionHead {
  readonly heading = input.required<string>();
  readonly level = input<1 | 2>(1);
}
```

- [ ] **Step 4: Run and watch it pass**

Run: `cd frontend && npm test -- --include src/app/ui/section-head.spec.ts`
Expected: PASS, 3 tests.

- [ ] **Step 5: Convert all seven workspaces**

In each of the seven, replace the `<header class="head">…</header>` block with:

```html
    <sb-section-head heading="Trades">
      <sb-control-row actions class="head-actions"> … existing actions … </sb-control-row>
    </sb-section-head>
```

Delete the `.head` rule from that component's `styles` and its `h1 { font-size: … }` rule. Add `SectionHead` to `imports`. Keep `.head-actions` where the component styles it beyond what `sb-control-row` supplies.

Do the seven one at a time, running `npm test` after each — a heading that silently disappears is easy to miss in a diff of seven files.

- [ ] **Step 6: Add the gate**

Append to `primitives.spec.ts`:

```ts
describe('no call site redefines a promoted composite', () => {
  const PROMOTED = ['head', 'row-link', 'note', 'chips'];
  for (const { name, source } of callSites()) {
    it(`${name} defines none of the promoted classes`, () => {
      const offenders = PROMOTED.filter((cls) =>
        new RegExp(`^\\s*\\.${cls}\\s*[,{]`, 'm').test(source),
      );
      expect(offenders).toEqual([]);
    });
  }
});
```

This fails for `row-link`, `note` and `chips` until Tasks 6–8 land. That is expected — run it again at the end of Task 8.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app
git commit -m "feat(v54): extract sb-section-head and adopt it in all seven workspaces"
```

---

### Task 6: `sb-row-link`

**Files:**
- Create: `frontend/src/app/ui/row-link.ts`
- Test: `frontend/src/app/ui/row-link.spec.ts`
- Modify (4): the four workspaces defining `.row-link`

**Interfaces:**
- Consumes: nothing.
- Produces: `<sb-row-link [link]="['/trades', id]">` projecting cell content.

- [ ] **Step 1: Find the four call sites and read them**

Run: `cd frontend/src/app && grep -rn "row-link" workspaces/ | grep -v spec`

Read each. If two of them differ in behaviour (one navigates, one opens a drawer), the component takes `link` **or** emits `activated`, never both silently — record which call site uses which in the component's doc comment.

- [ ] **Step 2: Write the failing test**

Create `frontend/src/app/ui/row-link.spec.ts`:

```ts
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { RowLink } from './row-link';

function render(link: unknown[]) {
  const f = TestBed.createComponent(RowLink);
  f.componentRef.setInput('link', link);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('RowLink', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
  });

  it('renders a real anchor so the row can be opened in a new tab', () => {
    const a = render(['/trades', 7]).querySelector('a')!;
    expect(a.tagName).toBe('A');
    expect(a.getAttribute('href')).toBe('/trades/7');
  });

  it('covers the whole row so the click target is the row, not the text', () => {
    expect(render(['/trades', 7]).querySelector('a')!.className).toContain('row-link');
  });
});
```

- [ ] **Step 3: Run and watch it fail**

Run: `cd frontend && npm test -- --include src/app/ui/row-link.spec.ts`
Expected: FAIL — module not found.

- [ ] **Step 4: Create the component**

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * A table row that navigates.
 *
 * A real `<a>` with an href, not a `(click)` on the `<tr>`: middle-click,
 * ctrl-click, "open in new tab" and the status-bar preview all come free, and
 * every one of them is lost the moment a row becomes a div with a handler.
 * Four workspaces had hand-rolled `.row-link`, and they disagreed about the
 * hover colour.
 */
@Component({
  selector: 'sb-row-link',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `<a class="row-link" [routerLink]="link()"><ng-content /></a>`,
  styles: `
    :host { display: contents; }
    .row-link {
      display: flex;
      align-items: center;
      gap: var(--space-8);
      color: inherit;
      text-decoration: none;
    }
    .row-link:hover { background: var(--surface-raised); text-decoration: none; }
    .row-link:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  `,
})
export class RowLink {
  readonly link = input.required<unknown[]>();
}
```

- [ ] **Step 5: Run and watch it pass, then convert the four call sites**

Run: `cd frontend && npm test -- --include src/app/ui/row-link.spec.ts` → PASS, 2 tests.
Then replace each `.row-link` usage, delete the local rule, add `RowLink` to `imports`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app
git commit -m "feat(v54): extract sb-row-link and adopt it in four workspaces"
```

---

### Task 7: `sb-note`

**Files:**
- Create: `frontend/src/app/ui/note.ts`
- Test: `frontend/src/app/ui/note.spec.ts`
- Modify (3): the three workspaces defining `.note`

**Interfaces:**
- Consumes: nothing.
- Produces: `<sb-note [tone]="'info' | 'warn'">` projecting text.

`styles.css` already has `.section-help` and `.panel-subtitle` globals. Read both before writing this — if `.note` in all three call sites is the same thing as one of those, **delete `.note` and use the existing global instead of adding a fourth kind of explanatory text.** Only create `sb-note` if it is genuinely distinct (a bordered callout rather than running copy). Record which it turned out to be in the commit message.

- [ ] **Step 1: Read the three call sites and both globals**

Run: `cd frontend/src/app && grep -rn -A6 '^\s*\.note\s*[,{]' workspaces/ | head -40` and `sed -n '/section-help/,/^}/p;/panel-subtitle/,/^}/p' ../styles.css`

- [ ] **Step 2: Decide, and take the matching branch**

If they are the same as an existing global: delete the three local `.note` rules, switch the markup to `class="section-help"` or `class="panel-subtitle"`, run `npm test`, commit `refactor(v54): fold .note into the existing section-help global`, and skip to Task 8.

If genuinely distinct, continue to Step 3.

- [ ] **Step 3: Write the failing test**

Create `frontend/src/app/ui/note.spec.ts`:

```ts
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Note } from './note';

@Component({
  imports: [Note],
  template: `<sb-note [tone]="tone">Positions are paper only.</sb-note>`,
})
class Host {
  tone: 'info' | 'warn' = 'info';
}

function render(tone: 'info' | 'warn') {
  const f = TestBed.createComponent(Host);
  f.componentInstance.tone = tone;
  f.detectChanges();
  return f.nativeElement.querySelector('sb-note') as HTMLElement;
}

describe('Note', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('projects its content', () => {
    expect(render('info').textContent).toContain('paper only');
  });

  it('carries the tone as a class so the valence token is picked by CSS', () => {
    expect(render('warn').classList.contains('warn')).toBe(true);
    expect(render('info').classList.contains('info')).toBe(true);
  });
});
```

- [ ] **Step 4: Run and watch it fail, then create the component**

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * A bordered callout: a fact about this panel the reader must not miss.
 *
 * Distinct from `.section-help` (running explanatory copy under a heading)
 * and `.panel-subtitle` (a one-line gloss naming what a table is). Both of
 * those are quiet by design; this one is not, which is why it takes a tone.
 *
 * Only `info` and `warn`: a note is never `--pos` or `--neg`, because those
 * two hues mean money everywhere else in this app.
 */
@Component({
  selector: 'sb-note',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[class]': 'tone()' },
  template: `<ng-content />`,
  styles: `
    :host {
      display: block;
      padding: var(--space-8) var(--space-10);
      border-left: 2px solid;
      border-radius: var(--radius-chip);
      font-size: var(--text-table);
      line-height: 1.5;
    }
    :host(.info) { border-color: var(--info); background: var(--info-soft); color: var(--text-secondary); }
    :host(.warn) { border-color: var(--warn); background: var(--warn-soft); color: var(--text); }
  `,
})
export class Note {
  readonly tone = input<'info' | 'warn'>('info');
}
```

- [ ] **Step 5: Run, convert the three call sites, commit**

```bash
git add frontend/src/app
git commit -m "feat(v54): extract sb-note and adopt it in three workspaces"
```

---

### Task 8: `sb-chip-row`

**Files:**
- Create: `frontend/src/app/ui/chip-row.ts`
- Test: `frontend/src/app/ui/chip-row.spec.ts`
- Modify (3): the three workspaces defining `.chips`

**Interfaces:**
- Consumes: nothing.
- Produces: `<sb-chip-row>` projecting `sb-chip` / `sb-button variant="chip"` children.

**Read `tokens.spec.ts`'s `NOT_CONTROL_ROWS` first.** `chips` is on that allowlist, with the reason *"the Dashboard's data-card rows … rows of DISPLAYED figures, not controls"*. So `.chips` means two different things across the three call sites — a display row on dashboard, a filter row elsewhere. Determine which each is before extracting; if they are genuinely different, extract only the display one and route the filter ones through `sb-control-row`, then **remove `chips` from `NOT_CONTROL_ROWS`** and note in that comment that the row it exempted is now a component.

- [ ] **Step 1: Classify the three call sites**

Run: `cd frontend/src/app && grep -rn -B3 -A8 '^\s*\.chips\s*[,{]' workspaces/`

Write down, for each: display row or control row?

- [ ] **Step 2: Write the failing test**

Create `frontend/src/app/ui/chip-row.spec.ts`:

```ts
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { ChipRow } from './chip-row';

@Component({
  imports: [ChipRow],
  template: `<sb-chip-row><span class="a">1</span><span class="b">2</span></sb-chip-row>`,
})
class Host {}

describe('ChipRow', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('projects its chips', () => {
    const f = TestBed.createComponent(Host);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('.a')).toBeTruthy();
    expect(el.querySelector('.b')).toBeTruthy();
  });
});
```

- [ ] **Step 3: Run it, watch it fail, create the component**

```ts
import { ChangeDetectionStrategy, Component } from '@angular/core';

/**
 * A wrapping row of chips that DISPLAY rather than control.
 *
 * `tokens.spec.ts` exempts `chips` from the "no hand-rolled control row" gate
 * precisely because these are figures, not controls — so this is not
 * `sb-control-row` and must not become it. A row of chips that are filters is
 * a control row and belongs in `sb-control-row` instead.
 */
@Component({
  selector: 'sb-chip-row',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<ng-content />`,
  styles: `
    :host {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-6);
    }
  `,
})
export class ChipRow {}
```

- [ ] **Step 4: Convert, update `NOT_CONTROL_ROWS`, run the full gate**

Run: `cd frontend && npm test`
Expected: green — and the Task 5 "no call site redefines a promoted composite" gate now passes for all four names.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app
git commit -m "feat(v54): extract sb-chip-row; separate display chip rows from control rows"
```

---

### Task 9: Global valence utilities

**Files:**
- Modify: `frontend/src/styles.css`
- Modify (3): the workspaces defining `.pos`, `.neg`, `.muted`
- Test: `frontend/src/app/ui/primitives.spec.ts` (extend)

**Interfaces:**
- Consumes: nothing.
- Produces: global `.pos`, `.neg`, `.muted` classes. Task 25 (`_3`) uses them for the numeric law.

Three workspaces each redefined `.pos` and `.neg`. These are the valence law's own colours — the most carefully argued rule in `tokens.css` — and a local redefinition is how such a law dies: not by being overruled, but by drifting a shade at a time.

- [ ] **Step 1: Compare the three definitions before merging them**

Run: `cd frontend/src/app && grep -rn -A3 '^\s*\.\(pos\|neg\|muted\)\s*[,{]' workspaces/`

If any of the three has drifted off `var(--pos)` / `var(--neg)` / `var(--text-muted)`, **that drift is a bug this task fixes** — note the drifted value in the commit message rather than silently normalising it.

- [ ] **Step 2: Write the failing gate**

Append to `primitives.spec.ts`:

```ts
describe('the valence law is not forked', () => {
  for (const { name, source } of callSites()) {
    it(`${name} does not redefine .pos, .neg or .muted`, () => {
      const offenders = ['pos', 'neg', 'muted'].filter((cls) =>
        new RegExp(`^\\s*\\.${cls}\\s*[,{]`, 'm').test(source),
      );
      expect(offenders).toEqual([]);
    });
  }
});
```

- [ ] **Step 3: Run it and watch it fail** for the three workspaces.

- [ ] **Step 4: Add the globals**

Append to `frontend/src/styles.css`:

```css
/* Valence utilities.
 *
 * Global, and they have to be. Three workspaces had each declared their own
 * `.pos` / `.neg`, which is how a colour law dies — not by being overruled,
 * but by drifting a shade at a time in three files nobody diffs together.
 * `tokens.css` owns what the hues MEAN; this owns the one way to apply them
 * to text.
 *
 * Colour is never the only carrier — see the numeric law: a sign is a glyph
 * as well as a hue, because a screenshot pasted into Discord loses neither. */
.pos { color: var(--pos); }
.neg { color: var(--neg); }
.muted { color: var(--text-muted); }
```

- [ ] **Step 5: Delete the three local copies, run the gate**

Run: `cd frontend && npm test` → green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles.css frontend/src/app
git commit -m "feat(v54): promote the valence utilities to global; unfork .pos/.neg"
```

---

### Task 10: `sb-async` — the four honest states

**Files:**
- Create: `frontend/src/app/ui/async.ts`
- Test: `frontend/src/app/ui/async.spec.ts`

**Interfaces:**
- Consumes: `EmptyStateComponent` from `ui/empty-state.ts`.
- Produces — every symbol wave `_2` binds against:

```ts
export type AsyncEmptyReason = 'no-data-yet' | 'measured-zero';

class Async {
  loading    = input(false);
  error      = input<string | null>(null);
  empty      = input(false);
  emptyReason = input.required<AsyncEmptyReason>();   // required: this is gate G2
  emptyTitle  = input.required<string>();
  emptyHint   = input<string | undefined>(undefined);
  staleAsOf  = input<string | null>(null);            // 'HH:MM', or null when fresh
  skeletonRows = input(6);
  skeletonCols = input(4);
  retry      = output<void>();
}
```

**`emptyReason` is `input.required` on purpose.** It is the whole of gate G2: a call site that has not decided which empty it is will not compile. `known-traps.md` records that this repo has empty tables which are measured answers rather than stubs; rendering both identically tells the reader "something is broken" when the truth is "the scan found nothing, and that is the finding."

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/async.spec.ts`:

```ts
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Async, type AsyncEmptyReason } from './async';

@Component({
  imports: [Async],
  template: `
    <sb-async
      [loading]="loading"
      [error]="error"
      [empty]="empty"
      [emptyReason]="reason"
      [emptyTitle]="'No closed trades'"
      [staleAsOf]="staleAsOf"
      [skeletonRows]="3"
      [skeletonCols]="2"
      (retry)="retried = retried + 1"
    >
      <p class="content">loaded</p>
    </sb-async>
  `,
})
class Host {
  loading = false;
  error: string | null = null;
  empty = false;
  reason: AsyncEmptyReason = 'no-data-yet';
  staleAsOf: string | null = null;
  retried = 0;
}

function render(patch: Partial<Host> = {}) {
  const f = TestBed.createComponent(Host);
  Object.assign(f.componentInstance, patch);
  f.detectChanges();
  return { f, el: f.nativeElement as HTMLElement };
}

describe('Async', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('shows the content when there is nothing wrong', () => {
    const { el } = render();
    expect(el.querySelector('.content')).toBeTruthy();
    expect(el.querySelector('.skeleton')).toBeNull();
  });

  it('shows a shaped skeleton while loading, not a spinner', () => {
    const { el } = render({ loading: true });
    expect(el.querySelectorAll('.skeleton-row').length).toBe(3);
    expect(el.querySelectorAll('.skeleton-row')[0].children.length).toBe(2);
    expect(el.querySelector('.content')).toBeNull();
  });

  it('marks itself busy while loading', () => {
    const { el } = render({ loading: true });
    expect(el.querySelector('sb-async')!.getAttribute('aria-busy')).toBe('true');
  });

  it('shows the error and offers a retry that emits', () => {
    const { f, el } = render({ error: 'Request failed' });
    expect(el.textContent).toContain('Request failed');
    el.querySelector<HTMLButtonElement>('.retry')!.click();
    expect(f.componentInstance.retried).toBe(1);
  });

  it('distinguishes a measured zero from missing data', () => {
    expect(render({ empty: true, reason: 'no-data-yet' }).el.textContent)
      .toContain('awaiting data');
    expect(render({ empty: true, reason: 'measured-zero' }).el.textContent)
      .toContain('result: 0');
  });

  it('dims the content and names the time when the data is stale', () => {
    const { el } = render({ staleAsOf: '15:42' });
    expect(el.querySelector('.content')).toBeTruthy();
    expect(el.querySelector('.stale-badge')!.textContent).toContain('as of 15:42');
  });

  it('prefers error over loading, and loading over empty', () => {
    const { el } = render({ error: 'boom', loading: true, empty: true });
    expect(el.textContent).toContain('boom');
    expect(el.querySelector('.skeleton')).toBeNull();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd frontend && npm test -- --include src/app/ui/async.spec.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Create the component**

```ts
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { EmptyStateComponent } from './empty-state';

/** Which empty this is. Not optional — see the class comment. */
export type AsyncEmptyReason = 'no-data-yet' | 'measured-zero';

/**
 * The four states every fetch-backed region can be in, in one place.
 *
 * Before this, six of seven workspaces rendered nothing at all while
 * fetching, and an empty table looked identical whether the request failed,
 * the data had not arrived, or the answer was genuinely zero.
 *
 * **`emptyReason` is required.** `known-traps.md` records that this repo
 * contains empty tables which are measured answers rather than stubs. A table
 * showing no confluence setups because the scan found none is a RESULT;
 * rendering it like a failed fetch tells the reader the opposite of the
 * truth. Making the reason required means a call site that has not thought
 * about it does not compile.
 *
 * The loading branch is a SHAPED skeleton, not a spinner: it occupies the
 * geometry the loaded content will, so nothing reflows at the moment the
 * reader starts reading. A spinner swapped for a table moves every element on
 * the page.
 *
 * Branch order is error > loading > empty > content, so a refetch that fails
 * reports the failure rather than spinning forever.
 */
@Component({
  selector: 'sb-async',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [EmptyStateComponent],
  host: { '[attr.aria-busy]': 'loading() ? "true" : null' },
  template: `
    @if (error(); as message) {
      <div class="failed" role="alert">
        <p class="failed-text">{{ message }}</p>
        <button class="retry" type="button" (click)="retry.emit()">Retry</button>
      </div>
    } @else if (loading()) {
      <div class="skeleton" aria-hidden="true">
        @for (row of rows(); track $index) {
          <div class="skeleton-row">
            @for (col of cols(); track $index) {
              <span class="skeleton-cell"></span>
            }
          </div>
        }
      </div>
    } @else if (empty()) {
      <div class="empty-wrap">
        <span class="reason" [class]="emptyReason()">
          {{ emptyReason() === 'measured-zero' ? 'result: 0' : 'awaiting data' }}
        </span>
        <sb-empty-state [title]="emptyTitle()" [hint]="emptyHint()" />
      </div>
    } @else {
      @if (staleAsOf(); as at) {
        <span class="stale-badge">as of {{ at }}</span>
      }
      <div class="content" [class.stale]="staleAsOf() !== null">
        <ng-content />
      </div>
    }
  `,
  styles: `
    :host { display: block; position: relative; }

    .failed { padding: var(--space-14); text-align: center; }
    .failed-text { color: var(--neg); font-size: var(--text-table); }
    .retry {
      margin-top: var(--space-8);
      min-height: var(--control-h);
      padding: 0 var(--space-14);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
      background: var(--surface-raised);
      color: var(--text);
      font-family: var(--font-sans);
      font-size: var(--text-table);
      cursor: pointer;
    }

    .skeleton { display: flex; flex-direction: column; gap: var(--space-6); }
    .skeleton-row { display: flex; gap: var(--space-10); }
    /* Height matched to a table row so the swap costs no layout shift. */
    .skeleton-cell {
      flex: 1;
      height: var(--control-h);
      border-radius: var(--radius-chip);
      background: var(--surface-raised);
      animation: pulse 1.4s var(--ease-out) infinite;
    }
    @keyframes pulse { 50% { opacity: 0.45; } }

    .empty-wrap { text-align: center; }
    .reason {
      display: inline-block;
      padding: var(--space-4) var(--space-8);
      border-radius: var(--radius-chip);
      font-family: var(--font-mono);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    /* A measured zero is a NEUTRAL fact; missing data is a CAUTION. The two
       tokens are the whole visible difference and they are the point. */
    .reason.measured-zero { background: var(--info-soft); color: var(--info); }
    .reason.no-data-yet { background: var(--warn-soft); color: var(--warn); }

    .stale-badge {
      position: absolute;
      top: 0;
      right: 0;
      padding: var(--space-4) var(--space-6);
      border-radius: var(--radius-chip);
      background: var(--warn-soft);
      color: var(--warn);
      font-family: var(--font-mono);
      font-size: var(--text-micro);
    }
    .content.stale { color: var(--text-secondary); }
  `,
})
export class Async {
  readonly loading = input(false);
  readonly error = input<string | null>(null);
  readonly empty = input(false);
  /** Required: this input IS acceptance gate G2. */
  readonly emptyReason = input.required<AsyncEmptyReason>();
  readonly emptyTitle = input.required<string>();
  readonly emptyHint = input<string | undefined>(undefined);
  /** 'HH:MM', or null when the data is fresh. */
  readonly staleAsOf = input<string | null>(null);
  readonly skeletonRows = input(6);
  readonly skeletonCols = input(4);

  readonly retry = output<void>();

  protected readonly rows = computed(() => Array.from({ length: this.skeletonRows() }));
  protected readonly cols = computed(() => Array.from({ length: this.skeletonCols() }));
}
```

- [ ] **Step 4: Run and watch it pass**

Run: `cd frontend && npm test -- --include src/app/ui/async.spec.ts`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/async.ts frontend/src/app/ui/async.spec.ts
git commit -m "feat(v54): add sb-async with a required empty reason"
```

---

### Task 11: The `/ui` gallery

**Files:**
- Create: `frontend/src/app/workspaces/gallery/gallery.ts`
- Modify: `frontend/src/app/app.routes.ts`
- Test: `frontend/src/app/workspaces/gallery/gallery.spec.ts`

**Interfaces:**
- Consumes: every exported primitive in `ui/`.
- Produces: the `/ui` route. Waves `_3` and `_4` add their new parts here.

The gallery is the only surface on which the elevation ladder, the numeric law and the chart ramp can be seen together and judged as one system — reviewing them one workspace at a time is how inconsistency survives review. It ships in the production bundle behind the existing auth guard: a gallery that only exists in dev rots, because nothing fails when it does.

- [ ] **Step 1: Write the failing test — it enumerates `ui/` from disk**

Create `frontend/src/app/workspaces/gallery/gallery.spec.ts`:

```ts
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const UI = join(process.cwd(), 'src/app/ui');
const GALLERY = readFileSync(
  join(process.cwd(), 'src/app/workspaces/gallery/gallery.ts'),
  'utf8',
);

/** Every `selector: 'sb-…'` declared under ui/, read off disk so a new
 *  primitive is caught the day it is added rather than the day someone
 *  remembers this file exists. */
function selectors(): string[] {
  const found = new Set<string>();
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) { walk(full); continue; }
      if (!entry.name.endsWith('.ts') || entry.name.endsWith('.spec.ts')) continue;
      for (const [, sel] of readFileSync(full, 'utf8')
        .matchAll(/selector:\s*'((?:button\[)?sb-[\w-]+)\]?'/g)) {
        found.add(sel.replace(/^button\[/, ''));
      }
    }
  };
  walk(UI);
  return [...found].sort();
}

describe('the gallery shows every primitive', () => {
  for (const selector of selectors()) {
    it(`renders ${selector}`, () => {
      expect(GALLERY).toContain(`<${selector}`);
    });
  }
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd frontend && npm test -- --include src/app/workspaces/gallery/gallery.spec.ts`
Expected: FAIL — the gallery file does not exist.

- [ ] **Step 3: Create the gallery**

Build it section by section, one `<sb-panel>` per primitive family, each showing every variant and every state. Minimum content:

- **Buttons** — all eight variants × {default, hover-note, disabled, loading}.
- **Form controls** — `sb-text-input` in all five types, `sb-select`, `sb-checkbox` (checked, unchecked, disabled, with and without `topLabel`).
- **Chips** — `sb-chip`, `sb-quality-chip` at levels 1–5, inside an `sb-chip-row`.
- **Composites** — `sb-section-head` at both levels, `sb-note` in both tones, `sb-row-link`, `sb-control-row`, `sb-filter-bar`, `sb-panel`, `sb-tab-bar`, `sb-drawer`.
- **`sb-async`** — **all four branches side by side**, both empty reasons, driven by local signals so a reader can toggle them.
- **Empty state** — `sb-empty-state` with and without a hint.

Every section is wrapped in `<sb-section-head level="2" [heading]="…">` so the gallery itself uses the system it documents.

- [ ] **Step 4: Register the route**

In `app.routes.ts`, add inside the authenticated route group so it inherits `authGuard`:

```ts
  {
    path: 'ui',
    title: 'UI gallery',
    loadComponent: () => import('./workspaces/gallery/gallery').then((m) => m.Gallery),
  },
```

Do **not** add a sidebar nav entry — the gallery is a developer surface, and wave `_5` groups the nav around the eight data workspaces. It is reachable by URL.

- [ ] **Step 5: Run the test and look at the page**

Run: `cd frontend && npm test -- --include src/app/workspaces/gallery/gallery.spec.ts` → PASS.
Run: `cd frontend && npm start`, open `/ui`, and read it top to bottom. Anything that looks wrong here is wrong everywhere — fix it now rather than in wave `_3`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app
git commit -m "feat(v54): add the /ui primitive gallery and gate it on ui/ exports"
```

---

### Task 12: Finish the regression gate

**Files:**
- Modify: `frontend/src/app/ui/primitives.spec.ts`

**Interfaces:**
- Consumes: `callSites()` from Task 3.
- Produces: gates G4 and G7.

- [ ] **Step 1: Add the hex-literal gate and the button allowlist**

Append to `primitives.spec.ts`:

```ts
/**
 * Raw buttons that stay raw, each with the reason.
 *
 * One entry, and it should stay that way. A gate that starts life with a
 * fistful of exceptions teaches everyone that exceptions are normal.
 */
const RAW_BUTTON_ALLOWLIST = new Map<string, string>([
  // The whole toast IS the dismiss control -- a full-bleed surface with its
  // own kind-coloured background, not a button sitting inside a toast. Giving
  // it a variant would mean a variant used exactly once, which is a worse
  // answer than one justified exception.
  ['shell/toast-host.ts', 'class="toast"'],
]);

/**
 * Colour literals outside tokens.css.
 *
 * Empty, and that is the point: `--chart-1..8` (wave _4) moved the last eight
 * out of `ui/line-chart.ts`. An entry here is a hue that escaped the valence
 * law.
 */
const HEX_ALLOWLIST = new Map<string, string>([]);

describe('no colour is declared outside tokens.css', () => {
  for (const { name, source } of callSites()) {
    it(`${name} declares no hex literal`, () => {
      const allowed = HEX_ALLOWLIST.get(name);
      const hexes = [...source.matchAll(/#[0-9a-fA-F]{3,8}\b/g)]
        .map(([hex]) => hex)
        .filter((hex) => !(allowed && allowed.includes(hex)));
      expect(hexes).toEqual([]);
    });
  }
});
```

Then wire `RAW_BUTTON_ALLOWLIST` into the Task 3 button gate:

```ts
      const allowed = RAW_BUTTON_ALLOWLIST.get(name);
      const raw = [...source.matchAll(/<button\b[^>]*>/gs)]
        .map(([tag]) => tag.replace(/\s+/g, ' '))
        .filter((tag) => !tag.includes('sb-button'))
        .filter((tag) => !(allowed && tag.includes(allowed)));
      expect(raw).toEqual([]);
```

- [ ] **Step 2: Run it**

Run: `cd frontend && npm test -- --include src/app/ui/primitives.spec.ts`
Expected: the hex gate **fails for `ui/line-chart.ts`** only if `callSites()` walked `ui/` — it does not, by construction. It should PASS. If any workspace still carries a hex, that hex is a real finding: move it to `tokens.css` or justify it in `HEX_ALLOWLIST` with a reason on the line.

- [ ] **Step 3: Add a meta-test that the allowlists stay justified**

```ts
describe('every allowlist entry is justified', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/primitives.spec.ts'), 'utf8');

  for (const list of ['RAW_CONTROL_ALLOWLIST', 'RAW_BUTTON_ALLOWLIST', 'HEX_ALLOWLIST']) {
    it(`${list} has a comment above every entry`, () => {
      const body = SOURCE.slice(SOURCE.indexOf(`const ${list}`));
      const block = body.slice(0, body.indexOf(']);'));
      const entries = [...block.matchAll(/^\s*\[['"]/gm)];
      const comments = [...block.matchAll(/^\s*\/\//gm)];
      expect(comments.length).toBeGreaterThanOrEqual(entries.length);
    });
  }
});
```

- [ ] **Step 4: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: green.

- [ ] **Step 5: Confirm the Python suite did not move**

Run: `python scripts/dev/testrun.py full`
Expected: `1686 passed, 66 skipped, 0 failed` — this wave touched no Python, so anything else is a real signal.

- [ ] **Step 6: Commit and merge the wave**

```bash
git add frontend/src/app/ui/primitives.spec.ts
git commit -m "test(v54): gate raw controls, forked valence classes and stray hexes"
```

Then merge `_1` to `main` before starting any other wave.

## Wave 1 done when

- [ ] `npm test` green; `primitives.spec.ts` passes with exactly two allowlist entries (file input, toast), both justified.
- [ ] `/ui` renders every `sb-*` selector declared under `ui/` (G8).
- [ ] Zero hex literals outside `tokens.css` and `ui/line-chart.ts` (G4 — line-chart is wave `_4`).
- [ ] `.head`, `.row-link`, `.note`, `.chips`, `.pos`, `.neg`, `.muted` defined in no workspace.
- [ ] Python suite unchanged.
- [ ] Merged to `main`.
