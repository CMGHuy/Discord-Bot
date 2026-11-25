# v247 — Doctena night, plan 3 of 5: Shell and navigation — Part 3: Rail and wordmark

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V247-9" -A 400 <this file>`).

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) §5 (64px icon rail, tooltips, active bar, order, brand), §8/§9 (long-press ignores a mouse; three devices), §11 (Rail line, long-press host links gate, panel-driven nav colour gate).
**Index:** [2026-11-23-v247-doctena-night-shell-and-navigation_0-index.md](2026-11-23-v247-doctena-night-shell-and-navigation_0-index.md) — Goal, Global Constraints, Decisions (6, 7, 10, 11 and 12 above all), Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks: V247-8 (the 64px icon rail: `aria-label`, one anchored hint per link, the accent bar), V247-9 (rail long-press opens the hint; the layout audit's `rail-label` check redefined), V247-10 (the "Bomeo Capital" wordmark and `LABELS.brand`). All three edit `shell/shell.html`, `shell/shell.css` and `shell/shell.spec.ts`, so they run **in id order**, one commit each.

Runs after part 1 (V247-2b has already flipped the rail's nav rows in `shell.spec.ts`: seven destinations with Calendar after Trades, route stubs `calendar` and `calendar/:date`, the `lights exactly one entry` rows `['/calendar', 'Calendar']`) and part 2 (`HINT_HOVER_DELAY_MS`, `Hint.openDelay`, `Hint.dismiss()`, `Hint.openPinned()`, `LongPress`/`sbLongPress`, the `.sb-long-press` rule in `styles.css`).

All frontend commands run from the worktree root; `--include` paths are relative to `frontend/`. Shell specs mount through the file's existing `shellProviders()` / `createShell()` helpers. jsdom has no `PointerEvent` constructor: pointer events are a `MouseEvent` with `pointerType` and `pointerId` defined on it, as `ui/long-press.spec.ts` does. Timer tests fake only `setTimeout`/`clearTimeout`; the hint's open effect uses `requestAnimationFrame`, which stays real.

The three-width check (spec §9): the rail shows at 820 and 1440px and is hidden at 390px (`@media (max-width: 639px) { .rail { display: none; } }`, unchanged). V247-16 drives the rail tooltip in a real browser at all three widths and runs `layout-audit.mjs`, whose `rail-label` check V247-9 rewrites.

---

# Phase 3 — Rail and wordmark

### Task V247-8: Rail: 64px, icons only, `aria-label`, one anchored hint per link, accent bar

**Model:** sonnet — a shell template and stylesheet change pinned by a dozen source-scan and DOM tests across three spec files; mechanical but wide.

**Files:**
- Modify: `frontend/src/app/shell/shell.html:1-38` (rail comment and the two link lists)
- Modify: `frontend/src/app/shell/shell.css:1-9` (`.shell`), `:57-107` (`.rail-link` through the active rules)
- Modify: `frontend/src/app/shell/shell.ts:63-70` (class doc comment), import line 30, the field block after `railFoot` (line 115)
- Test: `frontend/src/app/shell/shell.spec.ts` (`describe('shell navigation')` CSS pins at 317-334; `describe('shell labelled rail (v202 §3)')` at 571-712; `sizes the rail and the bar` at 738-748)
- Test: `frontend/src/app/ui/hit-area.spec.ts:62-65` (the `GROWN` rows that pin the 64x52 rail entry). It pins `.rail-link`'s size, so it moves with it.

**Interfaces:**
- Consumes (V247-5): `export const HINT_HOVER_DELAY_MS = 300` and `Hint.openDelay = input(0)` from `ui/hint.ts`. Decision 6: the delay applies to hover only; focus opens at once. Decision 7: opening any hint dismisses the open one.
- Produces (consumed by V247-9):
  - `Shell.railHintDelay`: `protected readonly railHintDelay = HINT_HOVER_DELAY_MS;`
  - Per rail link, inside its `<li>`: the anchor `<a #link class="rail-link" ...>` and, right after it, `<sb-hint #hint [anchor]="link" [text]="entry.label" [openDelay]="railHintDelay" />`. V247-9 adds `sbLongPress (longPress)="hint.openPinned()"` to that anchor.
  - The rail link has no `.rail-pill` and no `.rail-label`; its only child is `<sb-icon [name]="entry.icon" title="" [size]="24" />`.

Spec §5: the rail narrows to 64px; each entry is a 44×44 target with a 24px icon; `.rail-label` leaves the DOM and the link keeps `aria-label="<label>"`; an `sb-hint` anchored to each entry shows the label to the right (the default `placement`, `'beside'`). The active entry is the `--accent-soft` fill on the 44×44 link plus a 3px `--accent` bar on the rail's inner (right) edge (Decision 11), and `aria-current="page"`. Hover, focus and Escape come from `Hint`'s anchor mode, which already binds them. The long-press opener is V247-9.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/shell/shell.spec.ts`, imports. Add below `import { styleRules } from '../ui/testing/style-rules';`:

```ts
import { HINT_HOVER_DELAY_MS } from '../ui/hint';
import { POPOVER_OPEN_ATTR } from '../testing/popover-polyfill';
```

`describe('shell navigation')`: replace the two tests `marks the active entry with the pill and a brighter glyph and label` and `sizes each entry 64x52, a 24px icon over a micro label` (lines 317-334) with:

```ts
  it('marks the active entry with the accent-soft fill and a 3px accent bar on the inner edge (v247 §5)', () => {
    const css = readSource('src/app/shell/shell.css');
    const active = css.match(/^\.rail-link\.active \{[^}]*\}/m)?.[0] ?? '';
    expect(active).toContain('background: var(--accent-soft);');
    expect(active).toContain('color: var(--text);');
    const bar = css.match(/^\.rail-link\.active::after \{[^}]*\}/m)?.[0] ?? '';
    for (const declaration of ['content: "";', 'position: absolute;', 'width: 3px;',
      'right: calc((var(--rail-width) - 44px) / -2);', 'border-radius: var(--pill-radius);',
      'background: var(--accent);']) {
      expect(bar, declaration).toContain(declaration);
    }
    // The bar is placed against the link, so the link is its containing block.
    const link = css.match(/^\.rail-link \{[^}]*\}/m)?.[0] ?? '';
    expect(link).toContain('position: relative;');
    expect(link).toContain('color: var(--text-muted);');
    expect(css).not.toMatch(/sb-nav-indicator|border-left-color|\.rail-pill/);
  });

  it('sizes each entry 44x44 with a 24px icon and no label rule (v247 §5)', () => {
    const css = readSource('src/app/shell/shell.css');
    const link = css.match(/^\.rail-link \{[^}]*\}/m)?.[0] ?? '';
    expect(link).toContain('width: 44px;');
    expect(link).toContain('height: 44px;');
    expect(link).not.toContain('flex-direction: column;');
    // The icon draws at 24 through sb-icon's size input (v240 §4); no rule
    // reaches into the svg to resize it.
    expect(styleRules('shell.css', css).filter((rule) => /sb-icon\s+svg/.test(rule.selector))).toEqual([]);
    expect(css).not.toMatch(/\.rail-label/);
  });
```

`describe('shell labelled rail (v202 §3)')`: rename it `describe('shell icon rail (v247, spec v240 §5)')`. Replace `labelOf` (line 592) with:

```ts
  /** v247: a rail link is named by its aria-label alone; it draws no text. */
  const labelOf = (link: Element) => link.getAttribute('aria-label') ?? '';
  /** The role="tooltip" popover the link's aria-describedby points at (its sb-hint). */
  const tooltipOf = (el: HTMLElement, link: Element) =>
    el.querySelector(`[id="${link.getAttribute('aria-describedby')}"]`) as HTMLElement;
  const isOpen = (tooltip: HTMLElement) => tooltip.hasAttribute(POPOVER_OPEN_ATTR);
  async function settle(fixture: ComponentFixture<Shell>) {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }
  const railLink = (el: HTMLElement, path: string) =>
    el.querySelector<HTMLAnchorElement>(`nav.rail a.rail-link[href="${path}"]`)!;
```

The two tests that call `labelOf` on the lists (`draws seven labelled destinations, …` and `drops the System foot list for a viewer …`) and the `lights exactly one entry` table keep their bodies: the new `labelOf` reads the same labels from `aria-label`.

Replace the test `draws each entry as its icon over its visible label, with no hint and no title` with these five:

```ts
  it('names each entry by aria-label alone, draws no label, and gives it one anchored hint with that name', async () => {
    const { el } = await mount();
    const links = [...el.querySelectorAll<HTMLAnchorElement>('nav.rail a.rail-link')];
    expect(links.map((a) => a.getAttribute('href'))).toEqual(NAV_ENTRIES.map((entry) => entry.path));
    expect(el.querySelector('nav.rail .rail-label, nav.rail .rail-pill')).toBeNull();
    links.forEach((link, index) => {
      const label = NAV_ENTRIES[index].label;
      expect(link.getAttribute('aria-label'), label).toBe(label);
      expect(link.hasAttribute('title'), label).toBe(false);
      // No visible text: the icon is the link's only child, and it is unnamed.
      expect(link.textContent!.trim(), label).toBe('');
      expect([...link.children].map((child) => child.tagName.toLowerCase()), label).toEqual(['sb-icon']);
      expect(link.querySelector(':scope > sb-icon')!.getAttribute('title'), label).toBe('');
      // One hint per entry, beside the link in its <li>, describing it with the same name.
      expect(link.parentElement!.querySelectorAll('sb-hint'), label).toHaveLength(1);
      const tooltip = tooltipOf(el, link);
      expect(tooltip.getAttribute('role'), label).toBe('tooltip');
      expect(tooltip.textContent!.trim(), label).toBe(label);
      expect(isOpen(tooltip), label).toBe(false);
    });
    expect(el.querySelectorAll('nav.rail ul.nav button')).toHaveLength(0);
  });

  it('gives a viewer a hint on every entry it sees and none naming System (v207)', async () => {
    asViewer();
    const { el } = await mount();
    const links = [...el.querySelectorAll<HTMLAnchorElement>('nav.rail a.rail-link')];
    expect(links.map(labelOf)).toEqual(['Dashboard', 'Watchlist', 'Trades', 'Calendar', 'Risk', 'Insights']);
    expect(el.querySelectorAll('nav.rail li > sb-hint')).toHaveLength(links.length);
    expect([...el.querySelectorAll('nav.rail li [role="tooltip"]')].map((tip) => tip.textContent!.trim()))
      .not.toContain('System');
  });

  it('opens the entry hint at once on keyboard focus, and closes it on blur and on Escape', async () => {
    const { fixture, el } = await mount();
    const link = railLink(el, '/watchlist');
    const tooltip = tooltipOf(el, link);
    link.dispatchEvent(new FocusEvent('focus'));
    await settle(fixture);
    expect(isOpen(tooltip)).toBe(true);
    link.dispatchEvent(new FocusEvent('blur'));
    await settle(fixture);
    expect(isOpen(tooltip)).toBe(false);
    link.dispatchEvent(new FocusEvent('focus'));
    await settle(fixture);
    expect(isOpen(tooltip)).toBe(true);
    link.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(isOpen(tooltip)).toBe(false);
  });

  it('opens the entry hint on hover only after the hint delay, and a leave before it cancels', async () => {
    const { fixture, el } = await mount();
    const link = railLink(el, '/risk');
    const tooltip = tooltipOf(el, link);
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      link.dispatchEvent(new MouseEvent('mouseenter'));
      fixture.detectChanges();
      vi.advanceTimersByTime(HINT_HOVER_DELAY_MS - 1);
      fixture.detectChanges();
      expect(isOpen(tooltip)).toBe(false);
      vi.advanceTimersByTime(1);
      fixture.detectChanges();
      expect(isOpen(tooltip)).toBe(true);
      link.dispatchEvent(new MouseEvent('mouseleave'));
      fixture.detectChanges();
      expect(isOpen(tooltip)).toBe(false);
      // A pass over the link shorter than the delay never opens it.
      link.dispatchEvent(new MouseEvent('mouseenter'));
      vi.advanceTimersByTime(HINT_HOVER_DELAY_MS - 50);
      link.dispatchEvent(new MouseEvent('mouseleave'));
      vi.advanceTimersByTime(HINT_HOVER_DELAY_MS);
      fixture.detectChanges();
      expect(isOpen(tooltip)).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows one rail tooltip at a time', async () => {
    const { fixture, el } = await mount();
    const first = railLink(el, '/trades');
    const second = railLink(el, '/calendar');
    first.dispatchEvent(new FocusEvent('focus'));
    await settle(fixture);
    expect(isOpen(tooltipOf(el, first))).toBe(true);
    second.dispatchEvent(new FocusEvent('focus'));
    await settle(fixture);
    expect(isOpen(tooltipOf(el, second))).toBe(true);
    expect(isOpen(tooltipOf(el, first))).toBe(false);
    expect(el.querySelectorAll(`nav.rail li [role="tooltip"][${POPOVER_OPEN_ATTR}]`)).toHaveLength(1);
  });
```

`ComponentFixture` is already imported at the top of the file (`import { ComponentFixture, TestBed } from '@angular/core/testing';`).

In `draws the brand and every destination icon at 24px through sb-icon size (v240 §4)`, change the selector:

```ts
    const svgs = [...el.querySelectorAll(
      'nav.rail > a.rail-brand > sb-icon svg, nav.rail a.rail-link > sb-icon svg',
    )];
```

`describe('shell top bar (v195 Phase 3, correction 9)')`, test `sizes the rail and the bar from two shell tokens, with no animated width`: `expect(shell).toContain('--rail-width: 80px;');` becomes `expect(shell).toContain('--rail-width: 64px;');`.

`frontend/src/app/ui/hit-area.spec.ts`, the first two `GROWN` rows and their comment (lines 63-65) become:

```ts
    // v247 (spec v240 §5): a 44x44 rail entry is the 44px hit size at every width.
    ['src/app/shell/shell.css', '.rail-link', 'width: 44px'],
    ['src/app/shell/shell.css', '.rail-link', 'height: 44px'],
```

The `PADDED` row for `overview.ts` already reads `/calendar` (V247-3 flipped it); leave it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/shell.spec.ts --include src/app/ui/hit-area.spec.ts`
Expected: FAIL. The CSS pins fail (`width: 44px`, `.rail-link.active::after`, `--rail-width: 64px`), and so does the aria-label/hint test (no `aria-label`, no `sb-hint` in the `<li>`). The viewer hint count fails too. Focus, hover and one-at-a-time fail because `tooltipOf` finds no tooltip (`null`). The `lights exactly one entry` rows fail because `labelOf` reads `aria-label`, which is absent today.

- [ ] **Step 3: Implement**

3a. `frontend/src/app/shell/shell.ts`. Line 30 becomes:

```ts
import { HINT_HOVER_DELAY_MS, Hint } from '../ui/hint';
```

In the class doc comment (lines 63-70), replace the paragraph that starts `**One rail state.**` with:

```ts
 * **One rail state.** The rail is always 64px, each entry a 24px icon in a
 * 44x44 link named by its aria-label, with an anchored sb-hint that shows
 * the name on hover (after HINT_HOVER_DELAY_MS), on focus and on a touch
 * long-press (v247, spec v240 §5). There is no expanded sidebar, no overlay
 * and no stored collapse choice. The server's pre-v195 sidebar preference
 * is left in place (an older image reads it again on rollback) and is never
 * read or written here.
```

Below `railFoot` (line 115), add:

```ts
  /** The rail hints wait this long on hover, so a pointer crossing the rail
   *  does not flash every label (v247 Decision 6); focus opens at once. */
  protected readonly railHintDelay = HINT_HOVER_DELAY_MS;
```

3b. `frontend/src/app/shell/shell.html`, the comment (lines 2-6) becomes:

```html
  <!-- v247 (spec v240 §5): a 64px icon rail. The diamond mark heads it, the
       six work destinations follow, System sits at the foot. Each entry is a
       24px icon in a 44x44 link named by its aria-label; its sb-hint shows
       the name beside it on hover (after the hint delay), on focus and on a
       touch long-press, one at a time. The active entry has the accent-soft
       fill and the accent bar on the rail's inner edge. "Active" comes from
       the nav model (navHere), not routerLinkActive, so /plans/7 lights Trades. -->
```

Replace the work list's `@for` block (lines 14-22) with:

```html
      @for (entry of railWork(); track entry.path) {
        <li>
          <a #link class="rail-link" [routerLink]="entry.path"
             [attr.aria-label]="entry.label"
             [class.active]="entry.path === activePath()"
             [attr.aria-current]="entry.path === activePath() ? 'page' : null">
            <sb-icon [name]="entry.icon" title="" [size]="24" />
          </a>
          <sb-hint #hint [anchor]="link" [text]="entry.label" [openDelay]="railHintDelay" />
        </li>
      }
```

and the foot list's `@for` block (lines 28-36) with the same markup:

```html
        @for (entry of railFoot(); track entry.path) {
          <li>
            <a #link class="rail-link" [routerLink]="entry.path"
               [attr.aria-label]="entry.label"
               [class.active]="entry.path === activePath()"
               [attr.aria-current]="entry.path === activePath() ? 'page' : null">
              <sb-icon [name]="entry.icon" title="" [size]="24" />
            </a>
            <sb-hint #hint [anchor]="link" [text]="entry.label" [openDelay]="railHintDelay" />
          </li>
        }
```

`#link` and `#hint` are per-iteration template refs; `#hint` stays unused until V247-9 wires the long-press to it. `sb-hint` in anchor mode is `display: contents` (`:host(.anchored)`), so it takes no room in the `<li>`.

3c. `frontend/src/app/shell/shell.css`. Lines 2-4 of the `.shell` rule become:

```css
  /* v247 (spec v240 §5): a 64px icon rail and a 40px top bar. One state,
     so nothing here animates. */
  --rail-width: 64px;
```

Replace everything from the comment `/* 64x52 at every width: past the 44px touch size, so no .sb-hit. */` down to the end of the `.rail-link.active { color: var(--text); }` rule (lines 57-107: `.rail-link`, its hover and focus rules, `.rail-pill`, its hover rule, `.rail-label` and both active rules) with:

```css
/* 44x44 at every width: the touch size itself, so no .sb-hit. The 24px icon
   is sb-icon's size input; the link is the bar's containing block. */
.rail-link {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 44px;
  height: 44px;
  border-radius: var(--control-radius);
  color: var(--text-muted);
  text-decoration: none;
  transition: color var(--transition), background var(--transition);
}
.rail-link:hover { color: var(--text); background: var(--surface-raised); }
.rail-link:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }

/* Three cues, so the active entry survives a monochrome reading: the fill,
   the bar on the rail's inner edge, and aria-current. Accent, never mint:
   mint means "gain" (spec v240 §1). After :hover, so a hovered active entry
   keeps its fill. */
.rail-link.active {
  color: var(--text);
  background: var(--accent-soft);
}
/* The link sits centred in the rail, (rail - 44px) / 2 in from each edge;
   the bar sits that far out, flush with the rail's right edge. */
.rail-link.active::after {
  content: "";
  position: absolute;
  top: var(--space-8);
  bottom: var(--space-8);
  right: calc((var(--rail-width) - 44px) / -2);
  width: 3px;
  border-radius: var(--pill-radius);
  background: var(--accent);
}
```

`.rail` keeps `overflow-x: hidden`: the bar ends at the rail's edge, so at most a sub-pixel of it, under the rail's border, is cut.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/shell.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/money-colour.spec.ts --include src/app/ui/type-gates.spec.ts`
Expected: PASS, 0 failed. `money-colour.spec.ts` still finds `.rail-link.active` among the shell nav rules and no `--pos`/`--neg` in them; the new `::after` rule reads `--accent` only.

Then check that the delay test is not vacuous: temporarily delete `[openDelay]="railHintDelay"` from the work list's `<sb-hint>` and re-run `shell.spec.ts`. `opens the entry hint on hover only after the hint delay` must fail, because the hint opens at 299ms. Restore the binding.

- [ ] **Step 5: Confirm no rail label survives in the app**

Run: `git grep -n "rail-label\|rail-pill" -- frontend/src`
Expected: only the `not.toMatch` / `toBeNull` assertions in `shell.spec.ts`. (`frontend/scripts/layout-audit.mjs` still reads `.rail-label`; V247-9 rewrites it. The `admin-page-timing.mjs` fallback V247-4 added stays harmless: it matches by `aria-label` first.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.spec.ts frontend/src/app/ui/hit-area.spec.ts
git commit -m "feat(v247): 64px icon rail -- aria-label names, one anchored hint per link, accent bar on the active entry"
```

### Task V247-9: Rail long-press opens the hint; layout audit's `rail-label` check redefined

**Model:** sonnet — wires two contracts from part 2 into the shell under fake timers, and rewrites a Playwright audit check plus its pure verdict; small but cross-file.

**Files:**
- Modify: `frontend/src/app/shell/shell.html` (the two rail `<a #link class="rail-link">` anchors V247-8 wrote)
- Modify: `frontend/src/app/shell/shell.ts` (imports; the `imports: [...]` array, lines 85-90)
- Test: `frontend/src/app/shell/shell.spec.ts` (`describe('shell icon rail (v247, spec v240 §5)')`, renamed by V247-8)
- Modify: `frontend/scripts/layout-audit-lib.mjs:199-217` (`RAIL_MIN_WIDTH` comment, `railLabelVerdict`)
- Test: `frontend/scripts/layout-audit-lib.test.mjs:369-388` (the three `railLabelVerdict` tests)
- Modify: `frontend/scripts/layout-audit.mjs:22-24` (header), `:347-393` (`railEntry`, `railFinding`, `auditRailLabels`)

**Interfaces:**
- Consumes (V247-6): `Hint.openPinned(): void`. It opens and pins at once and closes on the next `pointerdown` anywhere or on Escape pressed anywhere; hover and focus ending do not close it.
- Consumes (V247-7): `LONG_PRESS_MS = 500` and `@Directive({ selector: '[sbLongPress]' }) class LongPress { readonly longPress = output<void>() }` from `ui/long-press.ts`. The directive sets host class `sb-long-press`, fires only for `touch`/`pen`, and swallows the click after a fired press.
- Consumes (V247-8): the per-link refs `#link` / `#hint`; `Shell.railHintDelay`.
- Produces: `railLabelVerdict({ name, tooltip })` in `frontend/scripts/layout-audit-lib.mjs`, returning `{ ok: true, reason: null }` or `{ ok: false, reason }` with reason `'no-name'`, then `'no-tooltip'`, then `'tooltip-not-name'` (Decision 12). The `CHECKS` id stays `'rail-label'`.

Spec §5/§6: a touch held 500ms on a rail entry opens its tooltip, navigates nowhere, and the tooltip stays until the next touch or Escape. Spec §8: a mouse never fires it (hover covers a mouse). Spec §11: long-press host links carry `-webkit-touch-callout: none` (the `.sb-long-press` rule V247-7 put in `styles.css`). Decision 12: the audit's `rail-label` check stops looking for a visible `.rail-label`. It now needs an accessible name, plus an `aria-describedby` that points at a `role="tooltip"` whose text equals that name.

- [ ] **Step 1: Write the failing shell tests**

`frontend/src/app/shell/shell.spec.ts`, imports. Add below the `HINT_HOVER_DELAY_MS` import V247-8 added:

```ts
import { LONG_PRESS_MS } from '../ui/long-press';
```

Inside `describe('shell icon rail (v247, spec v240 §5)')`, directly after the `railLink` helper, add:

```ts
  /** jsdom has no PointerEvent: a MouseEvent carrying pointerType and pointerId
   *  is what sbLongPress reads (ui/long-press.spec.ts does the same). */
  function pointer(type: string, pointerType = 'touch'): MouseEvent {
    const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX: 30, clientY: 120 });
    Object.defineProperty(event, 'pointerType', { value: pointerType });
    Object.defineProperty(event, 'pointerId', { value: 1 });
    return event;
  }

  /** Holds a pointer on the link for LONG_PRESS_MS and lifts it. Only
   *  setTimeout is faked: the hint's requestAnimationFrame stays real. */
  async function hold(fixture: ComponentFixture<Shell>, link: Element, pointerType = 'touch') {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      link.dispatchEvent(pointer('pointerdown', pointerType));
      vi.advanceTimersByTime(LONG_PRESS_MS);
      link.dispatchEvent(pointer('pointerup', pointerType));
    } finally {
      vi.useRealTimers();
    }
    await settle(fixture);
  }

  const tap = () => new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
```

Append these tests at the end of the same describe:

```ts
  it('makes every rail link a long-press host, and the brand mark not one', async () => {
    const { el } = await mount();
    const links = [...el.querySelectorAll('nav.rail a.rail-link')];
    expect(links).toHaveLength(NAV_ENTRIES.length);
    for (const link of links) expect(link.classList.contains('sb-long-press'), labelOf(link)).toBe(true);
    expect(el.querySelector('nav.rail a.rail-brand')!.classList.contains('sb-long-press')).toBe(false);
  });

  it('opens the entry hint on a 500ms touch hold and not a moment before', async () => {
    const { fixture, el } = await mount();
    const link = railLink(el, '/calendar');
    const tooltip = tooltipOf(el, link);
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      link.dispatchEvent(pointer('pointerdown'));
      vi.advanceTimersByTime(LONG_PRESS_MS - 1);
      fixture.detectChanges();
      expect(isOpen(tooltip)).toBe(false);
      vi.advanceTimersByTime(1);
    } finally {
      vi.useRealTimers();
    }
    await settle(fixture);
    expect(isOpen(tooltip)).toBe(true);
    expect(tooltip.textContent!.trim()).toBe('Calendar');
  });

  it('keeps the held-open hint after the finger lifts, and swallows the click so it navigates nowhere', async () => {
    const { fixture, el } = await mount();
    const router = TestBed.inject(Router);
    const before = router.url;
    const link = railLink(el, '/trades');
    await hold(fixture, link);
    expect(isOpen(tooltipOf(el, link))).toBe(true);
    link.dispatchEvent(tap());
    await settle(fixture);
    expect(router.url).toBe(before);
    expect(isOpen(tooltipOf(el, link))).toBe(true);
  });

  it('closes the held-open hint on the next touch anywhere, and on Escape', async () => {
    const { fixture, el } = await mount();
    const link = railLink(el, '/risk');
    await hold(fixture, link);
    expect(isOpen(tooltipOf(el, link))).toBe(true);
    document.body.dispatchEvent(pointer('pointerdown'));
    await settle(fixture);
    expect(isOpen(tooltipOf(el, link))).toBe(false);

    await hold(fixture, link);
    expect(isOpen(tooltipOf(el, link))).toBe(true);
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(isOpen(tooltipOf(el, link))).toBe(false);
  });

  it('never opens on a mouse held down, and that click still navigates (hover covers a mouse)', async () => {
    const { fixture, el } = await mount();
    const link = railLink(el, '/trades');
    await hold(fixture, link, 'mouse');
    expect(isOpen(tooltipOf(el, link))).toBe(false);
    link.dispatchEvent(tap());
    await settle(fixture);
    expect(TestBed.inject(Router).url).toBe('/trades');
  });

  it('moves a held-open hint to the entry held next (one at a time)', async () => {
    const { fixture, el } = await mount();
    const first = railLink(el, '/dashboard');
    const second = railLink(el, '/insights');
    await hold(fixture, first);
    expect(isOpen(tooltipOf(el, first))).toBe(true);
    await hold(fixture, second);
    expect(isOpen(tooltipOf(el, second))).toBe(true);
    expect(isOpen(tooltipOf(el, first))).toBe(false);
  });
```

The rail describe's route stubs (V247-2b) hold `trades`, `calendar`, `calendar/:date`, `plans/:id`, `insights/analytics` and `system/versions`. The mouse test navigates to `/trades`, which is stubbed. `/dashboard` and `/insights` are only held, never clicked.

- [ ] **Step 2: Run the shell tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/shell.spec.ts`
Expected: FAIL. The new tests fail because no rail link has `sb-long-press`, a 500ms touch hold opens nothing, and the click after a hold navigates to `/trades`. The mouse test passes already, and that is expected: it pins that the wiring added below never fires for a mouse.

- [ ] **Step 3: Wire the long-press in the shell**

`frontend/src/app/shell/shell.ts`: add below `import { Icon } from '../ui/icon';`:

```ts
import { LongPress } from '../ui/long-press';
```

and add `LongPress` to the component's `imports` array, after `Hint`:

```ts
  imports: [
    RouterOutlet, RouterLink, AlarmChip, ToastHost,
    ScanProgressStrip, Icon, Hint, LongPress, Breadcrumb, KillswitchChip, VoiceChip, ProfileMenu, Tape,
    Button, PhoneTabBar, MoreSheet, CommandPalette, RefresherBanner, SectionTabs,
    LiveDock, LiveEdgeTab, LiveStrip, LiveSheet, ReadOnlyBadge, ShockPill,
  ],
```

`frontend/src/app/shell/shell.html`: both rail anchors (work list and foot list) gain the directive and its output. Each opening tag becomes:

```html
          <a #link class="rail-link" [routerLink]="entry.path"
             [attr.aria-label]="entry.label"
             [class.active]="entry.path === activePath()"
             [attr.aria-current]="entry.path === activePath() ? 'page' : null"
             sbLongPress (longPress)="hint.openPinned()">
```

(The foot list's copy is indented two more spaces.) `hint` is the `#hint` ref on the `<sb-hint>` after the anchor, in the same `@for` iteration. In the rail comment (lines 2-8), the words `on a touch long-press` stay as they are: V247-8 wrote them for this wiring.

- [ ] **Step 4: Run the shell tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/shell.spec.ts --include src/app/ui/long-press.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 5: Write the failing audit-verdict tests**

`frontend/scripts/layout-audit-lib.test.mjs`: replace the comment and the three `railLabelVerdict` tests (lines 369-388, from `// railLabelVerdict (v202 §3)` to the end of `a missing label, a hidden one and a name without it each fail`) with:

```js
// railLabelVerdict (v247 Decision 12): an icon-rail entry draws no label. It needs an accessible
// name and a role="tooltip" (its sb-hint, through aria-describedby) whose text is that name.
test('railLabelVerdict: a named entry whose tooltip reads its name passes', () => {
  assert.deepEqual(railLabelVerdict({ name: 'Dashboard', tooltip: 'Dashboard' }), { ok: true, reason: null });
  // Whitespace around and inside either side is not a difference.
  assert.deepEqual(railLabelVerdict({ name: ' Calendar ', tooltip: '\n   Calendar\n' }), { ok: true, reason: null });
});

test('railLabelVerdict: no accessible name fails no-name first, whatever the tooltip does', () => {
  for (const name of ['', '   ', null, undefined]) {
    assert.deepEqual(railLabelVerdict({ name, tooltip: 'Risk' }), { ok: false, reason: 'no-name' }, String(name));
    assert.deepEqual(railLabelVerdict({ name, tooltip: null }), { ok: false, reason: 'no-name' }, String(name));
  }
});

test('railLabelVerdict: no tooltip fails no-tooltip; an empty or different one fails tooltip-not-name', () => {
  for (const tooltip of [null, undefined]) {
    assert.deepEqual(railLabelVerdict({ name: 'Risk', tooltip }), { ok: false, reason: 'no-tooltip' }, String(tooltip));
  }
  assert.deepEqual(railLabelVerdict({ name: 'Risk' }), { ok: false, reason: 'no-tooltip' });
  for (const tooltip of ['', '  ', 'Trades', 'risk', 'Risk page']) {
    assert.deepEqual(railLabelVerdict({ name: 'Risk', tooltip }), { ok: false, reason: 'tooltip-not-name' }, tooltip);
  }
});

test('railLabelVerdict: the pre-v247 visible-label fields no longer pass an entry', () => {
  assert.deepEqual(railLabelVerdict({ name: 'Risk', label: 'Risk', labelVisible: true }), { ok: false, reason: 'no-tooltip' });
});
```

Run: `node --test frontend/scripts/layout-audit-lib.test.mjs`
Expected: FAIL. The old verdict returns `no-label` where `no-tooltip` or `tooltip-not-name` is expected, and the passing case fails as `no-label`.

- [ ] **Step 6: Rewrite the verdict**

`frontend/scripts/layout-audit-lib.mjs`, lines 199-217 (the `RAIL_MIN_WIDTH` comment through the end of `railLabelVerdict`) become:

```js
/** Narrowest width the icon rail shows at: below it (the shell's 639px phone breakpoint) the bottom
 *  tab bar navigates, and its tabs carry visible labels. */
export const RAIL_MIN_WIDTH = 640;

/** Collapses runs of whitespace and trims, so a tooltip's template indentation is no difference. */
const squash = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();

/**
 * The rail-label check's verdict (v247 Decision 12, spec v240 §5) on one icon-rail entry: its
 * accessible name and the text of the role="tooltip" its aria-describedby points at (null when
 * none does; layout-audit.mjs auditRailLabels). No name fails first, then no tooltip, then a
 * tooltip whose text is not the name. The id stays 'rail-label': CHECKS is pinned.
 */
export function railLabelVerdict(entry) {
  const name = squash(entry.name);
  if (!name) return { ok: false, reason: 'no-name' };
  if (entry.tooltip === null || entry.tooltip === undefined) return { ok: false, reason: 'no-tooltip' };
  if (squash(entry.tooltip) !== name) return { ok: false, reason: 'tooltip-not-name' };
  return { ok: true, reason: null };
}
```

Run: `node --test frontend/scripts/layout-audit-lib.test.mjs`
Expected: PASS, 0 failed (the `CHECKS` and `RAIL_MIN_WIDTH` tests are unchanged and still pass).

- [ ] **Step 7: Point the audit at the tooltip**

`frontend/scripts/layout-audit.mjs`, header lines 22-24 (the `rail-label` entry) become:

```js
 *   rail-label an icon-rail entry (nav.rail a.rail-link; widths >= 640 only, the phone navigates by
 *              its tab bar) with no accessible name, no aria-describedby role="tooltip", or a
 *              tooltip whose text is not its name (v247 Decision 12, spec v240 §5). Never allowed.
```

Replace `railEntry`, `railFinding` and `auditRailLabels` (lines 347-393, from the comment `/** Runs inside the page (locator.evaluate): a rail link's accessible name` to the closing `}` of `auditRailLabels`) with:

```js
/** Runs inside the page (locator.evaluate): a rail link's accessible name (aria-labelledby,
 *  aria-label, then text), its href, and the text of the first role="tooltip" its
 *  aria-describedby names (null when none). Self-contained. The tooltip is read closed:
 *  its text is in the DOM whether or not the popover shows. */
function railEntry(link) {
  const ids = (attr) => (link.getAttribute(attr) ?? '').split(/\s+/).filter(Boolean);
  const labelledBy = ids('aria-labelledby')
    .map((id) => document.getElementById(id)?.textContent ?? '').join(' ').trim();
  const name = labelledBy || (link.getAttribute('aria-label') ?? '').trim() || (link.textContent ?? '').trim();
  const tooltip = ids('aria-describedby').map((id) => document.getElementById(id))
    .find((el) => el?.getAttribute('role') === 'tooltip');
  return { name, href: link.getAttribute('href') ?? '', tooltip: tooltip ? (tooltip.textContent ?? '') : null };
}

const railFinding = (entry, reason, extra) => ({
  check: 'rail-label',
  selector: entry.href ? `nav.rail a.rail-link[href="${entry.href}"]` : 'nav.rail a.rail-link',
  text: entry.name,
  detail: `rail entry ${entry.href || '(none)'}: ${reason}${extra ? ` (${extra})` : ''}`,
});

/**
 * The rail-label check (v247 Decision 12): every icon-rail entry needs an accessible name and a
 * describing role="tooltip" (its sb-hint) that reads that name. Skipped below RAIL_MIN_WIDTH (the
 * phone's tab bar navigates). Nothing is hovered: the tooltip text is read from the DOM, and
 * whether it fits on screen when open is V247-16's browser check.
 */
async function auditRailLabels(page, width) {
  if (width < RAIL_MIN_WIDTH) return [];
  const links = page.locator('nav.rail a.rail-link');
  const count = await links.count();
  if (count === 0) return [railFinding({ href: '', name: '' }, 'no rail entries found', `width ${width}`)];
  const findings = [];
  for (let i = 0; i < count; i += 1) {
    const entry = await links.nth(i).evaluate(railEntry);
    const verdict = railLabelVerdict(entry);
    if (!verdict.ok) findings.push(railFinding(entry, verdict.reason, entry.tooltip?.trim() || ''));
  }
  return findings;
}
```

`isVisuallyHidden` stays imported: `auditPage` still receives it as `hiddenSrc`.

Run: `node --check frontend/scripts/layout-audit.mjs && git grep -n "rail-label'\|\.rail-label\|labelVisible" -- frontend/scripts`
Expected: no syntax error. The grep lists only the `'rail-label'` check id (in `CHECKS`, the counts test, `railFinding`), the pre-v247 fields test in `layout-audit-lib.test.mjs`, and the `byText` fallback in `admin-page-timing.mjs` (V247-4; it matches nothing now and the `aria-label` locator wins).

- [ ] **Step 8: Run every touched suite once more**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/shell.spec.ts` and `node --test frontend/scripts/layout-audit-lib.test.mjs`
Expected: PASS, 0 failed, both.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.spec.ts
git commit -m "feat(v247): a touch long-press on a rail entry opens its hint"
git add frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs frontend/scripts/layout-audit.mjs
git commit -m "feat(v247): layout audit's rail-label check reads the rail hint, not a visible label"
```

### Task V247-10: Wordmark "Bomeo Capital"; `LABELS.brand`

**Model:** haiku — copy and two CSS declarations with exact code given; three small test edits.

**Files:**
- Modify: `frontend/src/app/shell/shell.html` (the top-bar wordmark, `<a class="brand sb-hit">` and the comment above it, lines ~50-61)
- Modify: `frontend/src/app/shell/shell.css` (the `.brand .word` comment and rules)
- Test: `frontend/src/app/shell/shell.spec.ts` (`describe('shell top bar (v203, spec v202 §3)')`, the two wordmark tests)
- Modify: `frontend/src/app/ui/icon.ts:181` (`LABELS.brand`)
- Test: `frontend/src/app/ui/icon.spec.ts` (`renders the brand icon (R1-14)`)

**Interfaces:**
- Consumes: nothing from earlier tasks. V247-8 and V247-9 edited other lines of the same three shell files, so this task runs after them.
- Produces: none.

Spec §5 / D8: the top-bar wordmark reads **Bomeo Capital**, with a real space between the words: Bomeo in `--text` weight 700, Capital in `--accent` weight 500. That is the two-tone treatment v202 D2 kept, in blue, not mint. `LABELS.brand` changes from "Swingbot" to "Bomeo Capital". Decision 10: the family becomes `var(--font-sans)`. The wordmark holds no figures, so it leaves the scope of the `--font-mono` / `tabular-nums` gate (`ui/type-gates.spec.ts`) and drops `font-variant-numeric`. Today `--font-mono` resolves to `var(--font-sans)` (tokens.css:225), so the face drawn does not change.

The space: Angular's default `preserveWhitespaces: false` drops a whitespace-only text node between two elements, so `<span>Bomeo</span> <span>Capital</span>` still renders "BomeoCapital". `&ngsp;` is Angular's entity for a space the compiler keeps. The test reads `textContent` and catches a dropped space.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/shell/shell.spec.ts`, `describe('shell top bar (v203, spec v202 §3)')`. Replace `renders the two-tone wordmark as two spans, not one coloured string` and `gives the wordmark the pre-v195 treatment, Capital in the accent, linking to the Dashboard` with:

```ts
  it('renders the two-tone wordmark as two spans with a real space between them (v247, spec v240 D8)', () => {
    const word = render().querySelector('header.topbar > a.brand .word')!;
    expect(word.querySelectorAll('span')).toHaveLength(2);
    expect([...word.querySelectorAll('span')].map((x) => x.textContent)).toEqual(['Bomeo', 'Capital']);
    // An ordinary U+0020, not a no-break space and not nothing.
    expect(word.textContent).toBe('Bomeo Capital');
  });

  it('draws Bomeo in the text colour at 700 and Capital in the accent at 500, in the sans face, linking to the Dashboard', () => {
    const brand = render().querySelector('header.topbar > a.brand')!;
    expect(brand.getAttribute('href')).toBe('/dashboard');
    expect(brand.getAttribute('aria-label')).toBe('Bomeo Capital — go to the Dashboard');
    expect(brand.querySelector('sb-icon')).toBeNull();          // the diamond heads the rail above phone width
    const css = readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '');
    const rule = (selector: string) =>
      css.match(new RegExp('^' + selector.replace(/[.]/g, '[.]') + ' [{][^}]*[}]', 'm'))?.[0] ?? '';
    const word = rule('.brand .word');
    for (const declaration of ['font-family: var(--font-sans);', 'font-size: var(--text-body);', 'font-weight: 700;',
      'letter-spacing: -0.02em;', 'white-space: nowrap;', 'color: var(--text);']) {
      expect(word, declaration).toContain(declaration);
    }
    // No figures in a wordmark: no mono face and no tabular figures (v247 Decision 10).
    expect(word).not.toContain('--font-mono');
    expect(word).not.toContain('tabular-nums');
    const capital = rule('.brand .word span:last-child');
    expect(capital).toContain('color: var(--accent);');
    expect(capital).toContain('font-weight: 500;');
    // Nav and brand never read the money colours (spec v240 §1).
    expect(word + capital).not.toMatch(/--pos|--neg/);
  });
```

`frontend/src/app/ui/icon.spec.ts`: replace `renders the brand icon (R1-14)` with:

```ts
  it('renders the brand icon, named Bomeo Capital by default (R1-14, v247)', () => {
    expect(ICON_NAMES).toContain('brand');
    expect(render('brand').querySelector('svg path')).not.toBeNull();
    expect(render('brand').getAttribute('title')).toBe('Bomeo Capital');
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/shell.spec.ts --include src/app/ui/icon.spec.ts`
Expected: FAIL. The wordmark `textContent` reads `'BomeoCapital'`, `.brand .word` still reads `--font-mono` / `tabular-nums` with no `color: var(--text);`, the last span has no `font-weight: 500;`, and the brand icon's title reads `'Swingbot'`.

- [ ] **Step 3: Implement**

`frontend/src/app/ui/icon.ts:181`, in `LABELS`:

```ts
  cancelled: 'Cancelled', trailing: 'Trailing stop', brand: 'Bomeo Capital',
```

`frontend/src/app/shell/shell.html`, the top-bar wordmark. The comment above it and the `.word` span become:

```html
      <!-- v247 (spec v240 §5, D8): the two-tone "Bomeo Capital" wordmark
           leads the bar on every device: Bomeo in the text colour, Capital in
           the accent. &ngsp; is the space Angular keeps between the two
           spans. On a phone the diamond sits before it (the rail that carries
           it elsewhere is hidden there). A link, never a heading: the page's
           one <h1> belongs to sb-page (correction 9). -->
      <a class="brand sb-hit" routerLink="/dashboard" aria-label="Bomeo Capital — go to the Dashboard">
        @if (isPhone()) {
          <sb-icon name="brand" title="" />
        }
        <span class="word"><span>Bomeo</span>&ngsp;<span>Capital</span></span>
      </a>
```

`frontend/src/app/shell/shell.css`: replace the comment above `.brand` and the two `.brand .word` rules:

```css
/* v247 (spec v240 §5, D8): the two-tone "Bomeo Capital" wordmark leads the
   bar; on a phone the diamond sits before it. Sans, not mono: a wordmark
   holds no figures (v247 Decision 10). Accent, never mint (spec v240 §1). */
```

(keep the `.brand` and `.brand sb-icon` rules between the comment and `.brand .word` as they are)

```css
.brand .word {
  font-family: var(--font-sans);
  font-size: var(--text-body);
  font-weight: 700;
  letter-spacing: -0.02em;
  white-space: nowrap;
  color: var(--text);
}
.brand .word span:last-child { color: var(--accent); font-weight: 500; }
```

The phone rule that visually collapses `.brand .word` while the shock pill and the read-only badge share the bar (`@media (max-width: 639px)`, `clip-path: inset(50%)`) is unchanged: the words stay in the link's accessible name.

If the test still reads `'BomeoCapital'` after this step (an Angular build that does not decode `&ngsp;` in this position), use `<span>Bomeo</span>{{ ' ' }}<span>Capital</span>` instead: an interpolated text node is never stripped. Update the comment to match.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/shell.spec.ts --include src/app/ui/icon.spec.ts --include src/app/ui/type-gates.spec.ts --include src/app/ui/money-colour.spec.ts`
Expected: PASS, 0 failed. `money-colour.spec.ts` still finds `.brand .word` among the shell nav rules; `type-gates.spec.ts` no longer sees the wordmark as a mono rule.

- [ ] **Step 5: Confirm the old name is gone from the app**

Run: `git grep -n "Swingbot'\|BomeoCapital" -- frontend/src`
Expected: no output. (The old comment's "BomeoCapital" in `shell.html` was replaced in Step 3.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts frontend/src/app/ui/icon.ts frontend/src/app/ui/icon.spec.ts
git commit -m "feat(v247): wordmark reads Bomeo Capital -- Bomeo 700 text, Capital 500 accent, sans; brand icon label follows"
```

