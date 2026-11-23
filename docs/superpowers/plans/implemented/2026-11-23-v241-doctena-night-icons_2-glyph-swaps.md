# v241 — Doctena night, plan 2 of 5: Icons — Part 2: glyph swaps and the gate

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V241-6" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) §4 and its `### Corrections from the plan 2 code brief (2026-11-23)` (which wins over earlier text and the mockups).
**Index:** [2026-11-23-v241-doctena-night-icons_0-index.md](2026-11-23-v241-doctena-night-icons_0-index.md) — Goal, Architecture, Decisions, Global Constraints, Parallelisation and the task ledger live there; every task below implicitly includes its Global Constraints.

This part: V241-5..V241-8 — the help trigger draws `info`, the drawer close and the panel and row toggles draw icons, the watchlist tape toggle, the versions "now" marker and the Guide's fold marker draw icons, and one source gate keeps the replaced glyphs out and each swapped control's accessible name in.

Verification in every task is the narrow run, from `frontend/`:
`npx ng test --watch=false --include <spec>` (a 60s `Timeout waiting for worker` is machine load: re-run once). No task runs the full suite; CI does.

**Pattern for every swap in this part (index Architecture):** the control keeps its element, class and accessible name; only the glyph text becomes `<sb-icon ... title="" />` (empty `title`, so the icon adds no tooltip or second name inside a labelled control). The svg is `aria-hidden` (V241-1). `sb-icon` sits `inline-flex` with `vertical-align: middle` inside the button's line box, so the button keeps the text baseline its header row aligns on (`sb-panel` and `sb-drawer` headers are `align-items: baseline`): no `display` change on the buttons.

**Icon drawings these tasks assert** (from V241-1/V241-2's `PATHS`; `sb-icon`'s `name` is a property binding with no DOM trace, so a test reads the drawn `d`):

```ts
const INFO_D = 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v5.5 M12 7.6v.1';
const CLOSE_D = 'M6 6l12 12 M18 6 6 18';
const EXPAND_D = 'M9 6l6 6-6 6';
const DOWN_D = 'M6 9l6 6 6-6';
const UP_D = 'M6 15l6-6 6 6';
const PLUS_D = 'M12 7v10 M7 12h10';
const MINUS_D = 'M7 12h10';
```

Each spec below declares the ones it needs locally (a spec file never imports from another spec).

**Commits:** one subject line per commit, no body and no trailer (partner's standing rule).

# Phase 2 — glyph swaps

### Task V241-5: `sb-hint` draws the `info` icon; the `glyph` input is deleted

**Model:** sonnet — one shared primitive used on every page plus two callers; the trigger's name, `aria-describedby` and phone touch target must survive, and a static `glyph=` left on a caller would not fail the build.

**Files:**
- Modify: `frontend/src/app/ui/hint.ts` (imports; the trigger's `<span class="glyph">`, l.143; the `.glyph` rule, l.177-186; the touch-target comment, l.227-231; the `glyph` input, l.244-245)
- Modify: `frontend/src/app/ui/hint.spec.ts` (new tests in `describe('Hint (v80 D4)')` and `describe('Hint anchor (label) mode (v195 correction 10)')`)
- Modify: `frontend/src/app/shell/shell.html` (l.45, drop `glyph="v"`)
- Modify: `frontend/src/app/shell/shell.spec.ts` (`keeps the ui and bot versions in a hint at the foot of the rail`, ~l.333)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (l.312, drop `glyph="?"`)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (`merges the Open positions help into one tooltip`, ~l.493)

**Interfaces:**
- Consumes: V241-2's `info` name (`IconName`) and its drawing; V241-1b's 16px default `size`; `allSources(): Source[]` and `stripComments(source: string): string` from `frontend/src/app/ui/testing/all-sources.ts` (exist).
- Produces: `sb-hint`'s trigger is `button.trigger[aria-label][aria-expanded][aria-describedby] > sb-icon[name=info][title=""]` (no text, no `.glyph`); `Hint` has no `glyph` input. V241-8's accessible-name guard reads `hint.ts` for `[attr.aria-label]="label()"` on the trigger and `<sb-icon name="info" title="" />` inside it.

**Why:** spec §4 and its correction — `sb-hint` drew a letter (`i`, or `v`/`?` for two callers) in a 14px CSS circle in the mono face; it now always draws the `info` icon, and the rail's version hint and the dashboard's open-positions help become `info` too (partner, 2026-11-23). The `.glyph` rule was the only `--font-mono` rule here, so plan 1's type gate (`ui/type-gates.spec.ts`) can only lose an offender. The icon is 16px (index Decision 2: everything off the rail, the tab bar and the lists is 16); the trigger's 44px phone/tablet target stays the centred `::after`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/hint.spec.ts`, add to the imports:

```ts
import { allSources, stripComments } from './testing/all-sources';
```

and below `const SOURCE = ...`:

```ts
/** icon.ts's `info` drawing (V241-2): a circle, a stem and a dot. */
const INFO_D = 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v5.5 M12 7.6v.1';
```

Inside `describe('Hint (v80 D4)', ...)`, after `it('floats as an overlay, ...')`, add:

```ts
  it('draws the info icon in its trigger, not a letter in a circle (v240 §4)', () => {
    const icon = trigger().querySelector(':scope > sb-icon');
    expect(icon).not.toBeNull();
    expect(icon!.querySelector('svg path')!.getAttribute('d')).toBe(INFO_D);
    // No text left in the button: the shape no longer depends on the font.
    expect(trigger().textContent!.trim()).toBe('');
    expect(trigger().querySelector('.glyph')).toBeNull();
  });

  it('keeps the name on the button and out of the icon', () => {
    // One name per control: "About expectancy", never "About expectancy Information".
    expect(trigger().getAttribute('aria-label')).toBe('About expectancy');
    expect(trigger().getAttribute('aria-describedby')).toBe(pop().id);
    expect(trigger().getAttribute('aria-expanded')).toBe('false');
    const icon = trigger().querySelector('sb-icon')!;
    expect(icon.getAttribute('title')).toBe('');
    expect(icon.querySelector('svg')!.getAttribute('aria-hidden')).toBe('true');
    expect(trigger().querySelectorAll('[aria-label]')).toHaveLength(0);
  });

  it('draws the icon at the inline size, 16px', () => {
    expect(trigger().querySelector('sb-icon svg')!.getAttribute('width')).toBe('16');
  });

  it('has no glyph input and no glyph rule left', () => {
    expect(SOURCE).not.toMatch(/\bglyph\s*=\s*input\b/);
    expect(SOURCE).not.toMatch(/\.glyph\s*\{/);
  });

  it('is never handed a glyph by a caller: a static glyph= would be a dead attribute', () => {
    // strictTemplates does not reject an unknown static attribute on a
    // component, so a leftover glyph="v" would build, render nothing and
    // mislead the next reader. Scan every template instead.
    const offenders = allSources()
      .filter(({ source }) => /<sb-hint\b[^>]*\bglyph=/.test(stripComments(source)))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });
```

Inside `describe('Hint anchor (label) mode (v195 correction 10)', ...)`, after `it('renders no trigger button, ...')`, add:

```ts
  it('draws no info icon in anchor mode: the rail link is the thing being named', () => {
    expect((fixture.nativeElement as HTMLElement).querySelector('sb-hint sb-icon')).toBeNull();
  });
```

(`fixture` is that describe's `ComponentFixture<AnchorHost>`, created in its `beforeEach` with `anchored()` true.)

In `frontend/src/app/shell/shell.spec.ts`, in `it('keeps the ui and bot versions in a hint at the foot of the rail', ...)`, after the `expect(hint.querySelector('[role=tooltip]')...)` assertion and before `expect(el.querySelector('.version-row')).toBeNull();`, add:

```ts
    // v240 §4 correction: the version hint draws the info icon like every
    // other hint; the "v" letter it used to opt into is gone.
    const trigger = hint.querySelector('button.trigger')!;
    expect(trigger.getAttribute('aria-label')).toBe('Version');
    expect(trigger.querySelector('sb-icon svg path')!.getAttribute('d'))
      .toBe('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v5.5 M12 7.6v.1');
    expect(trigger.textContent!.trim()).toBe('');
```

In `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, in `it('merges the Open positions help into one tooltip', ...)`, after `expect(hint).not.toBeNull();`, add:

```ts
    // v240 §4 correction: the "?" opt-in is gone; this help draws info too.
    const trigger = hint.querySelector('button.trigger')!;
    expect(trigger.getAttribute('aria-label')).toBe('About open positions');
    expect(trigger.querySelector('sb-icon svg path')!.getAttribute('d'))
      .toBe('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v5.5 M12 7.6v.1');
    expect(trigger.textContent!.trim()).toBe('');
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/hint.spec.ts --include src/app/shell/shell.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: FAIL — the trigger holds `<span class="glyph">i</span>` (no `sb-icon`), the source still declares `glyph = input('i')` and `.glyph {`, and the scan names `app/shell/shell.html` and `app/workspaces/dashboard/dashboard.ts`.

- [ ] **Step 3: Draw the icon in `frontend/src/app/ui/hint.ts`**

Add the import after the `@angular/core` import block:

```ts
import { Icon } from './icon';
```

Add `imports: [Icon],` to the `@Component({ selector: 'sb-hint', ... })` metadata, after `selector`.

In the template, replace:

```html
      <span class="glyph" aria-hidden="true">{{ glyph() }}</span>
```

with:

```html
      <sb-icon name="info" title="" />
```

In `styles`, delete the whole `.glyph { ... }` rule (l.177-186, `display: inline-grid;` through `line-height: 1;`). `.trigger` already centres its content (`display: inline-grid; place-items: center`) and its `color` is what `sb-icon` strokes with (`currentColor`), so hover and the open state still brighten the icon.

In the touch-target comment, replace:

```css
    /* A fingertip needs 44px around a 14px glyph (v80 D4; phone and tablet
```

with:

```css
    /* A fingertip needs 44px around a 16px icon (v80 D4; phone and tablet
```

In the `Hint` class, delete these two lines:

```ts
  /** Default to the familiar information glyph; a nearby question can opt in. */
  readonly glyph = input('i');
```

In the class doc comment above `@Component`, after the paragraph that starts ``The trigger is a real button with `aria-expanded` ``, add:

```ts
 *
 * The trigger always draws the `info` icon (v240 §4): the per-caller letter
 * (`glyph="v"`, `glyph="?"`) is gone. The icon is aria-hidden with an empty
 * title, so the button's `label` stays its one accessible name.
```

- [ ] **Step 4: Drop the two `glyph=` attributes**

`frontend/src/app/shell/shell.html` l.45 becomes:

```html
        <sb-hint class="version" label="Version" align="left" [text]="versionText()" />
```

`frontend/src/app/workspaces/dashboard/dashboard.ts` l.312 becomes:

```html
      <sb-hint panel-actions class="lifecycle-hint" [xl]="true" align="left"
```

(the next line, `label="About open positions">`, is unchanged).

- [ ] **Step 5: Run the tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/hint.spec.ts --include src/app/shell/shell.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/ui/type-gates.spec.ts`
Expected: PASS, 0 failed (`type-gates` runs because a `--font-mono` rule left `hint.ts`).

Then: `git grep -n "glyph" -- frontend/src/app/ui/hint.ts frontend/src/app/shell/shell.html frontend/src/app/workspaces/dashboard/dashboard.ts`. Expected: no output.

- [ ] **Step 6: Check the three widths**

Per `docs/claude/ui-design.md` (Playwright only, `.env` admin credentials loaded inside the script, never printed): at 390px, 820px and 1440px, a Dashboard KPI tile's hint, the Open positions panel's hint (was `?`) and, where the rail shows, the rail-foot version hint (was `v`) all draw the same 16px circled-i icon in `--text-muted`, brightening on hover; it sits centred on its label's line, the label row is no taller than before, and a tap at 390px opens the popover.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/hint.ts frontend/src/app/ui/hint.spec.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.spec.ts frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git commit -m "feat(ui): sb-hint draws the info icon and drops its glyph input (V241-5)"
```

### Task V241-6: Drawer close, panel toggle and row-detail toggle draw icons

**Model:** sonnet — two shared primitives on every page; three buttons whose accessible names and touch targets many click-through specs rely on, inside headers that align on the text baseline.

**Files:**
- Modify: `frontend/src/app/ui/layout.ts` (`Panel` `imports`, l.42; the panel toggle, l.57-65; `Drawer` `imports`, l.463; the drawer close button, l.479; the `.close` rule, l.533-545)
- Modify: `frontend/src/app/ui/layout.spec.ts` (`describe('sb-panel collapse')`; a new `describe` after `describe('sb-drawer header slot (v179 §3.2)')`)
- Modify: `frontend/src/app/ui/data-table/data-table.ts` (imports, l.18-26 and l.75; the row-detail toggle, l.163-173; the `.expander` rule, l.435-442)
- Modify: `frontend/src/app/ui/data-table/data-table.spec.ts` (`describe('DataTable row detail')`, `describe('DataTable look (v195 Phase 2)')`)

**Interfaces:**
- Consumes: V241-2's `close` and `down` names and V241-1's `expand` drawing; V241-1b's 16px default `size`.
- Produces: `sb-drawer`'s `button.close[aria-label="Close"] > sb-icon[name=close][title=""]`; `sb-panel`'s `button.panel-toggle > sb-icon` drawing `down` while expanded and `expand` while collapsed; `sb-data-table`'s `button.expander.detail-toggle > sb-icon` the same way. Every button keeps its class, `aria-expanded` and `aria-label` unchanged. V241-8's accessible-name guard reads these three sources.

**Why:** spec §4 and its correction (the `layout.ts` `×` close and `▾`/`▸` toggle, the `data-table.ts` `▾`/`▸`; index Decision 3: `▾` expanded → `down`, `▸` collapsed → `expand`, `×` → `close`). The chevron says "open this" by pointing right and "it is open" by pointing down, as the glyphs did. The buttons' `font-size` (`--text-title` on `.close`, `--text-body` on `.expander`) only sized the glyph, so it goes; `line-height` and the `min-height`/`min-width: var(--control-h)` touch targets stay. No `display` change: the icon is inline-flex with `vertical-align: middle` in the button's line box, so each button keeps a text baseline and the `align-items: baseline` headers (`layout.spec.ts`, "keeps heading, marker and close on one baseline") still line up.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/layout.spec.ts`, below `const rule = ...` (l.17), add:

```ts
/** icon.ts drawings (V241-1, V241-2). sb-icon's `name` leaves no DOM trace. */
const CLOSE_D = 'M6 6l12 12 M18 6 6 18';
const EXPAND_D = 'M9 6l6 6-6 6';
const DOWN_D = 'M6 9l6 6 6-6';
```

Inside `describe('sb-panel collapse', ...)`, after `it('expands in place on tap and keeps the digest out of the way', ...)`, add:

```ts
  it('draws the expand chevron while collapsed and the down chevron once open (v240 §4)', () => {
    host.inlineFrom.set('md'); host.digest.set('3 open');
    host.viewportAt.set('sm'); fixture.detectChanges();
    const toggle = () => el().querySelector('button.panel-toggle') as HTMLElement;
    const drawn = () => toggle().querySelector(':scope > sb-icon svg path')!.getAttribute('d');

    expect(drawn()).toBe(EXPAND_D);
    expect(toggle().getAttribute('aria-label')).toBe('Expand Watchlist');
    expect(toggle().textContent!.trim()).toBe('');

    toggle().click();
    fixture.detectChanges();
    expect(drawn()).toBe(DOWN_D);
    expect(toggle().getAttribute('aria-label')).toBe('Collapse Watchlist');
    // The name is the button's alone: no tooltip, no second name from the icon.
    expect(toggle().querySelector('sb-icon')!.getAttribute('title')).toBe('');
    expect(toggle().querySelector('sb-icon svg')!.getAttribute('aria-hidden')).toBe('true');
  });
```

After the closing `});` of `describe('sb-drawer header slot (v179 §3.2)', ...)`, add:

```ts
describe('sb-drawer close draws the close icon (v240 §4)', () => {
  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('off')] });
  });

  it('is the close icon in a button named Close, with no text', () => {
    const fixture = TestBed.createComponent(DrawerSlotHost);
    fixture.detectChanges();
    const close = (fixture.nativeElement as HTMLElement).querySelector('sb-drawer header button.close')!;
    expect(close.getAttribute('aria-label')).toBe('Close');
    expect(close.textContent!.trim()).toBe('');
    const icon = close.querySelector(':scope > sb-icon')!;
    expect(icon.querySelector('svg path')!.getAttribute('d')).toBe(CLOSE_D);
    expect(icon.getAttribute('title')).toBe('');
    expect(icon.querySelector('svg')!.getAttribute('aria-hidden')).toBe('true');
    expect(close.querySelectorAll('[aria-label]')).toHaveLength(0);
  });

  it('keeps its touch target and drops the glyph font size', () => {
    const close = drawerRule('.close');
    expect(close).toContain('min-width: var(--control-h)');
    expect(close).toContain('min-height: var(--control-h)');
    expect(close).not.toContain('font-size');
  });
});
```

In `frontend/src/app/ui/data-table/data-table.spec.ts`, below `const ROWS: Row[] = [...]` (l.50), add:

```ts
/** icon.ts drawings (V241-1, V241-2). */
const EXPAND_D = 'M9 6l6 6-6 6';
const DOWN_D = 'M6 9l6 6 6-6';
```

Inside `describe('DataTable row detail', ...)`, after `it('names the row it opens, so the toggle is not an anonymous chevron', ...)`, add:

```ts
  it('draws the expand chevron collapsed and the down chevron expanded (v240 §4)', () => {
    const toggle = () => el().querySelector('button.detail-toggle') as HTMLElement;
    const drawn = () => toggle().querySelector(':scope > sb-icon svg path')!.getAttribute('d');

    expect(drawn()).toBe(EXPAND_D);
    expect(toggle().getAttribute('aria-label')).toMatch(/^Show more for /);
    expect(toggle().getAttribute('aria-label')).toContain(ROWS[0].ticker);
    expect(toggle().textContent!.trim()).toBe('');

    toggle().click();
    fixture.detectChanges();
    expect(drawn()).toBe(DOWN_D);
    expect(toggle().getAttribute('aria-label')).toMatch(/^Show less for /);
    expect(toggle().querySelector('sb-icon')!.getAttribute('title')).toBe('');
    expect(toggle().querySelector('sb-icon svg')!.getAttribute('aria-hidden')).toBe('true');
  });

  it('draws one chevron per row, every one of them an icon', () => {
    const toggles = [...el().querySelectorAll('button.detail-toggle')];
    expect(toggles).toHaveLength(ROWS.length);
    for (const toggle of toggles) {
      expect(toggle.querySelectorAll('sb-icon')).toHaveLength(1);
      expect(toggle.textContent!.trim()).toBe('');
    }
  });
```

Inside `describe('DataTable look (v195 Phase 2)', ...)`, add:

```ts
  it('sizes the row toggle by its touch target, not by a glyph font size (v240 §4)', () => {
    const expander = DATA_TABLE_SOURCE.match(/\n\s*\.expander\s*\{[^}]*\}/)?.[0] ?? '';
    expect(expander).not.toBe('');
    expect(expander).not.toContain('font-size');
    expect(DATA_TABLE_SOURCE).toMatch(/\.detail-toggle\s*\{[^}]*min-height: var\(--control-h\);[^}]*min-width: var\(--control-h\)/);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/layout.spec.ts --include src/app/ui/data-table/data-table.spec.ts`
Expected: FAIL — the buttons hold `×`, `▾` and `▸` text (no `sb-icon`), and the `.close` and `.expander` rules still carry `font-size`.

- [ ] **Step 3: Draw the icons in `frontend/src/app/ui/layout.ts`**

`Icon` is already imported (l.19). Change `Panel`'s `imports: [Hint],` (l.42) to `imports: [Hint, Icon],` and `Drawer`'s `imports: [FocusTrap],` (l.463) to `imports: [FocusTrap, Icon],`.

Replace the panel toggle's content line:

```html
              >{{ expanded() ? '▾' : '▸' }}</button>
```

with:

```html
              ><sb-icon [name]="expanded() ? 'down' : 'expand'" title="" /></button>
```

Replace the drawer's close button:

```html
            <button type="button" class="close" aria-label="Close" (click)="requestClose()">×</button>
```

with:

```html
            <button type="button" class="close" aria-label="Close" (click)="requestClose()"><sb-icon name="close" title="" /></button>
```

In the Drawer's `.close` rule, delete the line `font-size: var(--text-title);` (keep `line-height: 1;` and every other declaration).

- [ ] **Step 4: Draw the icon in `frontend/src/app/ui/data-table/data-table.ts`**

Add `import { Icon } from '../icon';` after `import { Hint } from '../hint';` (l.20), and add `Icon` to the component's `imports` array (l.75): `imports: [NgTemplateOutlet, EmptyStateComponent, Hint, Icon, PaginationComponent, Drawer, RouterLink],`.

Replace the toggle's content:

```html
                    {{ isExpanded(row) ? '▾' : '▸' }}
```

with:

```html
                    <sb-icon [name]="isExpanded(row) ? 'down' : 'expand'" title="" />
```

In the `.expander` rule, delete the line `font-size: var(--text-body);`.

- [ ] **Step 5: Run the tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/layout.spec.ts --include src/app/ui/data-table/data-table.spec.ts --include src/app/ui/hint.spec.ts --include src/app/ui/controls.spec.ts --include src/app/workspaces/dashboard/trade-drawer.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/ui/type-gates.spec.ts`
Expected: PASS, 0 failed (`hint`, `controls`, `trade-drawer` and `dashboard` click the drawer's `.close` or a toggle by class; `type-gates` scans both stylesheets).

Then: `git grep -n -E "▾|▸|>×<" -- frontend/src/app/ui/layout.ts frontend/src/app/ui/data-table/data-table.ts`. Expected: no output.

- [ ] **Step 6: Check the three widths**

Per `docs/claude/ui-design.md` (Playwright only, `.env` admin credentials loaded inside the script, never printed): at 390px, 820px and 1440px, open a trade drawer from a Dashboard open-positions row (a bottom sheet at 390px): the close is a 16px X at the end of the header row, on the heading's line, with its 44px target; at 390px a collapsible Dashboard panel shows the right chevron collapsed and the down chevron after a tap; on `/trades` at 390px a row's detail toggle shows the same pair. Each button's tooltip-free hover brightens the icon.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/layout.ts frontend/src/app/ui/layout.spec.ts frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/data-table/data-table.spec.ts
git commit -m "feat(ui): drawer close, panel toggle and row toggle draw icons (V241-6)"
```

### Task V241-7: Tape toggle, versions "now" marker and the Guide's fold marker

**Model:** sonnet — three pages and three mechanisms (a toggle with `aria-pressed`, a decorative inline marker, a CSS mask on sanitised markdown the component cannot template); each is small but none is a copy of the others.

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts` (the tape toggle's content, l.453)
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts` (`describe('Watchlist tape column sorting')`)
- Modify: `frontend/src/app/workspaces/versions/versions.ts` (imports, l.20 and l.47; the "now" tick, l.158)
- Modify: `frontend/src/app/workspaces/versions/versions.spec.ts` (`describe('Versions')`)
- Modify: `frontend/src/app/workspaces/guide/guide.ts` (the two `summary::before` rules, l.142-143)
- Modify: `frontend/src/app/workspaces/guide/guide.spec.ts` (imports; `describe('Guide page styles (source)')`)
- Modify: `frontend/src/app/ui/primitives.spec.ts` (the `(?<!&)` comment above `COLOUR_RE`, ~l.138-141; comment only)

**Interfaces:**
- Consumes: V241-2's `plus`, `minus`, `up` and `down` names and V241-1's `expand` drawing; V241-1b's 16px default `size`; plan 1 V240-6's `styleRules(name: string, source: string): StyleRule[]` from `frontend/src/app/ui/testing/style-rules.ts` (`name` relative to `src/`, as `allSources()` gives it).
- Produces: `button.tape-toggle > sb-icon[title=""]` drawing `plus` (row not in the tape, `aria-pressed="false"`) or `minus` (in the tape, `aria-pressed="true"`), `aria-label` unchanged; `.ticks .now > sb-icon[name=up][title=""]` between the date and "now"; the Guide's `summary::before` is a 16px `currentColor` box masked by the `expand` path, `details[open] > summary::before` by the `down` path. V241-8's gate reads all three sources for the replaced glyphs, and `watchlist.ts` for the toggle's `aria-label`.

**Why:** spec §4's correction lists `watchlist.ts` `◉`/`○`, `versions.ts` `&#9650;` and `guide.ts`'s CSS `▸`/`▾` among the standalone markers to replace. Index Decision 3 (open for the controller): the tape toggle draws `plus` when the row is not in the tape (pressing adds it) and `minus` when it is (pressing removes it); the button keeps `aria-pressed` and its aria-label "Show <SYM> in the live tape", so a screen reader still hears a pressed/not-pressed toggle. The versions marker is decorative (the word "now" follows it), so the icon carries `title=""` — without it the tooltip would read `up`'s label, "Move up", which is wrong here. The Guide's `<details>` is sanitised markdown rendered through `[innerHTML]`, where no Angular component can run, so it draws the same chevron paths through a CSS `mask` data URI (index Architecture); a mask reads alpha only, so the svg's `stroke='black'` means "opaque" and the colour is the summary's `currentColor` (`--text-muted`). The data URI holds no `#` and no `rgb(`, so `primitives.spec.ts`'s colour gate is unaffected; its `(?<!&)` lookbehind stays (it costs nothing and keeps any future entity from reading as a hex) and only its comment, which names `versions.ts`, is reworded.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`, inside `describe('Watchlist tape column sorting', ...)`, after `function rowSymbols()`, add:

```ts
  it('draws plus on a row outside the tape and minus on a row in it (v240 §4)', () => {
    // icon.ts drawings (V241-2).
    const PLUS_D = 'M12 7v10 M7 12h10';
    const MINUS_D = 'M7 12h10';
    const toggles = [...fixture.nativeElement.querySelectorAll('button.tape-toggle')] as HTMLButtonElement[];
    expect(toggles).toHaveLength(2);
    // Default sort: AAPL (not in the tape) first, NVDA (in the tape) second.
    const [aapl, nvda] = toggles;
    const drawn = (b: Element) => b.querySelector('sb-icon svg path')!.getAttribute('d');

    expect(drawn(aapl)).toBe(PLUS_D);
    expect(aapl.getAttribute('aria-pressed')).toBe('false');
    expect(aapl.getAttribute('aria-label')).toBe('Show AAPL in the live tape');

    expect(drawn(nvda)).toBe(MINUS_D);
    expect(nvda.getAttribute('aria-pressed')).toBe('true');
    expect(nvda.getAttribute('aria-label')).toBe('Show NVDA in the live tape');

    for (const toggle of toggles) {
      // No text glyph, no second name from the icon.
      expect(toggle.textContent!.trim()).toBe('');
      expect(toggle.querySelector('sb-icon')!.getAttribute('title')).toBe('');
      expect(toggle.querySelector('sb-icon svg')!.getAttribute('aria-hidden')).toBe('true');
    }
  });
```

In `frontend/src/app/workspaces/versions/versions.spec.ts`, inside `describe('Versions', ...)`, after `it('puts the "now" tick first, matching the flipped axis', ...)`, add:

```ts
  it('marks "now" with the up icon, not a text triangle (v240 §4)', async () => {
    const fixture = seed(SIX);
    await fixture.whenStable();
    fixture.detectChanges();

    const now = (fixture.nativeElement as HTMLElement).querySelector('.ticks .now')!;
    const icon = now.querySelector(':scope > sb-icon')!;
    expect(icon.querySelector('svg path')!.getAttribute('d')).toBe('M6 15l6-6 6 6');
    // Decorative: "now" names it. An unset title would tooltip "Move up".
    expect(icon.getAttribute('title')).toBe('');
    expect(icon.querySelector('svg')!.getAttribute('aria-hidden')).toBe('true');
    expect(now.textContent).not.toContain('▲');
    expect(now.textContent!.replace(/\s+/g, ' ').trim()).toMatch(/\S now$/);
  });
```

In `frontend/src/app/workspaces/guide/guide.spec.ts`, add to the imports:

```ts
import { styleRules } from '../../ui/testing/style-rules';
```

Inside `describe('Guide page styles (source)', ...)`, add:

```ts
  it('draws the fold marker with the chevron icons through a mask, not a text glyph (v240 §4)', () => {
    // Sanitised markdown runs no Angular component, so sb-icon cannot render
    // here; the marker masks the same 24-grid paths icon.ts draws.
    const rules = styleRules('app/workspaces/guide/guide.ts', source);
    const closed = rules.find((r) => r.selector === 'sb-guide .md summary::before')?.body ?? '';
    const open = rules.find((r) => r.selector === 'sb-guide .md details[open] > summary::before')?.body ?? '';

    expect(closed).toContain("content: ''");
    expect(closed).toContain('width: 16px');
    expect(closed).toContain('height: 16px');
    expect(closed).toContain('background: currentColor');
    expect(closed).toContain('-webkit-mask: url("data:image/svg+xml,');
    expect(closed).toMatch(/(?:^|[;\s])mask: url\("data:image\/svg\+xml,/);
    expect(closed).toContain("viewBox='0 0 24 24'");
    expect(closed).toContain("stroke-width='1.8'");
    expect(closed).toContain("d='M9 6l6 6-6 6'");   // expand

    expect(open).toContain('-webkit-mask-image: url("data:image/svg+xml,');
    expect(open).toMatch(/(?:^|[;\s])mask-image: url\("data:image\/svg\+xml,/);
    expect(open).toContain("d='M6 9l6 6 6-6'");     // down
    expect(open).not.toContain("d='M9 6l6 6-6 6'");

    expect(source).not.toMatch(/content: '[▸▾]'/);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/workspaces/watchlist/watchlist.spec.ts --include src/app/workspaces/versions/versions.spec.ts --include src/app/workspaces/guide/guide.spec.ts`
Expected: FAIL — the toggles hold `○`/`◉` text, the "now" tick holds `▲` and no `sb-icon`, and the Guide's `summary::before` rules are `content: '▸'` / `content: '▾'`.

- [ ] **Step 3: The tape toggle draws `plus`/`minus`**

In `frontend/src/app/workspaces/watchlist/watchlist.ts` (`Icon` is already imported, l.33, and in `imports`, l.188), replace the toggle's content line:

```html
        >{{ tape.symbols().includes(row.symbol) ? '◉' : '○' }}</button>
```

with:

```html
        ><sb-icon [name]="tape.symbols().includes(row.symbol) ? 'minus' : 'plus'" title="" /></button>
```

- [ ] **Step 4: The versions marker draws `up`**

In `frontend/src/app/workspaces/versions/versions.ts`, add `import { Icon } from '../../ui/icon';` after `import { Button } from '../../ui/button';` (l.15), add `Icon` to the component's `imports` (l.47): `imports: [Button, ControlRow, Icon, Page, PaginationComponent, Async, Timeline],`, and replace:

```html
        <span class="now">{{ store.lastDate() }} &#9650; now</span>
```

with:

```html
        <span class="now">{{ store.lastDate() }} <sb-icon name="up" title="" /> now</span>
```

- [ ] **Step 5: The Guide's fold marker masks the chevrons**

In `frontend/src/app/workspaces/guide/guide.ts`, replace the two lines:

```css
    sb-guide .md summary::before { content: '▸'; }
    sb-guide .md details[open] > summary::before { content: '▾'; }
```

with (each rule on one line, as the file's other rules are):

```css
    /* The fold marker: icon.ts's expand / down chevrons (24 grid, 1.8 stroke),
       masked because sanitised markdown cannot hold an sb-icon. A mask reads
       alpha only: stroke='black' means "opaque"; the colour is currentColor. */
    sb-guide .md summary::before { content: ''; flex: none; width: 16px; height: 16px; background: currentColor; -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 6l6 6-6 6'/%3E%3C/svg%3E") center / 16px 16px no-repeat; mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 6l6 6-6 6'/%3E%3C/svg%3E") center / 16px 16px no-repeat; }
    sb-guide .md details[open] > summary::before { -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E"); mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E"); }
```

(`summary` is already `display: flex; align-items: center; gap: var(--space-6)`, so the 16px box centres on the summary text. The `//` of `http://` follows a colon, so `stripComments` keeps it.)

- [ ] **Step 6: Reword the colour gate's comment**

In `frontend/src/app/ui/primitives.spec.ts`, replace:

```ts
 * or the space syntax. (?<!&) keeps an HTML numeric character reference out
 * (&#9650; in versions.ts is a triangle glyph, not a colour). Comments are
```

with:

```ts
 * or the space syntax. (?<!&) keeps an HTML numeric character reference
 * (a glyph entity such as &#9650;) from reading as a hex colour; since v241
 * none is left in the sources (icon-glyphs.spec.ts keeps the replaced
 * marker glyphs out), but the lookbehind costs nothing. Comments are
```

- [ ] **Step 7: Run the tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/workspaces/watchlist/watchlist.spec.ts --include src/app/workspaces/versions/versions.spec.ts --include src/app/workspaces/guide/guide.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/type-gates.spec.ts --include src/app/ui/money-colour.spec.ts`
Expected: PASS, 0 failed (the three gates scan the edited styles and templates).

Then: `git grep -n -E "◉|○|&#9650;|▸|▾" -- frontend/src ':!*.spec.ts'`. Expected: no output.

- [ ] **Step 8: Check the three widths**

Per `docs/claude/ui-design.md` (Playwright only, `.env` admin credentials loaded inside the script, never printed): at 390px, 820px and 1440px, `/watchlist`'s Tape column shows a 16px plus on rows outside the tape and a minus on rows in it; tapping one flips the icon and the tape strip (where shown) gains or loses the symbol, without opening the ticker. `/system/versions` shows the date, the up chevron and "now" on one line above the lanes, the icon centred on the text, no tooltip on hover. A Guide chapter with an "Under the hood" `<details>` (`/insights/guide`) shows a right chevron in the summary's muted colour, a down chevron once opened, both centred on the summary text inside its 44px row.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/watchlist/watchlist.spec.ts frontend/src/app/workspaces/versions/versions.ts frontend/src/app/workspaces/versions/versions.spec.ts frontend/src/app/workspaces/guide/guide.ts frontend/src/app/workspaces/guide/guide.spec.ts frontend/src/app/ui/primitives.spec.ts
git commit -m "feat(ui): tape toggle, versions now marker and guide fold marker draw icons (V241-7)"
```

# Phase 3 — the gate

### Task V241-8: Glyph gate and accessible-name guard

**Model:** sonnet — one new spec file, but its regexes must catch every spelling of seven glyphs and a standalone `×` while letting `1.40×`, `1.5 × ATR`, `✓` and `⚠` through, and its guard patterns must match the exact markup four earlier tasks wrote.

**Files:**
- Create: `frontend/src/app/ui/icon-glyphs.spec.ts`

**Interfaces:**
- Consumes: `allSources(): Source[]` (`Source = { name: string; source: string }`, names relative to `src/`, specs and `styles/` excluded) and `stripComments(source: string): string` from `frontend/src/app/ui/testing/all-sources.ts` (exist); the markup written by V241-4 (`direction-arrow.ts`), V241-3 (`recent-activity.ts`, `[size]="20"` added to the status icon), V241-5 (`hint.ts`), V241-6 (`layout.ts`, `data-table/data-table.ts`) and V241-7 (`watchlist.ts`); `plan-cell.ts`'s closed icon as it stands (l.61).
- Produces: two module consts in `icon-glyphs.spec.ts`, `REPLACED_GLYPHS: readonly ReplacedGlyph[]` (`{ name: string; pattern: RegExp }`) and `GUARDED_SITES: readonly GuardedSite[]` (`{ control: string; file: string; names: RegExp }`). Nothing imports them; a later plan that swaps another marker appends a row.

**Why:** the index's success measure — "a source scan fails if a replaced glyph (`ⓘ ▲ ▼ ▾ ▸ ◉ ○`, their character references, or a standalone close `×`) reappears in a template or stylesheet", and spec §4's correction: the accessible-name test guards the direction arrow, the recent-activity icon host, the plan-cell closed icon, the tape toggle, the drawer close button, the panel and row toggles and the `info` trigger. The runtime tests in V241-4..V241-7 prove each control's name in the DOM; this gate is the one table a reader checks, and it fails the moment a refactor drops a name or brings a glyph back. Glyphs inside a value or a sentence stay text and are deliberately not matched (index Decision 4): `×` as multiplication (`1.40×`, `1.5 × ATR`, `×{{ throttle }}`), `→`, `plan-cell.ts`'s banked-target `✓` and `plan-detail.ts`'s server-built `⚠`. `voice-chip.ts`'s hand-rolled speaker svg is not a glyph and is untouched (index Decision 5, open for the controller). The scan runs on comment-stripped sources, so a comment that names an old glyph stays legal.

- [ ] **Step 1: Write the gate**

Create `frontend/src/app/ui/icon-glyphs.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { allSources, stripComments } from './testing/all-sources';

/**
 * v241 (spec v240 §4): the standalone marker glyphs that sb-icon replaced.
 * A text glyph changes shape with the font and sits off the baseline; the
 * icons do not. Each row matches one spelling: the character, its HTML
 * character reference (decimal or hex), its JS or CSS escape, and the close
 * `×` standing alone in an element or a string.
 *
 * Not here on purpose (index Decision 4): a glyph inside a value or a
 * sentence stays text -- `1.40×`, `1.5 × ATR`, `×{{ throttle }}`, `→`,
 * plan-cell's banked-target `✓`, the server-built `⚠ SQUEEZE RISK` prefix.
 */
type ReplacedGlyph = { name: string; pattern: RegExp };

const REPLACED_GLYPHS: readonly ReplacedGlyph[] = [
  { name: 'a marker glyph (ⓘ ▲ ▼ ▾ ▸ ◉ ○)', pattern: /[ⓘ▲▼▾▸◉○]/u },
  { name: 'a marker glyph as a decimal reference', pattern: /&#0*(?:9432|9650|9660|9662|9656|9673|9675);/ },
  { name: 'a marker glyph as a hex reference', pattern: /&#x0*(?:24d8|25b2|25bc|25be|25b8|25c9|25cb);/i },
  { name: 'a marker glyph as a JS or CSS escape', pattern: /\\(?:u\{?)?0*(?:24d8|25b2|25bc|25be|25b8|25c9|25cb)(?![0-9a-f])/i },
  { name: 'a close × alone in an element', pattern: />\s*(?:×|&times;|&#215;|&#xd7;)\s*</i },
  { name: 'a close × alone in a string', pattern: /(['"`])\s*(?:×|&times;|\\u00d7|\\d7)\s*\1/i },
];

/** The REPLACED_GLYPHS rows a piece of source text offends. */
function offences(text: string): string[] {
  return REPLACED_GLYPHS.filter(({ pattern }) => pattern.test(text)).map(({ name }) => name);
}

/**
 * Spec v240 §4 correction: the controls whose glyph became an icon, or that
 * hold an icon beside their name. Each pattern pins the control's accessible
 * name on the control itself and, where the icon sits inside it, the icon's
 * empty title (no tooltip, no second name: never "Close Close").
 */
type GuardedSite = { control: string; file: string; names: RegExp };

const GUARDED_SITES: readonly GuardedSite[] = [
  {
    control: 'direction arrow',
    file: 'app/ui/direction-arrow.ts',
    names: /<span class="arrow"[^>]*role="img"[^>]*\[attr\.aria-label\]="text"[^>]*>\s*<sb-icon \[name\]="icon\(\)" title="" \/>/,
  },
  {
    control: 'recent-activity status icon (named on its own host)',
    file: 'app/workspaces/dashboard/panels/recent-activity.ts',
    names: /<sb-icon \[name\]="icon\(event\)"[^>]*\[attr\.aria-label\]="statusLabel\(event\)"/,
  },
  {
    control: 'plan-cell closed icon (named on the price beside it)',
    file: 'app/ui/plan-cell.ts',
    names: /<sb-icon name="closed" class="closed-icon"[^>]*\/>[\s\S]{0,120}?<span class="closed" \[attr\.aria-label\]="'Closed out at ' \+ fmt\(closedAt\(\)\)"/,
  },
  {
    control: 'watchlist tape toggle',
    file: 'app/workspaces/watchlist/watchlist.ts',
    names: /class="tape-toggle"[^>]*\[attr\.aria-pressed\]="tape\.symbols\(\)\.includes\(row\.symbol\)"[^>]*\[attr\.aria-label\]="'Show ' \+ row\.symbol \+ ' in the live tape'"[^>]*>\s*<sb-icon [^>]*title="" \/>\s*<\/button>/,
  },
  {
    control: 'drawer close button',
    file: 'app/ui/layout.ts',
    names: /<button type="button" class="close" aria-label="Close" \(click\)="requestClose\(\)">\s*<sb-icon name="close" title="" \/>\s*<\/button>/,
  },
  {
    control: 'panel collapse toggle',
    file: 'app/ui/layout.ts',
    names: /class="panel-toggle"[^>]*\[attr\.aria-label\]="\(expanded\(\) \? 'Collapse ' : 'Expand '\) \+ text"[^>]*>\s*<sb-icon \[name\]="expanded\(\) \? 'down' : 'expand'" title="" \/>/,
  },
  {
    control: 'data-table row-detail toggle',
    file: 'app/ui/data-table/data-table.ts',
    names: /class="expander detail-toggle"[^>]*\[attr\.aria-label\]="\(isExpanded\(row\) \? 'Show less for ' : 'Show more for '\) \+ rowLabel\(row\)"[^>]*>\s*<sb-icon \[name\]="isExpanded\(row\) \? 'down' : 'expand'" title="" \/>/,
  },
  {
    control: 'info trigger (sb-hint)',
    file: 'app/ui/hint.ts',
    names: /class="trigger"[^>]*\[attr\.aria-label\]="label\(\)"[^>]*>\s*<sb-icon name="info" title="" \/>/,
  },
];

const SOURCES = allSources();

describe('replaced glyphs stay replaced (v241, spec v240 §4)', () => {
  // The patterns first: a gate that matches nothing passes everything.
  it.each([
    "{{ open ? '▾' : '▸' }}",
    '{{ store.lastDate() }} &#9650; now',
    '&#x25B2;',
    '&#x25b8;',
    "content: '\\25B8'",
    "'\\u25BC'",
    "'\\u{25C9}'",
    'ⓘ',
    "{{ on ? '◉' : '○' }}",
    '(click)="requestClose()">×</button>',
    '<button> &times; </button>',
    "content: '×'",
    '"\\u00d7"',
  ])('catches %s', (text) => {
    expect(offences(text)).not.toEqual([]);
  });

  it.each([
    '1.40×',
    '1.5 × ATR',
    'Drawdown throttle at ×{{ fmt(store.throttleMultiplier()) }}',
    'shares × stop',
    '115.26 → 123.05',
    '`${fmt} ✓`',
    "line.startsWith('⚠')",
    '#9650 is a number, not a reference',
    "content: '\\25B80'",
    '',
  ])('keeps %j as text', (text) => {
    expect(offences(text)).toEqual([]);
  });

  it('finds none in any template, stylesheet or component', () => {
    const found = SOURCES.flatMap(({ name, source }) =>
      offences(stripComments(source)).map((offence) => `${name}: ${offence}`));
    expect(found).toEqual([]);
  });

  it('really scans the sources it guards', () => {
    // An empty or misrooted scan would pass the test above vacuously.
    const names = new Set(SOURCES.map(({ name }) => name));
    expect(names.size).toBeGreaterThan(100);
    for (const file of [...GUARDED_SITES.map((site) => site.file), 'app/workspaces/versions/versions.ts', 'app/workspaces/guide/guide.ts']) {
      expect(names.has(file), file).toBe(true);
    }
  });
});

describe('every swapped control keeps its accessible name (v241, spec v240 §4 correction)', () => {
  it.each(GUARDED_SITES.map((site) => [site.control, site] as const))('%s', (_control, site) => {
    const source = SOURCES.find(({ name }) => name === site.file)?.source;
    expect(source, site.file).toBeDefined();
    expect(stripComments(source!)).toMatch(site.names);
  });

  it('guards each control the spec names, once', () => {
    const controls = GUARDED_SITES.map((site) => site.control);
    expect(new Set(controls).size).toBe(controls.length);
    expect(controls).toHaveLength(8);
  });
});
```

- [ ] **Step 2: Run it**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/icon-glyphs.spec.ts`
Expected: PASS, 0 failed — V241-4..V241-7 removed every replaced glyph and wrote the guarded markup. A failure here is a real finding, not a pattern to loosen: a `found` entry names the file and the spelling still present (fix the site); a guard failure names the control whose markup drifted from what its task wrote (read that task's template step and the file, and fix whichever is wrong; change a `names` pattern only when the markup is right and the pattern is stale, and keep the accessible name in it).

- [ ] **Step 3: Prove the gate bites**

Temporarily change `frontend/src/app/ui/layout.ts`'s drawer close back to `...(click)="requestClose()">×</button>` and run the same command.
Expected: FAIL — `finds none in any template, stylesheet or component` lists `app/ui/layout.ts: a close × alone in an element`, and `drawer close button` fails its guard.
Restore the file: `git checkout -- frontend/src/app/ui/layout.ts`, re-run, expect PASS. (`git status --short` then shows only the new spec.)

- [ ] **Step 4: Run the neighbouring gates once**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/icon-glyphs.spec.ts --include src/app/ui/icon.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/type-gates.spec.ts --include src/app/ui/money-colour.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/icon-glyphs.spec.ts
git commit -m "test(ui): gate the replaced marker glyphs and the swapped controls' accessible names (V241-8)"
```
